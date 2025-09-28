import datetime
import json
import logging
import os
import random
import string

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
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Unwrap wrapped contract files (e.g. { "contracts": [...] }) for API payload
    if data_key == "contracts" and isinstance(data, dict) and "contracts" in data:
        data_list = data["contracts"]
    else:
        data_list = data

    body = {
        "source": {"sourceName": source_name, "sourceRef": source_ref},
        data_key: data_list,
    }

    logger.info(
        f"Importing {data_key} single file {os.path.basename(file_path)} with {len(data_list)} items"
    )

    try:
        response = session.post(
            f"{import_base_url}/api/v1/import/sample", headers=headers, json=body
        )

        logger.info(
            f"Response status: {response.status_code} for {os.path.basename(file_path)}"
        )

        data = response.json()
        import_process_id = data.get("data", {}).get("importProcessId")
        if import_process_id:
            check_import_status(
                session, import_process_id, import_base_url, tenant_code
            )
        else:
            logger.error(
                "importProcessId not found in response; skipping status check."
            )

        if response.status_code == 202:
            logger.info(f"Successfully imported {os.path.basename(file_path)}")
        else:
            logger.error(f"Import failed for {os.path.basename(file_path)}")

    except requests.RequestException as e:
        logger.error(f"Error importing {os.path.basename(file_path)}: {e}")


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
            logger.debug(f"Full status response JSON: {status_data}")
        except Exception as e:
            logger.error(f"Failed parsing status response JSON: {e}")
            logger.info(f"Raw status response text: {status_response.text}")
    except requests.RequestException as e:
        logger.error(f"Error requesting import status: {e}")


def get_target_files(config):
    """
    Determines target data chunk files based on environment config.

    Args:
        config (dict): Configuration dictionary from environment variables.

    Returns:
        dict: Mapping of data keys ("persons", "contracts") to file paths.
    """
    target_num = config.get("TARGET_FILE")
    if not target_num:
        logger.error("TARGET_FILE not set in env; cannot target specific chunk.")
        return {}

    files = {}
    person_folder = config.get("PERSON_FILE_PATH", "person_chunks")
    contract_folder = config.get("CONTRACT_FILE_PATH", "contract_chunks")

    person_path = os.path.join(person_folder, f"person_{target_num}.json")
    if os.path.isfile(person_path):
        files["persons"] = person_path
    else:
        logger.error(f"Person chunk file not found: {person_path}")

    contract_path = os.path.join(contract_folder, f"contract_{target_num}.json")
    if os.path.isfile(contract_path):
        files["contracts"] = contract_path
    else:
        logger.error(f"Contract chunk file not found: {contract_path}")

    return files


def main():
    """
    Main execution function to authenticate, locate chunk files, and initiate import.
    """
    config = {**dotenv_values(".env.shared"), **dotenv_values(".env.secret")}

    token = authenticate_employee(
        auth_url=config["AUTH_URL"],
        username=config["EMPLOYEE_USERNAME"],
        password=config["EMPLOYEE_PASSWORD"],
        tenant_code=config.get("TENANT_CODE", "BF"),
    )
    if not token:
        logger.error("Authentication failed – terminating program.")
        exit(1)

    session = create_session_with_token(token)

    import_base_url = config.get("DATA_IMPORT_BASE_URL")
    source_name = config.get("SOURCE_NAME")
    tenant_code = config.get("LEAF_TENANT_CODE")

    target_files = get_target_files(config)
    if not target_files:
        logger.error("No valid chunk files found for the given TARGET_FILE. Exiting.")
        exit(1)

    for data_key, file_path in target_files.items():
        # if data_key != "contracts":
        #     continue
        dynamic_source_ref = generate_dynamic_source_ref(data_key)
        import_single_file(
            session,
            import_base_url,
            source_name,
            dynamic_source_ref,
            tenant_code,
            file_path,
            data_key,
        )


if __name__ == "__main__":
    main()
