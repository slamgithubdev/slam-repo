# Unified Lookup and Custom Fields Manager

This tool allows you to create Lookups and Custom Fields in a single orchestrated run, ensuring that Lookups exist before Custom Fields try to reference them.

## Structure

- `main.py`: The entry point script.
- `lookup_manager.py`: Handles creation of Lookup Types.
- `config.json`: Configuration file defining what Lookups and Fields to create.

## Setup

1.  Ensure you have the `.env.shared` and `.env.secret` files in the parent `tuum_lookups` directory, or copy them here.
2.  Ensure `tuum_lookups` and `tuum_custom_fields` are present in the parent directory as this tool imports from them.

## Usage

1.  Edit `config.json` to define your Lookups and Custom Fields.
    ```json
    {
      "lookups": [
        {
          "entity_name": "person",
          "lookup_type_code": "TITLE",
          "description": "Person Title",
          "values": [{"code": "1", "label": "MR"}]
        }
      ],
      "custom_fields": [ ... ]
    }
    ```
2.  Run the script:
    ```bash
    python main.py
    ```

## Logic
The script first iterates through all defined `lookups` and creates them. Then, it iterates through `custom_fields` and uses the `CustomFieldsManager` to create Field Sets and Fields.
