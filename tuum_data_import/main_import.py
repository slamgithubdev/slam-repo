# main_import.py

import datetime
import glob
import json
import logging
import os
import random
import string
import sys

import requests
from dotenv import dotenv_values
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

fh = logging.FileHandler("app.log", encoding="utf-8")
formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

# Also log to console
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
logger.addHandler(ch)


def generate_dynamic_source_ref(data_type):
    """
    Generates a dynamic and unique source reference string for imports.

    Args:
        data_type (str): Identifies type of data being imported, e.g. 'contracts'.

    Returns:
        str: A unique string combining current datetime and random characters.
    """
    dt = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    rand_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{dt}_{data_type}_{rand_str}"


def authenticate_employee(auth_url, username, password, tenant_code):
    """
    Authenticates an employee by sending credentials to the authentication API endpoint.

    Args:
        auth_url (str): Authentication endpoint URL.
        username (str): Employee username.
        password (str): Employee password.
        tenant_code (str): Tenant code for access control.

    Returns:
        str or None: Authentication token if successful; otherwise None.
    """
    payload = {"username": username, "password": password}
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json",
        "x-tenant-code": tenant_code,
        "Accept-Language": "en",
    }

    try:
        response = requests.post(
            auth_url, headers=headers, data=json.dumps(payload), timeout=10
        )

        logger.info(f"Authentication response status: {response.status_code}")

        try:
            data = response.json()
            logger.info(f"Authentication response JSON: {json.dumps(data, indent=2)}")
        except json.JSONDecodeError:
            logger.error("Response content is not valid JSON")
            logger.error(f"Raw response content: {response.text}")

        if response.status_code // 100 != 2:
            logger.error(f"Authentication failed with status {response.status_code}")
            return None

        token = data.get("data", {}).get("token")
        if not token:
            logger.error("Authentication response did not contain a token.")
            return None

        logger.info("Employee authenticated successfully.")
        return token

    except requests.RequestException as e:
        logger.error(f"Error during authentication: {e}")
        raise e


