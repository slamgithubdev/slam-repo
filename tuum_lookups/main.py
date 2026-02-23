import json
import logging
import os
import sys
# import tuum_lookups
# import tuum_lookups.lookups_manager
import requests



from tuum_lookups.lookups_manager.settings import get_auth_url      #import just the method?
from tuum_lookups.lookups_manager.auth import authenticate_employee, create_session_with_token


from dotenv import dotenv_values

#from custom_fields_manager.config.settings import get_auth_url
# from custom_fields_manager.config.entities import ENTITY_REGISTRY
# from custom_fields_manager.models.field_models import (
#     FieldSetDefinition, FieldDefinition, ValueType
# )
# from custom_fields_manager.core.auth import authenticate_employee, create_session_with_token
# from custom_fields_manager.core.manager import CustomFieldsManager
# from custom_fields_manager.core.reporter import ReportGenerator
# from custom_fields_manager.cli.interactive import InteractiveBuilder


# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("lookups_manager.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)


logger = logging.getLogger(__name__)

def main():
    """Main execution"""

    logger.info("=" * 70)
    logger.info("TUUM LOOKUPS MANAGER")
    logger.info("=" * 70)

    # Load environment variables
    try:
        config_env = {**dotenv_values(".env.shared"), **dotenv_values(".env.secret")}
    except Exception as e:
        logger.error(f"Error loading .env files: {e}")
        sys.exit(1)

    tenant_code = config_env.get("TENANT_CODE", "BF")
    username = config_env["EMPLOYEE_USERNAME"]

    logger.info(f"Tenant: {tenant_code}")
    logger.info(f"User: {username}")

    # Authenticate
    auth_url = get_auth_url("dev")
    logger.info(f"Authenticating to: {auth_url}")

    try:
        token = authenticate_employee(
            auth_url=auth_url,
            username=username,
            password=config_env["EMPLOYEE_PASSWORD"],
            tenant_code=tenant_code,
        )
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)

    if not token:
        logger.error("Authentication failed")
        sys.exit(1)

    # Create session
    session = create_session_with_token(token=token, tenant_code=tenant_code)

    

    def create_lookup_type(entity_name, lookup_type_code, payload):

        url = f"https://lookup-api.billing-finance-dev.tuumplatform.com/entity/{entity_name}/lookup-type/{lookup_type_code}"
        #url = f"https://lookup-api.billing-finance-dev.tuumplatform.com/entity/{entityName}/lookup-type/{lookupTypeCode}"
        response = session.post(url, json=payload)    
        
        if response.status_code == 201:
            print("Lookup type created successfully")
            return response.json()
        else:
            print(f"Failed with {response.status_code}: {response.text}")
            return None

if __name__ == "__main__":
  #  main()
  payload = {
      "description": "person title",
      "values": [
          {"code":"1", "label": "MR"},
          {"code":"2", "label": "MRS"},
      ]

  }

  create_lookup_type("person", "TITLE", payload)
  print("success")
