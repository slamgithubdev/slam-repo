# domain_reports/contracts_reports.py

import csv
import json
import logging
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)


class ContractReportGenerator:
    """Generates multi-format reports for contract processing"""

    def __init__(self, contracts_with_strategy, output_dir="./reports"):
        self.contracts_with_strategy = contracts_with_strategy
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_strategy_report(self):
        """
        Generate strategy usage report in TXT and JSON formats.

        Returns: (txt_filepath, json_filepath)
        """
        # Aggregate strategy statistics
        strategy_counts = {}
        contract_details = []

        for contract, strategy_obj in self.contracts_with_strategy:
            # Handle None strategy_obj gracefully
            if strategy_obj is None:
                strategy_name = "No Strategy"
                reason = "No strategies applicable"
                adjustment_amount = 0.0
                details = {}
            else:
                strategy_name = strategy_obj.strategy_name or "No Strategy"
                reason = strategy_obj.reason or ""
                adjustment_amount = (
                    float(strategy_obj.adjustment_amount)
                    if strategy_obj.adjustment_amount
                    else 0.0
                )
                details = strategy_obj.details or {}

            strategy_counts[strategy_name] = strategy_counts.get(strategy_name, 0) + 1

            contract_details.append(
                {
                    "external_contract_id": contract.externalContractId,
                    "external_person_id": contract.externalPersonId,
                    "principal": contract.limitMoney.get("amount", 0),
                    "strategy_used": strategy_name,
                    "reason": reason,
                    "adjustment_amount": adjustment_amount,
                    "details": details,
                }
            )

        total_contracts = len(self.contracts_with_strategy)

        # Generate TXT report
        txt_filepath = self.output_dir / "strategy_report.txt"
        with open(txt_filepath, "w", encoding="utf-8") as f:
            f.write(
                "═══════════════════════════════════════════════════════════════════\n"
            )
            f.write(
                f"STRATEGY USAGE REPORT - Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            )
            f.write(
                "═══════════════════════════════════════════════════════════════════\n\n"
            )

            f.write("SUMMARY:\n")
            f.write(f"  Total Contracts Processed: {total_contracts}\n\n")

            # Sort by strategy name, with "No Strategy" at the end
            sorted_strategies = sorted(
                strategy_counts.items(), key=lambda x: (x[0] == "No Strategy", x[0])
            )

            for strategy_name, count in sorted_strategies:
                percentage = (
                    (count / total_contracts * 100) if total_contracts > 0 else 0
                )
                f.write(f"  {strategy_name}: {count} contracts ({percentage:.1f}%)\n")

            f.write(
                "\n───────────────────────────────────────────────────────────────────\n"
            )
            f.write("CONTRACT-LEVEL DETAILS:\n")
            f.write(
                "───────────────────────────────────────────────────────────────────\n\n"
            )

            for detail in contract_details:
                f.write(f"Contract: {detail['external_contract_id']}\n")
                f.write(f"  Person ID: {detail['external_person_id']}\n")
                f.write(f"  Principal: £{detail['principal']:.2f}\n")
                f.write(f"  Strategy: {detail['strategy_used']}\n")
                f.write(f"  Reason: {detail['reason']}\n")
                if detail["adjustment_amount"] != 0:
                    f.write(f"  Adjustment: £{detail['adjustment_amount']:.2f}\n")
                f.write("\n")

        logger.info(f"✓ Strategy report (TXT): {txt_filepath}")

        # Generate JSON report
        json_filepath = self.output_dir / "strategy_report.json"
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "report_generated_at": datetime.now().isoformat() + "Z",
                    "total_contracts_processed": total_contracts,
                    "strategy_summary": {
                        name: {
                            "count": count,
                            "percentage": round(
                                count / total_contracts * 100
                                if total_contracts > 0
                                else 0,
                                1,
                            ),
                        }
                        for name, count in sorted(
                            strategy_counts.items(),
                            key=lambda x: (x[0] == "No Strategy", x[0]),
                        )
                    },
                    "contracts": contract_details,
                },
                f,
                indent=2,
            )

        logger.info(f"✓ Strategy report (JSON): {json_filepath}")

        return txt_filepath, json_filepath

    def generate_payment_reconciliation_report(self):
        """
        Generate payment reconciliation report in CSV format.

        Returns: csv_filepath
        """
        csv_filepath = self.output_dir / "payment_reconciliation_report.csv"

        rows = []
        for contract, strategy_obj in self.contracts_with_strategy:
            debts_by_component = (
                contract.customFields.get("debts_by_component", {})
                if contract.customFields
                else {}
            )

            for schedule_line in contract.scheduleLines:
                payment_date = schedule_line.get("paymentDate", "")
                component_type = schedule_line.get("componentTypeCode", "")
                scheduled_amount = schedule_line.get("paymentMoney", {}).get(
                    "amount", 0
                )
                processed = schedule_line.get("processed", False)

                # Get debt info for this component
                debt_info = debts_by_component.get(component_type, [])
                total_debt = sum(
                    d.get("debtMoney", {}).get("amount", 0) for d in debt_info
                )

                # Handle None strategy_obj
                strategy_name = (
                    strategy_obj.strategy_name
                    if strategy_obj and strategy_obj.strategy_name
                    else "No Strategy"
                )

                rows.append(
                    {
                        "contract_id": contract.externalContractId,
                        "person_id": contract.externalPersonId,
                        "payment_date": payment_date,
                        "component": component_type,
                        "scheduled_amount": f"{scheduled_amount:.2f}",
                        "debt_before": f"{total_debt:.2f}",
                        "debt_after": f"{total_debt:.2f}",
                        "processed_status": "true" if processed else "false",
                        "strategy_used": strategy_name,
                    }
                )

        with open(csv_filepath, "w", newline="", encoding="utf-8") as f:
            if rows:
                fieldnames = rows[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        logger.info(f"✓ Payment reconciliation report (CSV): {csv_filepath}")

        return csv_filepath