def create_session_with_token(token):
    """
    Creates a requests.Session configured with retry strategy and authentication token header.

    Args:
        token (str): Authentication token to include in headers.

    Returns:
        requests.Session: Configured HTTP session object.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=4,
        backoff_factor=3,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.headers.update({"x-auth-token": token})
    return session


def import_single_file(
    session, import_base_url, source_name, source_ref, tenant_code, file_path, data_key
):
    """
    Imports a single data file to the API, handling loading, request construction, and logging.

    Args:
        session (requests.Session): Authenticated HTTP session.
        import_base_url (str): Base URL of the import API.
        source_name (str): External source system name.
        source_ref (str): Unique reference for this import.
        tenant_code (str): Tenant context code.
        file_path (str): Path to the JSON file to import.
        data_key (str): Top-level key in the payload ("contracts", "persons", etc.).

    Returns:
        None
    """
    headers = {
        "x-leaf-tenant-code": tenant_code,
        "x-tenant-code": tenant_code,
        "Accept-Language": "en",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Unwrap wrapped files (e.g. { "contracts": [...] }) for API payload
        if isinstance(data, dict) and data_key in data:
            data_list = data[data_key]
        else:
            data_list = data

        body = {
            "source": {"sourceName": source_name, "sourceRef": source_ref},
            data_key: data_list,
        }

        logger.info(
            f"Importing {data_key} from {os.path.basename(file_path)} "
            f"with {len(data_list)} items"
        )

        response = session.post(
            f"{import_base_url}/api/v1/import/sample", headers=headers, json=body
        )

        logger.info(
            f"Response status: {response.status_code} for {os.path.basename(file_path)}"
        )

        try:
            response_data = response.json()
            import_process_id = response_data.get("data", {}).get("importProcessId")

            if import_process_id:
                check_import_status(
                    session, import_process_id, import_base_url, tenant_code
                )
            else:
                logger.error(
                    "importProcessId not found in response; skipping status check."
                )

            if response.status_code == 202:
                logger.info(f"✓ Successfully imported {os.path.basename(file_path)}")
            else:
                logger.error(f"✗ Import failed for {os.path.basename(file_path)}")

        except json.JSONDecodeError:
            logger.error(f"Failed to parse response JSON: {response.text}")

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
    except requests.RequestException as e:
        logger.error(f"Error importing {os.path.basename(file_path)}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error importing {file_path}: {e}", exc_info=True)


def check_import_status(session, import_process_id, base_url, tenant_code):
    """
    Checks the status of an asynchronous import process.

    Args:
        session (requests.Session): Authenticated HTTP session.
        import_process_id (str): Import process identifier.
        base_url (str): Base URL of the import API.
        tenant_code (str): Tenant context code.

    Returns:
        None
    """
    status_url = f"{base_url}/api/v1/import/status/{import_process_id}"
    headers = {
        "accept": "*/*",
        "x-tenant-code": tenant_code,
        "Accept-Language": "en",
    }

    try:
        status_response = session.get(status_url, headers=headers, timeout=10)
        logger.info(f"Status request URL: {status_url}")
        logger.info(f"Status response code: {status_response.status_code}")

        try:
            status_data = status_response.json()
            import_status = status_data.get("statusCode", "Unknown")
            logger.info(f"Import status for {import_process_id}: {import_status}")
            logger.debug(f"Full status response: {json.dumps(status_data, indent=2)}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed parsing status response JSON: {e}")
            logger.info(f"Raw status response text: {status_response.text}")

    except requests.RequestException as e:
        logger.error(f"Error requesting import status: {e}")


def get_all_chunk_files(config):
    """
    Auto-discovers all chunk files in the configured directories using glob patterns.

    NEW LOGIC: Uses glob to find all persons_*.json and contracts_*.json files

    Args:
        config (dict): Configuration dictionary from environment variables.

    Returns:
        dict: Mapping of data keys to lists of file paths.
                {"persons": [list of files], "contracts": [list of files]}
    """
    files = {"persons": [], "contracts": []}

    person_folder = config.get("PERSON_FILE_PATH", "./chunks_persons")
    contract_folder = config.get("CONTRACT_FILE_PATH", "./chunks_contracts")

    logger.info(f"Looking for persons chunks in: {os.path.abspath(person_folder)}")
    logger.info(f"Looking for contracts chunks in: {os.path.abspath(contract_folder)}")

    # Glob for persons files: persons_0001.json, persons_0002.json, etc.
    person_pattern = os.path.join(person_folder, "persons_*.json")
    person_files = sorted(glob.glob(person_pattern))
    if person_files:
        files["persons"] = person_files
        logger.info(f"Found {len(person_files)} persons chunk files")
    else:
        logger.warning(f"No persons chunk files found matching: {person_pattern}")

    # Glob for contracts files: contracts_0001.json, contracts_0002.json, etc.
    contract_pattern = os.path.join(contract_folder, "contracts_*.json")
    contract_files = sorted(glob.glob(contract_pattern))
    if contract_files:
        files["contracts"] = contract_files
        logger.info(f"Found {len(contract_files)} contracts chunk files")
    else:
        logger.warning(f"No contracts chunk files found matching: {contract_pattern}")

    return files


def get_target_files(config):
    """
    Determines target data chunk files based on TARGET_FILE environment variable.

    BACKWARD COMPATIBLE: Still supports specific file targeting via TARGET_FILE env var

    Args:
        config (dict): Configuration dictionary from environment variables.

    Returns:
        dict: Mapping of data keys to file paths.
    """
    target_num = config.get("TARGET_FILE")

    if not target_num:
        logger.info("TARGET_FILE not set; using auto-discovery mode")
        return None  # Signal to use get_all_chunk_files instead

    logger.info(f"TARGET_FILE mode: targeting chunk {target_num}")

    files = {}

    person_folder = config.get("PERSON_FILE_PATH", "./chunks_persons")
    contract_folder = config.get("CONTRACT_FILE_PATH", "./chunks_contracts")

    # New naming: persons_0001.json instead of person_1.json
    person_path = os.path.join(person_folder, f"persons_{target_num:04d}.json")
    if os.path.isfile(person_path):
        files["persons"] = person_path
        logger.info(f"Found persons file: {person_path}")
    else:
        logger.warning(f"Persons chunk file not found: {person_path}")

    # New naming: contracts_0001.json instead of contract_1.json
    contract_path = os.path.join(contract_folder, f"contracts_{target_num:04d}.json")
    if os.path.isfile(contract_path):
        files["contracts"] = contract_path
        logger.info(f"Found contracts file: {contract_path}")
    else:
        logger.warning(f"Contracts chunk file not found: {contract_path}")

    return files if files else None


def main():
    """
    Main execution function to authenticate, locate chunk files, and initiate import.

    IMPORT ORDER: ✓ Persons always imported FIRST, then contracts
    """
    logger.info("=" * 70)
    logger.info("TUUM DATA IMPORT - Starting")
    logger.info("=" * 70)

    try:
        config = {**dotenv_values(".env.shared"), **dotenv_values(".env.secret")}
    except Exception as e:
        logger.error(f"Error loading environment variables: {e}")
        exit(1)

    # ═══════════════════════════════════════════════════════════════════════
    # IMPORT FLAGS
    # ═══════════════════════════════════════════════════════════════════════

    import_persons = config.get("IMPORT_PERSONS", "false").lower() == "true"
    import_contracts = config.get("IMPORT_CONTRACTS", "true").lower() == "true"

    logger.info(f"Import persons: {import_persons}")
    logger.info(f"Import contracts: {import_contracts}")

    if not (import_persons or import_contracts):
        logger.error(
            "Both IMPORT_PERSONS and IMPORT_CONTRACTS are false. Nothing to import."
        )
        exit(1)

    # Authenticate
    try:
        token = authenticate_employee(
            auth_url=config["AUTH_URL"],
            username=config["EMPLOYEE_USERNAME"],
            password=config["EMPLOYEE_PASSWORD"],
            tenant_code=config.get("TENANT_CODE", "BF"),
        )
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        exit(1)

    if not token:
        logger.error("Authentication failed – terminating program.")
        exit(1)

    session = create_session_with_token(token)

    import_base_url = config.get("DATA_IMPORT_BASE_URL")
    source_name = config.get("SOURCE_NAME")
    tenant_code = config.get("LEAF_TENANT_CODE")

    # Try targeted file import first, fall back to auto-discovery
    target_files = get_target_files(config)
    if target_files is None:
        target_files = get_all_chunk_files(config)

    if not target_files or not any(target_files.values()):
        logger.error("No valid chunk files found. Exiting.")
        exit(1)

    # ═══════════════════════════════════════════════════════════════════════
    # FILTER BY IMPORT FLAGS
    # ═══════════════════════════════════════════════════════════════════════

    filtered_files = {}

    if import_persons and "persons" in target_files and target_files["persons"]:
        filtered_files["persons"] = target_files["persons"]

    if import_contracts and "contracts" in target_files and target_files["contracts"]:
        filtered_files["contracts"] = target_files["contracts"]

    if not filtered_files:
        logger.error("No files to import after applying import flags.")
        exit(1)

    logger.info(f"Files to import: {list(filtered_files.keys())}")

    # ═══════════════════════════════════════════════════════════════════════
    # IMPORT PROCESS - PERSONS FIRST, THEN CONTRACTS
    # ═══════════════════════════════════════════════════════════════════════

    logger.info("\n" + "=" * 70)
    logger.info("IMPORT PROCESS - PERSONS FIRST, THEN CONTRACTS")
    logger.info("=" * 70)

    import_count = 0

    # ✓ PERSONS ALWAYS IMPORTED FIRST (if enabled)
    if "persons" in filtered_files:
        logger.info("\n[PHASE 1] IMPORTING PERSONS")
        logger.info("-" * 70)

        file_paths = filtered_files["persons"]
        files_to_import = file_paths if isinstance(file_paths, list) else [file_paths]

        for file_path in files_to_import:
            try:
                dynamic_source_ref = generate_dynamic_source_ref("persons")
                import_single_file(
                    session,
                    import_base_url,
                    source_name,
                    dynamic_source_ref,
                    tenant_code,
                    file_path,
                    "persons",
                )
                import_count += 1
            except Exception as e:
                logger.error(f"Error processing persons file {file_path}: {e}")

    # ✓ CONTRACTS IMPORTED AFTER PERSONS
    if "contracts" in filtered_files:
        logger.info("\n[PHASE 2] IMPORTING CONTRACTS")
        logger.info("-" * 70)

        file_paths = filtered_files["contracts"]
        files_to_import = file_paths if isinstance(file_paths, list) else [file_paths]

        for file_path in files_to_import:
            try:
                dynamic_source_ref = generate_dynamic_source_ref("contracts")
                import_single_file(
                    session,
                    import_base_url,
                    source_name,
                    dynamic_source_ref,
                    tenant_code,
                    file_path,
                    "contracts",
                )
                import_count += 1
            except Exception as e:
                logger.error(f"Error processing contracts file {file_path}: {e}")

    logger.info("\n" + "=" * 70)
    logger.info(f"Import process complete. {import_count} files imported.")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
