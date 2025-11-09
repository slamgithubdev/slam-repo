# domain_dataclass/contracts_dataclass.py

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Component:
    """
    Component (PRI, INT, ALIM, etc.) for Tuum contract.
    Matches Tuum API component schema.
    """

    componentTypeCode: str
    balanceMoney: dict
    invoicedBalanceMoney: dict
    paymentInterval: Optional[int] = None
    calculationMethod: Optional[dict] = None
    rateTypeCode: Optional[str] = None
    rate: Optional[float] = None
    rateBaseCode: Optional[str] = None
    marginRate: Optional[int] = None
    baseRate: Optional[int] = None


@dataclass
class Repayment:
    """
    Repayment configuration for Tuum contract.
    Matches Tuum API repayment schema.
    """

    monthlyRepaymentAmount: dict
    paymentDay: int
    previousInvoiceDate: Optional[str] = None
    monthlyRepaymentRate: Optional[float] = None
    paymentFreeMonths: Optional[int] = None
    maxInvoiceMoney: Optional[dict] = None
    minInvoiceMoney: Optional[dict] = None
    invoiceDay: Optional[int] = None


@dataclass
class Contract:
    """
    Tuum Contract dataclass matching success_1.json schema.
    All required fields for Tuum contract import API.
    """

    # Required identifiers
    externalPersonId: str
    externalContractId: str
    contractNumber: str

    # Source information
    source: dict  # {"sourceName": "...", "sourceRef": "..."}

    # Loan configuration
    loanTypeCode: str
    statusCode: str
    scheduleTypeCode: str

    # Dates
    preparationDate: str
    signingDate: str
    startDate: str
    activationDate: str
    endDate: str

    # Financial details
    period: int
    apr: float
    limitMoney: dict  # {"amount": float, "currencyCode": "GBP"}
    contractMoney: dict  # {"amount": float, "currencyCode": "GBP"}

    # Location and tenant
    countryCode: str
    tenantCode: str

    # Repayment configuration
    repayment: Repayment
    repaymentChannelCode: str

    # Components and schedule
    components: List[Component]
    scheduleLines: List[Dict[str, Any]] = field(default_factory=list)
