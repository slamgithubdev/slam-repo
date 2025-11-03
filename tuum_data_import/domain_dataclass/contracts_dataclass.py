# domain_dataclass/contracts_dataclass.py

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Component:
    componentTypeCode: str
    paymentInterval: Optional[int] = None
    balanceMoney: dict = field(default_factory=dict)
    invoicedBalanceMoney: dict = field(default_factory=dict)
    calculationMethod: Optional[dict] = None
    rateTypeCode: Optional[str] = None
    rate: Optional[float] = None
    rateBaseCode: Optional[str] = None
    marginRate: Optional[int] = None
    baseRate: Optional[int] = None
    debts: Optional[List[Dict[str, Any]]] = None  # NEW: Debt tracking


@dataclass
class Repayment:
    paymentFreeMonths: Optional[int]
    monthlyRepaymentAmount: dict
    monthlyRepaymentRate: Optional[float]
    maxInvoiceMoney: Optional[float]
    minInvoiceMoney: Optional[float]
    invoiceDay: Optional[int]
    paymentDay: int
    previousInvoiceDate: str


@dataclass
class Contract:
    externalPersonId: str
    tuumPersonId: Optional[str]
    externalContractId: str
    source: dict
    contractNumber: str
    loanTypeCode: str
    referenceNumber: Optional[str]
    preparationDate: str
    signingDate: str
    startDate: str
    activationDate: str
    endDate: str
    stopDate: Optional[str]
    statusCode: str
    period: int
    apr: Optional[float]
    scheduleTypeCode: str
    limitMoney: dict
    contractFeeMoney: Optional[dict]
    contractMoney: dict
    countryCode: str
    tenantCode: str
    solvencyLevelCode: Optional[str]
    externalServicingAccountId: Optional[str]
    repayment: Repayment
    hasCollateral: bool
    initialLtv: Optional[float]
    currentLtv: Optional[float]
    limitUsageDate: Optional[str]
    penaltyGraceDays: Optional[int]
    penaltyGraceMoney: Optional[float]
    repaymentChannelCode: str
    contractConditions: Optional[str]
    components: List[Component]
    coBorrowers: Optional[List] = None
    scheduleLines: List[dict] = field(default_factory=list)
    customFields: Optional[dict] = None
