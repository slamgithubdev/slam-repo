import json
import os
import sys
from typing import Dict, List, Optional

# Add sibling directory to path to import from tuum_custom_fields
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
# 'tuum_custom_fields' packages are in the parent directory now (since we are inside it)
sys.path.append(parent_dir)

try:
    from custom_fields_manager.cli.interactive import InteractiveBuilder
except ImportError:
    # Fallback if sibling not found or structure differs
    print("Warning: Could not import InteractiveBuilder from sibling. Field creation might be limited.")
    InteractiveBuilder = object

class ExtendedInteractiveBuilder(InteractiveBuilder):
    """
    Extends the sibling InteractiveBuilder to adding support for LOOKUP value types.
    """
    def __init__(self):
        super().__init__()
        self.available_lookups = []

    def build_field(self, field_set: Optional[Dict] = None):
        # Override to add LOOKUP support
        self.print_header("CREATE FIELD (EXTENDED)")

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
        # Added LOOKUP here
        value_types = ["TEXT", "NUMBER", "DATE", "DATETIME", "BOOLEAN", "JSON", "LOOKUP"]
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

        # Prompt for lookup code if type is LOOKUP
        lookup_type_code = None
        if value_type == "LOOKUP":
            print("\nNOTE: Ensure the Lookup Type exists (create it in step 1 if needed).")
            if self.available_lookups:
                print("Available Lookups (Created in Step 1):")
                for lk in self.available_lookups:
                    print(f" - {lk['lookup_type_code']} ({lk['entity_name']})")
                    
            lookup_type_code = input("Enter Lookup Type Code (e.g. TITLE): ").strip().upper()

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
        
        if lookup_type_code:
            field["lookup_type_code"] = lookup_type_code
            # Also add to payload key just in case main.py uses it raw, 
            # though CustomFieldsExtended uses "lookup_type_code" from model.

        self.fields.append(field)
        print(f"\n✓ Field '{name}' added!")
        return field

class UnifiedInteractiveBuilder:
    """
    Builds both Lookups and Custom Fields configurations interactivity.
    """
    def __init__(self):
        self.lookups = []
        # Use our Extended builder
        self.field_builder = ExtendedInteractiveBuilder() if InteractiveBuilder != object else None
        
    def print_header(self, text: str):
        print("\n" + "=" * 70)
        print(text)
        print("=" * 70)

    def build_lookup(self):
        self.print_header("CREATE LOOKUP TYPE")
        
        entity_name = input("Entity Name (e.g. person, account): ").strip()
        code = input("Lookup Type Code (e.g. TITLE, REASON): ").strip().upper()
        description = input("Description: ").strip()
        
        values = []
        print("\nAdding Lookup Values (Enter empty code to finish)")
        while True:
            val_code = input("\nValue Code (e.g. 1, MR): ").strip()
            if not val_code:
                break
            val_label = input(f"Label for '{val_code}': ").strip()
            values.append({"code": val_code, "label": val_label})
            
        lookup = {
            "entity_name": entity_name,
            "lookup_type_code": code,
            "description": description,
            "values": values
        }
        self.lookups.append(lookup)
        print(f"\n✓ Lookup '{code}' added!")
        return lookup

    def run(self) -> Dict:
        self.print_header("UNIFIED MIGRATION BUILDER")
        print("Build Lookups and Custom Fields configurations.")
        
        # 1. Build Lookups
        while True:
            add = input("\nCreate a Lookup Type? (y/n): ").strip().lower()
            if add != 'y':
                break
            self.build_lookup()
            
        # 2. Build Fields
        field_config = {"field_sets": [], "fields": []}
        if self.field_builder:
            print("\n" + "-" * 50)
            print("Switching to Custom Field Builder...")
            # We interact directly with the existing builder's methods
            # Mimic its run loop but without saving immediately
            
            # PASS LOOKUPS TO FIELD BUILDER
            self.field_builder.available_lookups = self.lookups
            
            while True:
                add = input("\nCreate a Field Set? (y/n): ").strip().lower()
                if add != 'y':
                    break
                
                field_set = self.field_builder.build_field_set()
                
                while True:
                    add_f = input("\nAdd field to this field set? (y/n): ").strip().lower()
                    if add_f != 'y':
                        break
                    self.field_builder.build_field(field_set)
            
            field_config["field_sets"] = self.field_builder.field_sets
            field_config["fields"] = self.field_builder.fields
        
        # 3. Combine
        full_config = {
            "lookups": self.lookups,
            "custom_fields": []
        }
        
        # Transform flat field lists into the structure main.py expects if needed
        # main.py expects a list of objects, each possibly containing "field_set" and "fields".
        # We need to group fields by field_set
        
        grouped_fields = {} # field_set_id -> list of fields
        for f in field_config["fields"]:
            fs_id = f["field_set_id"]
            if fs_id not in grouped_fields:
                grouped_fields[fs_id] = []
            grouped_fields[fs_id].append(f)
            
        for fs in field_config["field_sets"]:
            fs_id = fs["field_set_id"]
            entry = {
                "field_set": fs,
                "fields": grouped_fields.get(fs_id, [])
            }
            full_config["custom_fields"].append(entry)

        # Save
        config_file = os.path.join(current_dir, "config.json")
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(full_config, f, indent=2)

        self.print_header("CONFIGURATION SAVED")
        print(f"File: {config_file}")
        print(f"Lookups: {len(self.lookups)}")
        print(f"Field Sets: {len(full_config['custom_fields'])}")
        
        return full_config
