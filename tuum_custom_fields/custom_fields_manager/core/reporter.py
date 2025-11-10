"""
Report generation.
"""

import json
import logging
import datetime
from typing import List

from custom_fields_manager.models.field_models import ChangeRecord

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates documentation reports"""

    def __init__(self, change_history: List[ChangeRecord]):
        self.change_history = change_history

    def generate_json_report(self, output_file: str = "custom_fields_report.json"):
        """Generates detailed JSON report"""
        field_sets = [c for c in self.change_history if c.resource_type == "FIELD_SET"]
        fields = [c for c in self.change_history if c.resource_type == "FIELD"]

        report = {
            "report_metadata": {
                "generated_at": datetime.datetime.now().isoformat(),
                "total_operations": len(self.change_history),
                "successful": sum(1 for c in self.change_history if c.status == "SUCCESS"),
                "failed": sum(1 for c in self.change_history if c.status == "FAILED")
            },
            "summary": {
                "field_sets": {
                    "total": len(field_sets),
                    "successful": sum(1 for fs in field_sets if fs.status == "SUCCESS"),
                    "failed": sum(1 for fs in field_sets if fs.status == "FAILED")
                },
                "fields": {
                    "total": len(fields),
                    "successful": sum(1 for f in fields if f.status == "SUCCESS"),
                    "failed": sum(1 for f in fields if f.status == "FAILED")
                }
            },
            "field_sets_created": [
                {
                    "field_set_id": fs.resource_id,
                    "name": fs.resource_name,
                    "entity": fs.entity_name,
                    "api_module": fs.api_module,
                    "status": fs.status,
                    "timestamp": fs.timestamp,
                    "response": fs.response_data,
                    "error": fs.error_message
                }
                for fs in field_sets
            ],
            "fields_created": [
                {
                    "field_id": f.resource_id,
                    "name": f.resource_name,
                    "entity": f.entity_name,
                    "api_module": f.api_module,
                    "status": f.status,
                    "timestamp": f.timestamp,
                    "response": f.response_data,
                    "error": f.error_message
                }
                for f in fields
            ],
            "operations_by_module": {},
            "full_change_history": [c.to_dict() for c in self.change_history]
        }

        # Aggregate by module
        for change in self.change_history:
            module = change.api_module
            if module not in report["operations_by_module"]:
                report["operations_by_module"][module] = {
                    "total": 0,
                    "field_sets": 0,
                    "fields": 0,
                    "successful": 0,
                    "failed": 0
                }

            report["operations_by_module"][module]["total"] += 1
            if change.resource_type == "FIELD_SET":
                report["operations_by_module"][module]["field_sets"] += 1
            else:
                report["operations_by_module"][module]["fields"] += 1

            if change.status == "SUCCESS":
                report["operations_by_module"][module]["successful"] += 1
            else:
                report["operations_by_module"][module]["failed"] += 1

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"\n{'=' * 70}")
        logger.info(f"JSON Report: {output_file}")
        logger.info(f"Total: {report['report_metadata']['total_operations']}")
        logger.info(f"  Field sets: {report['summary']['field_sets']['total']}")
        logger.info(f"  Fields: {report['summary']['fields']['total']}")
        logger.info(f"Successful: {report['report_metadata']['successful']}")
        logger.info(f"Failed: {report['report_metadata']['failed']}")
        logger.info(f"{'=' * 70}")

        return report

    def generate_markdown_summary(self, output_file: str = "CUSTOM_FIELDS_SUMMARY.md"):
        """Generates human-readable Markdown summary"""
        field_sets = [c for c in self.change_history if c.resource_type == "FIELD_SET"]
        fields = [c for c in self.change_history if c.resource_type == "FIELD"]

        successful_fs = [fs for fs in field_sets if fs.status == "SUCCESS"]
        successful_f = [f for f in fields if f.status == "SUCCESS"]
        failed = [c for c in self.change_history if c.status == "FAILED"]

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Custom Fields Configuration Summary\n\n")
            f.write(f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## Summary\n\n")
            f.write(f"- **Total Operations:** {len(self.change_history)}\n")
            f.write(f"- **Field Sets:** {len(successful_fs)} created\n")
            f.write(f"- **Fields:** {len(successful_f)} created\n")
            f.write(f"- **Failed:** {len(failed)}\n\n")

            if successful_fs:
                f.write("## Field Sets Created\n\n")
                for fs in successful_fs:
                    f.write(f"### {fs.resource_name}\n\n")
                    f.write(f"- **ID:** `{fs.resource_id}`\n")
                    f.write(f"- **Entity:** {fs.entity_name}\n")
                    f.write(f"- **API:** {fs.api_module}\n\n")

            if successful_f:
                f.write("## Fields Created\n\n")
                by_fs = {}
                for field in successful_f:
                    fs_id = "Unknown"
                    if field.response_data:
                        fs_id = field.response_data.get("data", {}).get("fieldSetId", "Unknown")
                    if fs_id not in by_fs:
                        by_fs[fs_id] = []
                    by_fs[fs_id].append(field)

                for fs_id, field_list in by_fs.items():
                    f.write(f"### Field Set: `{fs_id}`\n\n")
                    for field in field_list:
                        f.write(f"- **{field.resource_name}** (`{field.resource_id}`)\n")
                    f.write("\n")

            if failed:
                f.write("## Failed Operations\n\n")
                for change in failed:
                    f.write(f"### {change.resource_type}: {change.resource_name}\n\n")
                    f.write(f"- **ID:** `{change.resource_id}`\n")
                    f.write(f"- **Error:** {change.error_message}\n\n")

        logger.info(f"Markdown summary: {output_file}")
