import os

import dlt
from dlt.sources.filesystem import filesystem, read_parquet
from google.cloud import storage

from schema_config.debt_schema import TABLE_SCHEMAS as DEBT_SCHEMAS
from schema_config.finance_schema import TABLE_SCHEMAS as FINANCE_SCHEMAS
from schema_config.loan_schema import TABLE_SCHEMAS as LOAN_SCHEMAS
from schema_config.person_schema import TABLE_SCHEMAS as PERSON_SCHEMAS
from schema_config.primary_key_config import PRIMARY_KEY_MAPPING

# ---- CONFIG: Set your GCS bucket ----
GCS_BUCKET_NAME = "daneshp-sandbox-delphi-data"
GCS_BUCKET_URI = f"gs://{GCS_BUCKET_NAME}"
DOMAIN_SCHEMAS = {
    "debt": DEBT_SCHEMAS,
    "finance": FINANCE_SCHEMAS,
    "loan": LOAN_SCHEMAS,
    "person": PERSON_SCHEMAS,
}
storage_client = storage.Client()


def list_parquet_files_in_bucket(bucket_name: str):
    """Get all parquet files in the bucket."""
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs()
    parquet_files = []
    for blob in blobs:
        if blob.name.endswith(".parquet"):
            parquet_files.append(blob.name)
    return parquet_files


def resolve_domain_and_table(path: str):
    """Infer domain and table name from path."""
    for domain, schemas in DOMAIN_SCHEMAS.items():
        if f"raw_{domain}_dataset" in path:
            parts = path.split("/")
            for part in parts:
                if part in schemas:
                    return domain, part
    return None, None


def group_files_by_folder(parquet_files):
    """Group parquet file paths by their domain and table folder."""
    grouped = {}
    for path in parquet_files:
        domain, table = resolve_domain_and_table(path)
        if domain and table:
            folder_path = "/".join(path.split("/")[:-1])
            key = (domain, table, folder_path)
            grouped.setdefault(key, []).append(path)
    return grouped


def bq_type_to_dlt_type(bq_type: str) -> str:
    mapping = {
        "STRING": "text",
        "INT64": "bigint",
        "INT32": "bigint",
        "TIMESTAMP": "timestamp",
        "DATE": "date",
        "BOOL": "bool",
        "DECIMAL(38, 18)": "decimal",
        "NUMERIC": "decimal",
        "BYTES": "binary",
    }
    return mapping.get(bq_type.upper(), "text")


def build_columns_hint(schema: dict) -> dict:
    return {
        col: {"data_type": bq_type_to_dlt_type(dtype)} for col, dtype in schema.items()
    }


def create_dlt_resource(domain: str, table: str, folder_path: str):
    schema = DOMAIN_SCHEMAS[domain].get(table)
    if not schema:
        raise ValueError(f"No schema found for {domain}.{table}")
    columns_hint = build_columns_hint(schema)
    resource_name = f"{domain}_{table}"

    @dlt.resource(name=resource_name, columns=columns_hint)
    def resource():
        folder_bucket_url = f"{GCS_BUCKET_URI}/{folder_path}"
        print(f"Reading all parquet files from folder: {folder_bucket_url}")
        yield from (filesystem(bucket_url=folder_bucket_url) | read_parquet())

    res = resource
    # primary_key = PRIMARY_KEY_MAPPING.get(resource_name)
    primary_key = None
    if primary_key:
        res.apply_hints(primary_key=primary_key)
    else:
        print(f"Warning: No primary key defined for {resource_name}")

    return res


def collect_resources_from_gcs():
    parquet_files = list_parquet_files_in_bucket(GCS_BUCKET_NAME)
    grouped = group_files_by_folder(parquet_files)
    resources = []
    for (domain, table, folder_path), files in grouped.items():
        try:
            resource = create_dlt_resource(domain, table, folder_path)
            resources.append(resource)
            print(
                f"Prepared resource for {domain}.{table} from folder {folder_path} with {len(files)} files"
            )
        except Exception as e:
            print(
                f"Error creating resource for {domain}.{table} in folder {folder_path}: {e}"
            )
    return resources


def run_pipeline():
    pipeline = dlt.pipeline(
        pipeline_name="gcs_to_bq_no_pk",
        destination="bigquery",
        dataset_name="src_tuum_no_pk",
    )
    resources = collect_resources_from_gcs()
    if not resources:
        print("No valid resources found to run pipeline.")
        return
    info = pipeline.run(resources, write_disposition="merge")
    print("Pipeline run info:", info)
    print("Normalization info:", pipeline.last_trace.last_normalize_info)


if __name__ == "__main__":
    run_pipeline()
