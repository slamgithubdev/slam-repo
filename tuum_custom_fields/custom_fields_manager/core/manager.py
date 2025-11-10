"""
Custom fields manager - CORRECTED.
"""

import datetime
import json
import logging
from typing import Dict, List, Optional

import requests

from custom_fields_manager.models.field_models import (
    ChangeRecord,
    FieldDefinition,
    FieldSetDefinition,
)

logger = logging.getLogger(__name__)


class CustomFieldsManager:
    """Manages custom field sets and fields"""

    def __init__(
        self, session: requests.Session, tenant_code: str, environment: str = "dev"
    ):
        """
        Initialize manager.

        Args:
            session: Authenticated session with x-auth-token set
            tenant_code: Tenant code (e.g., "BF")
            environment: Environment name (default: "dev")
        """
        self.session = session
        self.tenant_code = tenant_code
        self.environment = environment
        self.change_history: List[ChangeRecord] = []

        logger.info(
            f"Manager initialized (environment: {environment}, tenant: {tenant_code})"
        )

    def _record_change(
        self,
        operation: str,
        resource_type: str,
        api_module,
        entity_name: str,
        resource_id: str,
        resource_name: str,
        status: str,
        response_data: Optional[Dict] = None,
        error_message: Optional[str] = None,
    ):
        """Records a change"""
        record = ChangeRecord(
            timestamp=datetime.datetime.now().isoformat(),
            operation=operation,
            resource_type=resource_type,
            api_module=api_module.name,
            entity_name=entity_name,
            resource_id=resource_id,
            resource_name=resource_name,
            status=status,
            response_data=response_data,
            error_message=error_message,
        )
        self.change_history.append(record)

        icon = "✓" if status == "SUCCESS" else "✗"
        logger.info(
            f"{icon} {operation} {resource_type}: {resource_name} "
            f"({resource_id}) on {entity_name}"
        )
        if error_message:
            logger.error(f"   Error: {error_message}")

    def create_field_set(self, definition: FieldSetDefinition) -> Optional[Dict]:
        """
        Creates a field set.

        API: POST /api/v1/custom-fields/{entityName}/field-set

        Args:
            definition: Field set definition

        Returns:
            API response if successful
        """
        base_url = definition.api_module.get_url(self.environment)
        endpoint = f"/api/v1/custom-fields/{definition.entity_name}/field-set"
        url = base_url + endpoint

        logger.info(f"Creating field set: {definition.name} on {definition.entity_name}")

        payload = {"name": definition.name, "fieldSetId": definition.field_set_id}

        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "x-tenant-code": self.tenant_code,
            "Accept-Language": "en",
        }

        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=10)
            logger.info(f"Response status: {response.status_code}")

            if response.status_code // 100 == 2:
                data = response.json()
                logger.info(f"✓ Field set '{definition.name}' created successfully")
                self._record_change(
                    operation="CREATE",
                    resource_type="FIELD_SET",
                    api_module=definition.api_module,
                    entity_name=definition.entity_name,
                    resource_id=definition.field_set_id,
                    resource_name=definition.name,
                    status="SUCCESS",
                    response_data=data,
                )
                return data
            else:
                error_msg = f"Failed with status {response.status_code}: {response.text}"
                logger.error(f"✗ {error_msg}")
                self._record_change(
                    operation="CREATE",
                    resource_type="FIELD_SET",
                    api_module=definition.api_module,
                    entity_name=definition.entity_name,
                    resource_id=definition.field_set_id,
                    resource_name=definition.name,
                    status="FAILED",
                    error_message=error_msg,
                )
                return None

        except Exception as e:
            error_msg = f"Exception during field set creation: {str(e)}"
            logger.error(f"✗ {error_msg}")
            self._record_change(
                operation="CREATE",
                resource_type="FIELD_SET",
                api_module=definition.api_module,
                entity_name=definition.entity_name,
                resource_id=definition.field_set_id,
                resource_name=definition.name,
                status="ERROR",
                error_message=error_msg,
            )
            raise e

    def create_field(
        self,
        field_set_definition: FieldSetDefinition,
        field_definition: FieldDefinition,
    ) -> Optional[Dict]:
        """
        Create a custom field within a field set.

        API: POST /api/v1/custom-fields/{entityName}/field

        CRITICAL FIX: The field endpoint is DIRECTLY under entity:
           /api/v1/custom-fields/{entityName}/field

        NOT nested under field-set:
           /api/v1/custom-fields/{entityName}/field-set/{fieldSetId}/field  ← WRONG!

        The fieldSetId goes in the REQUEST BODY, not the URL path!

        Args:
            field_set_definition: Parent field set definition
            field_definition: Field definition

        Returns:
            API response data if successful, None otherwise
        """
        base_url = field_set_definition.api_module.get_url(self.environment)

        # CORRECTED: Field endpoint is directly under entity
        endpoint = f"/api/v1/custom-fields/{field_set_definition.entity_name}/field"
        url = base_url + endpoint

        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "x-tenant-code": self.tenant_code,
            "Accept-Language": "en",
        }

        # fieldSetId goes in the PAYLOAD, not the URL!
        payload = {
            "fieldId": field_definition.field_id,
            "name": field_definition.name,
            "fieldSetId": field_set_definition.field_set_id,  # ← In payload!
            "valueType": field_definition.value_type.value,
            "required": field_definition.required,
            "unique": field_definition.unique,
            "active": field_definition.active,
        }

        if field_definition.activity_code:
            payload["activityCode"] = field_definition.activity_code

        logger.info(
            f"Creating field: {field_definition.name} in {field_set_definition.name}"
        )
        logger.debug(f"POST {url}")
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=10)
            logger.info(f"Response status: {response.status_code}")

            if response.status_code // 100 == 2:
                data = response.json()
                logger.info(f"✓ Field '{field_definition.name}' created successfully")
                self._record_change(
                    operation="CREATE",
                    resource_type="FIELD",
                    api_module=field_set_definition.api_module,
                    entity_name=field_set_definition.entity_name,
                    resource_id=field_definition.field_id,
                    resource_name=field_definition.name,
                    status="SUCCESS",
                    response_data=data,
                )
                return data
            else:
                error_msg = (
                    f"Failed with status {response.status_code}: {response.text}"
                )
                logger.error(f"✗ {error_msg}")
                self._record_change(
                    operation="CREATE",
                    resource_type="FIELD",
                    api_module=field_set_definition.api_module,
                    entity_name=field_set_definition.entity_name,
                    resource_id=field_definition.field_id,
                    resource_name=field_definition.name,
                    status="FAILED",
                    error_message=error_msg,
                )
                return None

        except Exception as e:
            error_msg = f"Exception during field creation: {str(e)}"
            logger.error(f"✗ {error_msg}")
            self._record_change(
                operation="CREATE",
                resource_type="FIELD",
                api_module=field_set_definition.api_module,
                entity_name=field_set_definition.entity_name,
                resource_id=field_definition.field_id,
                resource_name=field_definition.name,
                status="ERROR",
                error_message=error_msg,
            )
            raise e
