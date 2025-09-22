import logging
import re
from typing import Callable, Dict, Iterator, List, Tuple

import boto3
import dlt
import pyarrow as pa
import pyarrow.parquet as pq

from schema_config import debt_schema, finance_schema, loan_schema, person_schema

log_file = "pipeline_run.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s|[%(levelname)s]|%(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
AWS_ROLE_ARN = "arn:aws:iam::513720670489:role/BF_Tuum_S3_Read"
AWS_SESSION_NAME = "dlt-session"
S3_BUCKET = "aws-glue-billing-finance-dev"
S3_PREFIX = "2025/09"
SCHEMAS_BY_DOMAIN = {
    "debt": debt_schema.TABLE_SCHEMAS,
    "finance": finance_schema.TABLE_SCHEMAS,
    "loan": loan_schema.TABLE_SCHEMAS,
    "person": person_schema.TABLE_SCHEMAS,
}


def to_pyarrow_type(bq_type: str) -> pa.DataType:
    """
    Convert a BigQuery-style type string to the corresponding PyArrow data type.

    Supports primitive types, arrays, decimals with precision/scale, and special cases.

    Args:
        bq_type (str): Data type string, e.g. "STRING", "INT64", "ARRAY<STRING>", "DECIMAL(10,2)"

    Returns:
        pa.DataType: Corresponding PyArrow data type object.

    Raises:
        ValueError: If the input type string is unsupported.
    """
    if bq_type.startswith("ARRAY<") and bq_type.endswith(">"):
        inner_type_str = bq_type[6:-1]
        inner_type = to_pyarrow_type(inner_type_str)
        return pa.list_(inner_type)
    decimal_match = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", bq_type)
    if decimal_match:
        precision = int(decimal_match.group(1))
        scale = int(decimal_match.group(2))
        return pa.decimal128(precision, scale)
    if bq_type == "NUMERIC":
        return pa.decimal128(38, 18)
    type_map = {
        "STRING": pa.string(),
        "DATE": pa.date32(),
        "TIMESTAMP": pa.timestamp("ns"),
        "BOOL": pa.bool_(),
        "DOUBLE": pa.float64(),
        "INT64": pa.int64(),
        "INT32": pa.int32(),
        "RECORD": pa.struct([]),
        "BYTES": pa.binary(),
    }
    if bq_type not in type_map:
        raise ValueError(f"Unsupported type {bq_type}")
    return type_map[bq_type]


def to_pyarrow_schema(schema_dict: Dict[str, str]) -> pa.Schema:
    """
    Convert a dictionary of column name to BigQuery-type strings into a PyArrow schema.

    Args:
        schema_dict (Dict[str, str]): Mapping of column names to type strings.

    Returns:
        pa.Schema: PyArrow schema object representing all columns.
    """
    fields = [
        pa.field(col, to_pyarrow_type(dtype)) for col, dtype in schema_dict.items()
    ]
    return pa.schema(fields)


def assume_role_aws() -> dict:
    """
    Assume an AWS IAM role to get temporary security credentials.

    Uses boto3 STS client to request credentials for the configured role ARN.

    Returns:
        dict: Dictionary containing aws_access_key_id, aws_secret_access_key, aws_session_token.
    """
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
    """
    Create a boto3 S3 client configured with provided AWS temporary credentials.

    Args:
        aws_creds (dict): AWS credentials with keys 'aws_access_key_id', 'aws_secret_access_key', 'aws_session_token'.

    Returns:
        boto3.client: Configured S3 client instance.
    """
    return boto3.client(
        "s3",
        aws_access_key_id=aws_creds["aws_access_key_id"],
        aws_secret_access_key=aws_creds["aws_secret_access_key"],
        aws_session_token=aws_creds["aws_session_token"],
    )


def extract_domain_and_table(s3_key: str) -> Tuple[str, str]:
    """
    Parse an S3 object key to extract the domain and table names.

    Assumes the key format includes a folder name like 'reports_db_<domain>.<table>'.

    Args:
        s3_key (str): The S3 object key path.

    Returns:
        Tuple[str, str]: Domain name and table name extracted from the key.
    """
    parts = s3_key.split("/")
    folder_name = parts[3]
    domain_table = folder_name[len("reports_db_") :]
    domain, table = domain_table.split(".", 1)
    return domain, table


def list_s3_parquet_files(s3_client, bucket: str, prefix: str) -> List[str]:
    """
    List all parquet file keys under a given bucket and prefix in S3.

    Uses S3 paginator to handle potentially many objects.

    Args:
        s3_client (boto3.client): Authenticated S3 client.
        bucket (str): S3 bucket name.
        prefix (str): Prefix path within the bucket to list under.

    Returns:
        List[str]: List of parquet file keys (paths).
    """
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
    """
    Read a parquet file from S3 into a PyArrow Table.

    Args:
        s3_client (boto3.client): Authenticated S3 client.
        bucket (str): S3 bucket name.
        key (str): S3 object key for the parquet file.

    Returns:
        pa.Table: PyArrow table representation of the parquet data.
    """
    obj = s3_client.get_object(Bucket=bucket, Key=key, RequestPayer="requester")
    buffer = obj["Body"].read()
    return pq.read_table(pa.BufferReader(buffer))


