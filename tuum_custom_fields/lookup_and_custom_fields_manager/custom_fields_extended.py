import logging
from typing import Dict, Optional
import requests
import json

from custom_fields_manager.core.manager import CustomFieldsManager
from custom_fields_manager.models.field_models import FieldSetDefinition, FieldDefinition

logger = logging.getLogger(__name__)

class CustomFieldsExtended(CustomFieldsManager):
    """
    Extends CustomFieldsManager to support updating (upserting) records.
    """

    def create_field_set(self, definition: FieldSetDefinition) -> Optional[Dict]:
        """
        Tries to create a field set. If it exists (409), it tries to update it.
        """
        # Call the original create method
        # Implementation note: The original method returns None on failure but logs it.
        # We need to hack it slightly: we can't easily intercept the 409 inside the parent method 
        # without copy-pasting the whole logic or making a pre-check.
        # However, checking if it exists first is safer.
        
        # Let's try to fetch it first? No, API might not exist.
        # Let's copy-paste logic slightly modified or just try-catch?
        # The parent method swallows exceptions and returns None on error. 
        # But it returns the JSON response on success.
        
        # Option: Just implement the UPSERT logic fresh here to avoid fighting the parent's error logging.
        # But we want to reuse code. 
        
        # Let's try to just run the update if we think it exists?
        # Better: Let's reimplement create_field_set with upsert logic to be precise.
        
        base_url = definition.api_module.get_url(self.environment)
        endpoint = f"/api/v1/custom-fields/{definition.entity_name}/field-set"
        url = base_url + endpoint

        payload = {"name": definition.name, "fieldSetId": definition.field_set_id}
        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "x-tenant-code": self.tenant_code,
            "Accept-Language": "en",
        }

        try:
            logger.info(f"Upserting field set: {definition.name}")
            response = self.session.post(url, json=payload, headers=headers)
            
            if response.status_code // 100 == 2:
                logger.info(f"✓ Field set '{definition.name}' created.")
                return response.json()
            elif response.status_code == 409:
                logger.info(f"Field set '{definition.name}' exists. Updating...")
                return self.update_field_set(definition)
            else:
                logger.error(f"Failed create with {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error in create_field_set upsert: {e}")
            return None

    def update_field_set(self, definition: FieldSetDefinition) -> Optional[Dict]:
        """
        Updates an existing field set.
        API: PUT /api/v1/custom-fields/{entityName}/field-set/{fieldSetId}
        """
        base_url = definition.api_module.get_url(self.environment)
        endpoint = f"/api/v1/custom-fields/{definition.entity_name}/field-set/{definition.field_set_id}"
        url = base_url + endpoint

        payload = {"name": definition.name} # Only name is updatable usually
        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "x-tenant-code": self.tenant_code,
        }
        
        try:
            response = self.session.put(url, json=payload, headers=headers)
            if response.status_code // 100 == 2:
                logger.info(f"✓ Field set '{definition.name}' updated.")
                return response.json()
            else:
                logger.error(f"Failed update with {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception updating field set: {e}")
            return None

    def create_field(self, field_set_definition: FieldSetDefinition, field_definition: FieldDefinition) -> Optional[Dict]:
        """
        Upserts a field.
        """
        base_url = field_set_definition.api_module.get_url(self.environment)
        endpoint = f"/api/v1/custom-fields/{field_set_definition.entity_name}/field"
        url = base_url + endpoint
        
        payload = {
            "fieldId": field_definition.field_id,
            "name": field_definition.name,
            "fieldSetId": field_set_definition.field_set_id,
            "valueType": field_definition.value_type.value,
            "required": field_definition.required,
            "unique": field_definition.unique,
            "active": field_definition.active,
        }
        if field_definition.activity_code:
            payload["activityCode"] = field_definition.activity_code
        
        if field_definition.lookup_type_code:
            payload["lookupTypeCode"] = field_definition.lookup_type_code

        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "x-tenant-code": self.tenant_code,
        }

        try:
            logger.info(f"Upserting field: {field_definition.name}")
            response = self.session.post(url, json=payload, headers=headers)
            
            if response.status_code // 100 == 2:
                logger.info(f"✓ Field '{field_definition.name}' created.")
                return response.json()
            elif response.status_code == 409:
                logger.info(f"Field '{field_definition.name}' exists. Updating...")
                return self.update_field(field_set_definition, field_definition)
            else:
                logger.error(f"Failed create with {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error in create_field upsert: {e}")
            return None

    def update_field(self, field_set_definition: FieldSetDefinition, field_definition: FieldDefinition) -> Optional[Dict]:
        """
        Updates an existing field.
        API: PUT /api/v1/custom-fields/{entityName}/field/{fieldId}
        """
        base_url = field_set_definition.api_module.get_url(self.environment)
        endpoint = f"/api/v1/custom-fields/{field_set_definition.entity_name}/field/{field_definition.field_id}"
        url = base_url + endpoint

        # Payload for update typically includes editable fields
        payload = {
            "name": field_definition.name,
            "required": field_definition.required,
            "active": field_definition.active
            # Note: valueType, unique, fieldSetId usually cannot be changed after creation
        }
        
        headers = {
            "Content-Type": "application/json",
            "accept": "application/json",
            "x-tenant-code": self.tenant_code,
        }
        
        try:
            response = self.session.put(url, json=payload, headers=headers)
            if response.status_code // 100 == 2:
                logger.info(f"✓ Field '{field_definition.name}' updated.")
                return response.json()
            else:
                logger.error(f"Failed update with {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception updating field: {e}")
            return None
