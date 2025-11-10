"""
Interactive CLI.
"""

import json
from typing import Dict, Optional

from custom_fields_manager.config.entities import ENTITY_REGISTRY


class InteractiveBuilder:
    """Interactive CLI - no JSON writing needed"""

    def __init__(self):
        self.field_sets = []
        self.fields = []

    def print_header(self, text: str):
        print("\n" + "=" * 70)
        print(text)
        print("=" * 70)

    def choose_api_module(self) -> str:
        self.print_header("SELECT API MODULE")
        modules = list(ENTITY_REGISTRY.keys())
        for i, module in enumerate(modules, 1):
            print(f"{i}. {module}")

        while True:
            choice = input("\nEnter module number: ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(modules):
                    return modules[idx]
            except ValueError:
                pass
            print("Invalid. Try again.")

    def choose_entity(self, api_module: str) -> str:
        self.print_header(f"SELECT ENTITY FOR {api_module}")
        entities = ENTITY_REGISTRY[api_module]["entities"]
        for i, entity in enumerate(entities, 1):
            print(f"{i}. {entity}")

        while True:
            choice = input("\nEnter entity number: ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(entities):
                    return entities[idx]
            except ValueError:
                pass
            print("Invalid. Try again.")

    def build_field_set(self):
        self.print_header("CREATE FIELD SET")

        api_module = self.choose_api_module()
        entity_name = self.choose_entity(api_module)

        print(f"\nAPI Module: {api_module}")
        print(f"Entity: {entity_name}")

        field_set_id = input("\nField Set ID (e.g., employment_history): ").strip()
        name = input("Field Set Name (e.g., Employment History): ").strip()

        field_set = {
            "api_module": api_module,
            "entity_name": entity_name,
            "field_set_id": field_set_id,
            "name": name
        }

        self.field_sets.append(field_set)
        print(f"\n✓ Field set '{name}' added!")
        return field_set

    def build_field(self, field_set: Optional[Dict] = None):
        self.print_header("CREATE FIELD")

        if not field_set and not self.field_sets:
            print("No field sets yet. Creating one...")
            field_set = self.build_field_set()

        if not field_set:
            print("\nAvailable field sets:")
            for i, fs in enumerate(self.field_sets, 1):
                print(f"{i}. {fs['name']} ({fs['field_set_id']})")

            while True:
                choice = input("\nEnter field set number: ").strip()
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(self.field_sets):
                        field_set = self.field_sets[idx]
                        break
                except ValueError:
                    pass
                print("Invalid. Try again.")

        print(f"\nAdding to: {field_set['name']}")

        field_id = input("\nField ID (e.g., job_title): ").strip()
        name = input("Field Name (e.g., JOB TITLE): ").strip()

        print("\nValue Types:")
        value_types = ["TEXT", "NUMBER", "DATE", "DATETIME", "BOOLEAN", "JSON"]
        for i, vt in enumerate(value_types, 1):
            print(f"{i}. {vt}")

        while True:
            choice = input("Enter type number: ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(value_types):
                    value_type = value_types[idx]
                    break
            except ValueError:
                pass
            print("Invalid. Try again.")

        required = input("Required? (y/n): ").strip().lower() == 'y'
        unique = input("Unique? (y/n): ").strip().lower() == 'y'

        field = {
            "api_module": field_set["api_module"],
            "entity_name": field_set["entity_name"],
            "field_set_id": field_set["field_set_id"],
            "field_id": field_id,
            "name": name,
            "value_type": value_type,
            "required": required,
            "unique": unique
        }

        self.fields.append(field)
        print(f"\n✓ Field '{name}' added!")
        return field

    def run(self) -> Dict:
        self.print_header("CUSTOM FIELDS BUILDER")
        print("Build custom fields without writing JSON!")

        field_set = self.build_field_set()

        while True:
            add = input("\nAdd field to this field set? (y/n): ").strip().lower()
            if add != 'y':
                break
            self.build_field(field_set)

        while True:
            more = input("\nCreate another field set? (y/n): ").strip().lower()
            if more != 'y':
                break

            field_set = self.build_field_set()

            while True:
                add = input("\nAdd field to this field set? (y/n): ").strip().lower()
                if add != 'y':
                    break
                self.build_field(field_set)

        config = {
            "field_sets": self.field_sets,
            "fields": self.fields
        }

        config_file = "custom_fields_config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        self.print_header("CONFIGURATION SAVED")
        print(f"File: {config_file}")
        print(f"Field sets: {len(self.field_sets)}")
        print(f"Fields: {len(self.fields)}")

        return config
