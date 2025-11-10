"""
Authentication module.
"""

import json
import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)


def authenticate_employee(auth_url: str, username: str, password: str, 
                         tenant_code: str) -> Optional[str]:
    """
    Authenticates an employee with the Tuum API.

    Args:
        auth_url: Full authentication URL
        username: Employee username
        password: Employee password
        tenant_code: Tenant code

    Returns:
        Authentication token if successful, None otherwise
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
            return None

        if response.status_code // 100 != 2:
            logger.error(f"Authentication failed with status {response.status_code}")
            return None

        token = data.get("data", {}).get("token")
        if not token:
            logger.error("Authentication response did not contain a token.")
            return None

        logger.info("✓ Employee authenticated successfully")
        return token

    except requests.RequestException as e:
        logger.error(f"Error during authentication: {e}")
        raise e


def create_session_with_token(token: str, tenant_code: str) -> requests.Session:
    """
    Creates an authenticated HTTP session.

    Args:
        token: Authentication token
        tenant_code: Tenant code

    Returns:
        Configured session with auth token in headers
    """
    session = requests.Session()

    retry_strategy = Retry(
        total=4,
        backoff_factor=3,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)

    session.headers.update({
        "x-auth-token": token,
        "x-tenant-code": tenant_code,
        "Accept-Language": "en",
        "Content-Type": "application/json",
        "accept": "application/json",
    })

    logger.info("✓ Session configured with auth token")

    return session
