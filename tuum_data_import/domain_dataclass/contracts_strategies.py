# domain_dataclass/contracts_strategies.py

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ScheduleStrategy:
    """Encapsulates payment schedule adjustment strategy metadata"""

    strategy_name: str
    reason: str
    original_pri_total: Decimal
    expected_principal: Decimal
    adjustment_amount: Decimal
    payments_modified: int
    details: Dict = field(default_factory=dict)

    def to_dict(self):
        """Convert to JSON-serializable dict"""
        return {
            "strategy_name": self.strategy_name,
            "reason": self.reason,
            "original_pri_total": float(self.original_pri_total),
            "expected_principal": float(self.expected_principal),
            "adjustment_amount": float(self.adjustment_amount),
            "payments_modified": self.payments_modified,
            "details": self.details,
        }


class ScheduleStrategyEngine:
    """Orchestrates payment schedule generation with pluggable strategies"""

    def __init__(
        self,
        cashflow_json,
        interest_json,
        expected_principal,
        start_date,
        term,
        agreement_ref,
        currency="GBP",
    ):
        self.cashflow_json = cashflow_json
        self.interest_json = interest_json
        self.expected_principal = Decimal(str(expected_principal))
        self.start_date = start_date
        self.term = term
        self.agreement_ref = agreement_ref
        self.currency = currency
        self.schedule_lines = []
        self.strategy_used = None

    def safe_amount(self, value):
        """Convert Decimal/float to 2dp float"""
        return round(float(value), 2)

    def generate(self):
        """
        Main orchestrator that delegates to generate_schedule_lines.
        Returns: (schedule_lines, actual_pri_total, strategy_info_dict, actual_end_date)
        """
        from domain_mapper.contracts_mapper import generate_schedule_lines

        schedule_lines, actual_pri, strategy_dict, actual_end = generate_schedule_lines(
            cashflow_json=self.cashflow_json,
            interest_json=self.interest_json,
            expected_principal=self.expected_principal,
            start_date=self.start_date,
            term=self.term,
            agreement_ref=self.agreement_ref,
            currency=self.currency,
        )

        # Convert strategy dict to ScheduleStrategy object
        self.strategy_used = ScheduleStrategy(
            strategy_name=strategy_dict.get("strategy_used", "None"),
            reason=strategy_dict.get("reason", ""),
            original_pri_total=Decimal(
                str(strategy_dict.get("original_pri_total", "0"))
            ),
            expected_principal=Decimal(
                str(strategy_dict.get("expected_principal", "0"))
            ),
            adjustment_amount=Decimal(str(strategy_dict.get("adjustment_amount", "0"))),
            payments_modified=strategy_dict.get("payments_modified", 0),
            details=strategy_dict.get("details", {}),
        )

        self.schedule_lines = schedule_lines
        return schedule_lines, actual_pri, self.strategy_used, actual_end
