import logging
import requests
import sys
import os

logger = logging.getLogger(__name__)

class LookupManager:
    def __init__(self, session: requests.Session, env: str = "dev"):
        self.session = session
        # Base URL could be dynamic based on env, currently defaulting to dev as per original script
        self.base_url = "https://lookup-api.billing-finance-dev.tuumplatform.com"

    def create_lookup_type(self, entity_name: str, lookup_type_code: str, config_payload: dict):
        """
        Creates a lookup type for a specific entity. If it exists, it attempts to update it.
        """
        # Fix: Use correct URL structure (api/v1 + Uppercase Entity)
        url = f"{self.base_url}/api/v1/entity/{entity_name.upper()}/lookup-type/{lookup_type_code}"
        
        logger.info(f"Creating lookup type {lookup_type_code} for entity {entity_name}")
        
        # Fix: Transform payload to match API requirements
        # config_payload: {"description": "...", "values": [{"code": "...", "label": "..."}]}
        
        api_payload = {
            "lookupTypeName": config_payload.get("description", lookup_type_code),
            "lookups": []
        }
        
        for val in config_payload.get("values", []):
            api_payload["lookups"].append({
                "lookupCode": val.get("code"),
                "translations": [
                    {
                        "languageCode": "en",
                        "translation": val.get("label")
                    }
                ]
            })

        try:
            response = self.session.post(url, json=api_payload)
            
            if response.status_code in [200, 201]:
                logger.info(f"Lookup type {lookup_type_code} created successfully")
                return response.json()
            elif response.status_code == 409 or (response.status_code == 400 and "err.lookupTypeExists" in response.text):
                logger.info(f"Lookup type {lookup_type_code} already exists. Skipping update (Update not supported).")
                return {"status": "exists", "message": "Lookup type already exists"}
            else:
                logger.error(f"Failed to create lookup type {lookup_type_code}. Status: {response.status_code}, URL: {url}, Response: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception while creating lookup type {lookup_type_code}: {e}")
            return None

    def update_lookup_type(self, entity_name: str, lookup_type_code: str, api_payload: dict):
        """
        Updates an existing lookup type.
        Currently disabled as API does not support standard PUT/PATCH for this resource.
        """
        logger.warning(f"Update requested for {lookup_type_code}, but updates are not currently supported by API discovery.")
        return {"status": "skipped", "reason": "Update not supported"}
