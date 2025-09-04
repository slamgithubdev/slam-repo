import logging
from typing import Callable, Dict, Iterator, List, Tuple

import boto3
import dlt
import pyarrow as pa
import pyarrow.parquet as pq

from schema_config import debt_schema, finance_schema, loan_schema, person_schema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AWS_ROLE_ARN = "arn:aws:iam::513720670489:role/BF_Tuum_S3_Read"
AWS_SESSION_NAME = "dlt-session"

S3_BUCKET = "aws-glue-billing-finance-dev"
S3_PREFIX = "2025/08/16"

SCHEMAS_BY_DOMAIN = {
    "debt": debt_schema.TABLE_SCHEMAS,
    "finance": finance_schema.TABLE_SCHEMAS,
    "loan": loan_schema.TABLE_SCHEMAS,
    "person": person_schema.TABLE_SCHEMAS,
}


def assume_role_aws() -> dict:
    sts_client = boto3.client("sts")
    assumed_role = sts_client.assume_role(
        RoleArn=AWS_ROLE_ARN,
        RoleSessionName=AWS_SESSION_NAME,
    )
    creds = assumed_role["Credentials"]
    return {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
    }


def get_s3_client(aws_creds):
    return boto3.client(
        "s3",
        aws_access_key_id=aws_creds["aws_access_key_id"],
        aws_secret_access_key=aws_creds["aws_secret_access_key"],
        aws_session_token=aws_creds["aws_session_token"],
    )


def to_pyarrow_schema(table_dict: Dict[str, str]) -> pa.Schema:
    TYPE_MAP = {
        "STRING": pa.string(),
        "DATE": pa.date32(),
        "TIMESTAMP": pa.timestamp("ns"),
        "BOOL": pa.bool_(),
        "NUMERIC": pa.float64(),
        "INT64": pa.int64(),
        "RECORD": pa.struct([]),
        "BYTES": pa.binary(),
    }
    fields = []
    for col, dtype in table_dict.items():
        pa_type = TYPE_MAP.get(dtype)
        if pa_type is None:
            raise ValueError(f"Unsupported type {dtype} in schema")
        fields.append(pa.field(col, pa_type))
    return pa.schema(fields)


def extract_domain_and_table(s3_key: str) -> Tuple[str, str]:
    parts = s3_key.split("/")
    folder_name = parts[3]
    domain_table = folder_name[len("reports_db_") :]
    domain, table = domain_table.split(".", 1)
    return domain, table


def list_s3_parquet_files(s3_client, bucket: str, prefix: str) -> List[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix, RequestPayer="requester")
    files = []
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".parquet"):
                files.append(key)
    return files


def read_s3_file(s3_client, bucket: str, key: str) -> pa.Table:
    obj = s3_client.get_object(Bucket=bucket, Key=key, RequestPayer="requester")
    buffer = obj["Body"].read()
    return pq.read_table(pa.BufferReader(buffer))


def make_resource(
    data: List[dict], name: str, primary_key: List[str] = None
) -> Callable[[], Iterator[dict]]:
    @dlt.resource(name=name)
    def resource_func() -> Iterator[dict]:
        for row in data:
            yield row

    if primary_key:
        resource_func.apply_hints(primary_key=primary_key)
    return resource_func


def main():
    aws_creds = assume_role_aws()
    s3_client = get_s3_client(aws_creds)

    files = list_s3_parquet_files(s3_client, S3_BUCKET, S3_PREFIX)

    files_by_domain = {"debt": [], "finance": [], "loan": [], "person": []}
    for key in files:
        try:
            domain, table = extract_domain_and_table(key)
        except Exception:
            continue
        if domain in files_by_domain:
            files_by_domain[domain].append((key, table))

    for domain, file_table_pairs in files_by_domain.items():
        if not file_table_pairs:
            continue
        logger.info(f"Processing domain: {domain}")
        schemas = SCHEMAS_BY_DOMAIN[domain]

        pipeline = dlt.pipeline(
            pipeline_name=f"s3_to_gcs_{domain}_v8",
            destination="filesystem",  # configured for GCS in your toml files
        )

        resources = []

        for key, table_name in file_table_pairs:
            if table_name not in schemas:
                logger.info(f"Skipping unknown table {table_name}")
                continue

            expected_schema = to_pyarrow_schema(schemas[table_name])

            logger.info(f"Validating file {key} for table {table_name}")
            table = read_s3_file(s3_client, S3_BUCKET, key)

            if not table.schema.equals(expected_schema):
                logger.info(f"Schema mismatch in {key}, skipping")
                continue

            data_dicts = table.to_pylist()

            # Optionally define primary keys per your schema
            primary_key = None  # set your keys if you have them, e.g. ["id"]

            res = make_resource(data_dicts, table_name, primary_key)
            resources.append(res)

        if resources:
            load_info = pipeline.run(
                resources, write_disposition="merge", loader_file_format="parquet"
            )
            logger.info(f"Finished loading domain {domain}:")
            logger.info(load_info)
        else:
            logger.info(f"No valid data to load for domain {domain}")


if __name__ == "__main__":
    main()
