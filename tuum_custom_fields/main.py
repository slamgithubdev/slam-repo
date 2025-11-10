#!/usr/bin/env python3
"""
Custom Fields Manager - Main Entry Point

Usage:
    python main.py interactive              # Interactive mode
    python main.py apply <config.json>      # Apply existing config
"""

import json
import logging
import os
import sys

from dotenv import dotenv_values

from custom_fields_manager.config.settings import get_auth_url
from custom_fields_manager.config.entities import ENTITY_REGISTRY
from custom_fields_manager.models.field_models import (
    FieldSetDefinition, FieldDefinition, ValueType
)
from custom_fields_manager.core.auth import authenticate_employee, create_session_with_token
from custom_fields_manager.core.manager import CustomFieldsManager
from custom_fields_manager.core.reporter import ReportGenerator
from custom_fields_manager.cli.interactive import InteractiveBuilder

# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("custom_fields_manager.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def apply_configuration(config: dict, manager: CustomFieldsManager):
    """
    Applies configuration: creates field sets AND fields.
    """

    # PHASE 1: Create field sets
    logger.info("\n" + "=" * 70)
    logger.info("PHASE 1: Creating Field Sets")
    logger.info("=" * 70)

    field_set_map = {}

    for fs_config in config.get("field_sets", []):
        field_set_def = FieldSetDefinition(
            entity_name=fs_config["entity_name"],
            field_set_id=fs_config["field_set_id"],
            name=fs_config["name"],
            api_module=ENTITY_REGISTRY[fs_config["api_module"]]["module"]
        )
        result = manager.create_field_set(field_set_def)
        if result:
            field_set_map[fs_config["field_set_id"]] = field_set_def

    # PHASE 2: Create fields
    logger.info("\n" + "=" * 70)
    logger.info("PHASE 2: Creating Fields")
    logger.info("=" * 70)

    for field_config in config.get("fields", []):
        # Get the field set definition
        field_set_id = field_config["field_set_id"]
        if field_set_id not in field_set_map:
            logger.error(f"Field set '{field_set_id}' not found for field '{field_config['field_id']}'")
            continue

        field_set_def = field_set_map[field_set_id]

        field_def = FieldDefinition(
            entity_name=field_config["entity_name"],
            field_id=field_config["field_id"],
            name=field_config["name"],
            field_set_id=field_config["field_set_id"],
            value_type=ValueType[field_config["value_type"]],
            unique=field_config.get("unique", False),
            required=field_config.get("required", False),
            active=field_config.get("active", True),
            activity_code=field_config.get("activity_code"),
            api_module=ENTITY_REGISTRY[field_config["api_module"]]["module"]
        )
        manager.create_field(field_set_def, field_def)


def main():
    """Main execution"""

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python main.py interactive")
        print("  python main.py apply <config.json>")
        sys.exit(1)

    mode = sys.argv[1].lower()

    logger.info("=" * 70)
    logger.info("TUUM CUSTOM FIELDS MANAGER")
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

    # Initialize manager
    manager = CustomFieldsManager(session, tenant_code, environment="dev")

    # Run mode
    logger.info("\n" + "=" * 70)
    logger.info("INTERACTIVE MODE" if mode == "interactive" else "APPLY MODE")
    logger.info("=" * 70)

    if mode == "interactive":
        builder = InteractiveBuilder()
        config = builder.run()

        apply_now = input("\nApply configuration now? (y/n): ").strip().lower()
        if apply_now == 'y':
            apply_configuration(config, manager)

            # Generate reports
            logger.info("\n" + "=" * 70)
            logger.info("GENERATING REPORTS")
            logger.info("=" * 70)
            reporter = ReportGenerator(manager.change_history)
            reporter.generate_json_report()
            reporter.generate_markdown_summary()
        else:
            print("\nConfig saved: custom_fields_config.json")
            print("Apply later: python main.py apply custom_fields_config.json")

    elif mode == "apply":
        if len(sys.argv) < 3:
            logger.error("Specify file: python main.py apply <config.json>")
            sys.exit(1)

        config_file = sys.argv[2]

        if not os.path.exists(config_file):
            logger.error(f"File not found: {config_file}")
            sys.exit(1)

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        apply_configuration(config, manager)

        # Generate reports
        logger.info("\n" + "=" * 70)
        logger.info("GENERATING REPORTS")
        logger.info("=" * 70)
        reporter = ReportGenerator(manager.change_history)
        reporter.generate_json_report()
        reporter.generate_markdown_summary()

    else:
        print(f"Unknown mode: {mode}")
        print("Use 'interactive' or 'apply'")
        sys.exit(1)

    logger.info("\n" + "=" * 70)
    logger.info("COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