def build_columns_hint(
    table_name: str, domain_schemas: Dict[str, Dict[str, str]]
) -> dict:
    """
    Generate column type hints suitable for the dlt pipeline from the domain schema for a given table.

    Maps BigQuery-like types to dlt supported data types and handles arrays as JSON.

    Args:
        table_name (str): Name of the table.
        domain_schemas (Dict[str, Dict[str, str]]): Mapping of all tables to their column schemas.

    Returns:
        dict: Mapping of column names to dictionaries with "data_type" keys for dlt hints.
    """
    schema = domain_schemas.get(table_name, {})
    bq_to_dlt = {
        "STRING": "text",
        "DATE": "date",
        "TIMESTAMP": "timestamp",
        "BOOL": "bool",
        "NUMERIC": "decimal",
        "DOUBLE": "double",
        "INT32": "bigint",
        "INT64": "bigint",
        "RECORD": "json",
        "BYTES": "binary",
    }
    columns = {}
    for col, dtype in schema.items():
        if dtype.startswith("ARRAY<"):
            columns[col] = {"data_type": "json"}
        else:
            if dtype.startswith("DECIMAL("):
                columns[col] = {"data_type": "decimal"}
            else:
                columns[col] = {"data_type": bq_to_dlt.get(dtype, "text")}
    return columns


def make_resource(
    data: List[dict],
    name: str,
    domain_schemas: Dict[str, Dict[str, str]],
    primary_key: List[str] = None,
) -> Callable[[], Iterator[dict]]:
    """
    Create a dlt resource generator function yielding rows from data with column hints.

    Args:
        data (List[dict]): List of records (row dictionaries) to be yielded by the resource.
        name (str): Name of the resource (usually the table name).
        domain_schemas (Dict[str, Dict[str, str]]): Mapping of table schemas for column hints.
        primary_key (List[str], optional): List of primary key column names for applying hints.

    Returns:
        Callable[[], Iterator[dict]]: A generator function decorated as a dlt resource.
    """
    columns_hint = build_columns_hint(name, domain_schemas)

    @dlt.resource(name=name, columns=columns_hint)
    def resource_func() -> Iterator[dict]:
        for row in data:
            yield row

    if primary_key:
        resource_func.apply_hints(primary_key=primary_key)
    return resource_func


def log_schema_differences(
    expected_schema: pa.Schema, actual_schema: pa.Schema, table_name: str, file_key: str
):
    """
    Log differences between expected PyArrow schema and actual schema from parquet file.

    Logs missing columns, extra columns, and type mismatches with details.

    Args:
        expected_schema (pa.Schema): Expected schema to validate against.
        actual_schema (pa.Schema): Schema read from the parquet file.
        table_name (str): Name of the table the file belongs to.
        file_key (str): S3 key of the file being validated.
    """
    expected_fields = {field.name: field for field in expected_schema}
    actual_fields = {field.name: field for field in actual_schema}
    missing_cols = [col for col in expected_fields if col not in actual_fields]
    extra_cols = [col for col in actual_fields if col not in expected_fields]
    type_mismatches = []
    for col in expected_fields:
        if col in actual_fields:
            exp_type = expected_fields[col].type
            act_type = actual_fields[col].type
            if not exp_type.equals(act_type):
                type_mismatches.append((col, exp_type, act_type))
    if missing_cols or extra_cols or type_mismatches:
        logger.info(
            f"Schema mismatch detected in file {file_key} for table {table_name}:"
        )
        if missing_cols:
            logger.info(f"  Missing columns: {missing_cols}")
        if extra_cols:
            logger.info(f"  Extra columns: {extra_cols}")
        if type_mismatches:
            for col, exp_t, act_t in type_mismatches:
                logger.info(
                    f"  Type mismatch in column '{col}': expected {exp_t}, got {act_t}"
                )
    else:
        logger.info(
            f"No schema mismatch detected for table {table_name} in file {file_key}"
        )


def main():
    aws_creds = assume_role_aws()
    s3_client = get_s3_client(aws_creds)
    files = list_s3_parquet_files(s3_client, S3_BUCKET, S3_PREFIX)
    files_by_domain = files_by_domain = {
        "debt": [],
        "finance": [],
        "loan": [],
        "person": [],
    }
    for key in files:
        try:
            domain, table = extract_domain_and_table(key)
        except Exception:
            continue
        if domain in files_by_domain:
            files_by_domain[domain].append((key, table))
    for domain, file_table_pairs in files_by_domain.items():
        if not file_table_pairs:
            logger.info(f"No files found for domain {domain}")
            continue
        logger.info(f"Processing domain: {domain}")
        schemas = SCHEMAS_BY_DOMAIN[domain]
        pipeline = dlt.pipeline(
            pipeline_name=f"raw_{domain}",
            destination="filesystem",
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
                log_schema_differences(expected_schema, table.schema, table_name, key)
                logger.info(f"Skipping file {key} due to schema mismatch")
                continue
            data_dicts = table.to_pylist()
            primary_key = None
            res = make_resource(data_dicts, table_name, schemas, primary_key)
            resources.append(res)
        if resources:
            load_info = pipeline.run(
                resources, write_disposition="append", loader_file_format="parquet"
            )
            logger.info(f"Finished loading domain {domain}:")
            logger.info(load_info)
        else:
            logger.info(f"No valid data to load for domain {domain}")


if __name__ == "__main__":
    main()
