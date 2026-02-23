import json
import logging
import os
import sys
import requests
from dotenv import dotenv_values

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# PATH SETUP (CRITICAL: Must be before imports)
# --------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)             # tuum_custom_fields
grandparent_dir = os.path.dirname(parent_dir)         # tuum-data-migration

# Add parent to path to find sibling 'custom_fields_manager' (it is directly inside parent_dir)
sys.path.append(parent_dir)

# Add grandparent dir to find 'tuum_lookups' package (grandparent/tuum_lookups)
sys.path.append(grandparent_dir)

# Add current dir to path explicitly (sometimes needed for package resolution)
sys.path.append(current_dir)
# --------------------------------------------------------------------------

# Import local modules (Directly, since we are in the folder)
try:
    # Try importing as if we are in the package (if running from parent)
    from lookup_and_custom_fields_manager.lookup_manager import LookupManager
    from lookup_and_custom_fields_manager.custom_fields_extended import CustomFieldsExtended
    from lookup_and_custom_fields_manager.interactive import UnifiedInteractiveBuilder
except ImportError:
    # Fallback to direct import (if running from inside the folder)
    from lookup_manager import LookupManager
    from custom_fields_extended import CustomFieldsExtended
    from interactive import UnifiedInteractiveBuilder

# Import sibling modules
try:
    from tuum_lookups.lookups_manager.auth import authenticate_employee, create_session_with_token
    from tuum_lookups.lookups_manager.settings import get_auth_url
    
    from custom_fields_manager.models.field_models import FieldSetDefinition, FieldDefinition, ValueType
    from custom_fields_manager.config.settings import APIModule

except ImportError as e:
    logger.error(f"Failed to import dependencies: {e}")
    logger.error(f"Sys Path: {sys.path}")
    sys.exit(1)

def load_config(config_path="config.json"):
    with open(config_path, "r") as f:
        return json.load(f)

def run_orchestration(config, session, tenant_code):
    # 3. Create/Update Lookups
    lookup_manager = LookupManager(session=session)
    lookups = config.get("lookups", [])
    logger.info(f"Found {len(lookups)} lookups to process.")

    for lookup in lookups:
        entity = lookup.get("entity_name")
        code = lookup.get("lookup_type_code")
        # Payload allows 'description' and 'values'
        payload = {
            "description": lookup.get("description"),
            "values": lookup.get("values", [])
        }
        lookup_manager.create_lookup_type(entity, code, payload)

    # 4. Create/Update Custom Fields
    # Only proceed if there are fields
    custom_fields_config = config.get("custom_fields", [])
    if custom_fields_config:
        logger.info(f"Found {len(custom_fields_config)} custom field configurations to process.")
        
        # Initialize CustomFieldsExtended
        cf_manager = CustomFieldsExtended(session=session, tenant_code=tenant_code)
        
        for cf_item in custom_fields_config:
            if cf_item.get("mock_data_for_structure"):
                logger.info("Skipping mock custom field entry.")
                continue

            try:
                if "field_set" in cf_item:
                    fs_data = cf_item["field_set"]
                    if isinstance(fs_data.get("api_module"), str):
                        fs_data["api_module"] = APIModule[fs_data["api_module"]]

                    fs_def = FieldSetDefinition(**fs_data)
                    logger.info(f"Processing field set: {fs_def.field_set_id}")
                    cf_manager.create_field_set(fs_def)
                    
                    if "fields" in cf_item:
                        for field_data in cf_item["fields"]:
                            if isinstance(field_data.get("api_module"), str):
                                field_data["api_module"] = APIModule[field_data["api_module"]]

                            if isinstance(field_data.get("value_type"), str):
                                field_data["value_type"] = ValueType[field_data["value_type"]]

                            f_def = FieldDefinition(**field_data)
                            logger.info(f"Processing field: {f_def.field_id} in set {fs_def.field_set_id}")
                            cf_manager.create_field(fs_def, f_def)
            except Exception as e:
                logger.error(f"Failed to process custom field item: {e}")

    logger.info("Processing complete.")

def main():
    logger.info("Starting Unified Lookup and Custom Fields Manager")
    
    mode = "apply"
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        mode = "interactive"

    if mode == "interactive":
        logger.info("Entering Interactive Mode...")
        builder = UnifiedInteractiveBuilder()
        config = builder.run()
        
        apply_now = input("\nApply configuration now? (y/n): ").strip().lower()
        if apply_now != 'y':
            logger.info("Configuration saved. Run without arguments to apply later.")
            return
    else:
        # Load Config
        try:
            config = load_config(os.path.join(current_dir, "config.json"))
            logger.info("Configuration loaded.")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return

    # 2. Auth
    # Load environment variables from parent or specific location
    # Trying to find .env files in parent root or tuum_lookups
    env_shared_path = os.path.join(grandparent_dir, "tuum_lookups", ".env.shared")
    env_secret_path = os.path.join(grandparent_dir, "tuum_lookups", ".env.secret")
    
    if not os.path.exists(env_shared_path):
         # Fallback to current dir if copied
         env_shared_path = ".env.shared"
         env_secret_path = ".env.secret"

    try:
        config_env = {**dotenv_values(env_shared_path), **dotenv_values(env_secret_path)}
        if not config_env:
             logger.warning("No environment variables found via dotenv. Using environment defaults if available.")
    except Exception as e:
        logger.error(f"Error loading .env files: {e}")
        sys.exit(1)

    tenant_code = config_env.get("TENANT_CODE", "BF")
    username = config_env.get("EMPLOYEE_USERNAME")
    password = config_env.get("EMPLOYEE_PASSWORD")

    if not username or not password:
        logger.error("Missing EMPLOYEE_USERNAME or EMPLOYEE_PASSWORD in env.")
        sys.exit(1)

    auth_url = get_auth_url("dev")
    logger.info(f"Authenticating user {username} to {auth_url}")

    try:
        token = authenticate_employee(
            auth_url=auth_url,
            username=username,
            password=password,
            tenant_code=tenant_code,
        )
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)

    if not token:
        logger.error("Authentication failed (no token).")
        sys.exit(1)

    session = create_session_with_token(token=token, tenant_code=tenant_code)
    logger.info("Authentication successful.")

    run_orchestration(config, session, tenant_code)


if __name__ == "__main__":
    main()
