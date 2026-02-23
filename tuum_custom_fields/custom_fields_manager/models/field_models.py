"""
Data models for custom fields.
"""

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Dict, Any


class ValueType(Enum):
    """Supported custom field value types"""
    NUMBER = "NUMBER"
    TEXT = "TEXT"
    DATE = "DATE"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"
    JSON = "JSON"
    LOOKUP = "LOOKUP"


@dataclass
class FieldSetDefinition:
    """Definition for a field set"""
    entity_name: str
    field_set_id: str
    name: str
    api_module: Any

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "entity_name": self.entity_name,
            "field_set_id": self.field_set_id,
            "name": self.name,
            "api_module": self.api_module.name
        }


@dataclass
class FieldDefinition:
    """Definition for a custom field"""
    entity_name: str
    field_id: str
    name: str
    field_set_id: str
    value_type: ValueType
    unique: bool = False
    required: bool = False
    active: bool = True
    activity_code: Optional[str] = None
    lookup_type_code: Optional[str] = None
    api_module: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "entity_name": self.entity_name,
            "field_id": self.field_id,
            "name": self.name,
            "field_set_id": self.field_set_id,
            "value_type": self.value_type.value,
            "unique": self.unique,
            "required": self.required,
            "active": self.active,
            "activity_code": self.activity_code,
            "lookup_type_code": self.lookup_type_code,
            "api_module": self.api_module.name if self.api_module else None
        }


@dataclass
class ChangeRecord:
    """Records changes made during execution"""
    timestamp: str
    operation: str
    resource_type: str
    api_module: str
    entity_name: str
    resource_id: str
    resource_name: str
    status: str
    response_data: Optional[Dict] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
