
import logging
import os
import sys
import requests
from dotenv import dotenv_values

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path setup
# We assume this file is in tuum_custom_fields/lookup_and_custom_fields_manager
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)

# Add paths so we can import modules
sys.path.append(parent_dir)
sys.path.append(grandparent_dir)
# Also add tuum_lookups path explicitly if needed, but grandparent_dir should cover it
# as tuum_lookups appears to be a package inside grandparent_dir

def run_probe():
    # 1. Load Environment
    logger.info(f"Current Dir: {current_dir}")
    logger.info(f"Grandparent Dir: {grandparent_dir}")
    
    env_shared = os.path.join(grandparent_dir, "tuum_lookups", ".env.shared")
    env_secret = os.path.join(grandparent_dir, "tuum_lookups", ".env.secret")
    
    if not os.path.exists(env_shared):
        logger.error(f"Environment file not found: {env_shared}")
        return

    config = {**dotenv_values(env_shared), **dotenv_values(env_secret)}
    tenant = config.get("TENANT_CODE", "BF")
    username = config.get("EMPLOYEE_USERNAME")
    password = config.get("EMPLOYEE_PASSWORD")
    
    if not username:
        logger.error("Missing credentials")
        return

    # 2. Authenticate
    # Import here to ensure paths are set
    try:
        from tuum_lookups.lookups_manager.auth import authenticate_employee, create_session_with_token
        from tuum_lookups.lookups_manager.settings import get_auth_url
        from tuum_lookups.lookups_manager.settings import APIModule
    except ImportError as e:
        logger.error(f"Import failed: {e}")
        # manual path check
        logger.info(f"Sys Path: {sys.path}")
        return

    auth_url = get_auth_url("dev")
    logger.info(f"Authenticating to {auth_url}")
    
    try:
        token = authenticate_employee(auth_url, username, password, tenant)
        session = create_session_with_token(token, tenant)
    except Exception as e:
        logger.error(f"Auth failed: {e}")
        return

    # 3. Probe URLs
    base_url = "https://lookup-api.billing-finance-dev.tuumplatform.com"
    entity = "COLLATERAL" # Try Uppercase
    code = "VEHICLE_CONDITION_V1"
    
    # Define test endpoints
    endpoints = [
        f"/api/v1/entity/{entity}/lookup-type/{code}", # With api/v1
        f"/entity/{entity}/lookup-type/{code}", # Without api/v1
    ]
    
    # Try promising payload with 'lookups' key
    # Try payload with translations
    # Try payload with LIST of translations and languageCode
    payload_variants = [
        # Variant 1: languageCode/translation
        {
            "lookupTypeName": "Vehicle Condition", 
            "lookups": [{
                "lookupCode": "TEST", 
                "translations": [{"languageCode": "en", "translation": "Test"}]
            }]
        },
        # Variant 2: languageCode/name
        {
            "lookupTypeName": "Vehicle Condition", 
            "lookups": [{
                "lookupCode": "TEST", 
                "translations": [{"languageCode": "en", "name": "Test"}]
            }]
        },
        # Variant 3: languageCode/value
        {
            "lookupTypeName": "Vehicle Condition", 
            "lookups": [{
                "lookupCode": "TEST", 
                "translations": [{"languageCode": "en", "value": "Test"}]
            }]
        }
    ]

    logger.info("Starting Sub-resource Probe...")
    
    url_base = f"{base_url}/api/v1/entity/COLLATERAL/lookup-type/VEHICLE_CONDITION_V1"
    
    # 1. Try GET
    try:
        logger.info(f"GET {url_base}")
        resp = session.get(url_base)
        logger.info(f"Status: {resp.status_code}")
        logger.info(f"Body: {resp.text[:300]}")
    except Exception as e:
        logger.error(e)
        
    # 2. Try POST to /values or /lookups
    sub_paths = ["/values", "/lookups", "/items"]
    
    value_payload = {
        "lookupCode": "TEST_ADD",
        "translations": [{"languageCode": "en", "translation": "Test Add"}]
    }
    
    for sub in sub_paths:
        url = url_base + sub
        logger.info(f"\nPOST {url}")
        try:
            resp = session.post(url, json=value_payload)
            logger.info(f"Status: {resp.status_code}")
            logger.info(f"Body: {resp.text[:300]}")
        except Exception as e:
            logger.error(e)

if __name__ == "__main__":
    run_probe()
