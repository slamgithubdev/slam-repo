# domain_mapper/contracts_mapper.py

import csv
import json
import logging
from datetime import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from domain_config.contracts_config import (
    COUNTRY_CODE,
    IMPORT_DATE,
    LOAN_TYPE_CODE,
    REPAYMENT_CHANNEL_CODE,
    TENANT_CODE,
)
from domain_dataclass.contracts_dataclass import Component, Contract, Repayment

logger = logging.getLogger(__name__)


def safe_amount(value):
    """Convert Decimal/float to 2dp float for JSON serialization"""
    if value is None:
        return 0.0
    return round(float(value), 2)


def parse_transaction_history(transaction_history_json):
    """Parse MaskedTransactionHistory JSON"""
    try:
        transactions = json.loads(transaction_history_json or "[]")
        if not isinstance(transactions, list):
            transactions = [transactions]
        return transactions
    except Exception as e:
        logger.error(f"Error parsing MaskedTransactionHistory: {e}")
        return []


def group_transactions_by_posting_date(transactions, agreement_ref):
    """
    Group transactions by postingDate and calculate net payment per date.

    Returns: {postingDate: {'net': Decimal, 'transactions': [...]}}
    """
    grouped = {}

    for tx in transactions:
        if tx.get("AGREEMENT_REF") != agreement_ref:
            continue

        posting_date = tx.get("postingDate", "")[:10]  # YYYY-MM-DD
        if not posting_date:
            continue

        try:
            amount_obj = tx.get("amount", {})
            if isinstance(amount_obj, dict):
                amount = Decimal(str(amount_obj.get("amount", 0)))
            else:
                amount = Decimal(str(amount_obj))
        except Exception as e:
            logger.warning(f"Error parsing transaction amount: {e}")
            continue

        if posting_date not in grouped:
            grouped[posting_date] = {
                "net": Decimal("0"),
                "transactions": [],
                "posting_date": posting_date,
            }

        grouped[posting_date]["transactions"].append(
            {
                "amount": amount,
                "details": tx.get("details", ""),
                "type": tx.get("transactionTypeCode", ""),
                "value_date": tx.get("valueDate", ""),
            }
        )

        grouped[posting_date]["net"] += amount

    return grouped


def process_schedule_with_transactions(
    schedule_lines,
    monthly_repayment_amount,
    transaction_groups,
    agreement_ref,
):
    """
    Process schedule lines against transaction history.

    NEW LOGIC: Group by payment date FIRST, then allocate across components.
    """
    debt_balance_by_component = {}
    debt_by_line_by_component = {}

    logger.info(f"\n{'=' * 70}")
    logger.info(f"Processing Schedule Lines with Transaction History")
    logger.info(f"Agreement: {agreement_ref}")
    logger.info(f"{'=' * 70}")

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1: Group schedule lines by payment date
    # ═══════════════════════════════════════════════════════════════════════

    schedule_by_date = {}
    for line in schedule_lines:
        pay_date = line["paymentDate"]
        if pay_date not in schedule_by_date:
            schedule_by_date[pay_date] = []
        schedule_by_date[pay_date].append(line)

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2: Process each payment date (NOT each line individually)
    # ═══════════════════════════════════════════════════════════════════════

    for pay_date in sorted(schedule_by_date.keys()):
        lines_for_date = schedule_by_date[pay_date]

        try:
            payment_date_obj = datetime.strptime(pay_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid payment date: {pay_date}")
            for line in lines_for_date:
                line["processed"] = False
            continue

        # Skip future payments
        if payment_date_obj > IMPORT_DATE:
            for line in lines_for_date:
                line["processed"] = False
            logger.debug(f"  {pay_date}: Future payment")
            continue

        # Initialize debt tracking for components on this date
        for line in lines_for_date:
            comp_type = line["componentTypeCode"]
            if comp_type not in debt_balance_by_component:
                debt_balance_by_component[comp_type] = {
                    "amount": Decimal("0"),
                    "start_date": None,
                }

        # Calculate total expected for this date (all components + debt)
        total_scheduled = Decimal("0")
        total_outstanding_debt = Decimal("0")
        component_breakdown = {}

        for line in lines_for_date:
            comp_type = line["componentTypeCode"]
            scheduled_amount = Decimal(str(line["paymentMoney"]["amount"]))
            outstanding_debt = debt_balance_by_component[comp_type]["amount"]

            component_breakdown[comp_type] = {
                "scheduled": scheduled_amount,
                "outstanding_debt": outstanding_debt,
                "line": line,
            }

            total_scheduled += scheduled_amount
            total_outstanding_debt += outstanding_debt

        total_expected = total_scheduled + total_outstanding_debt

        # Get actual payment for this date
        tx_group = transaction_groups.get(pay_date, {})
        actual_net_payment = tx_group.get("net", Decimal("0"))
        actual_paid = (
            abs(actual_net_payment) if actual_net_payment < 0 else Decimal("0")
        )

        logger.info(
            f"\n  {pay_date}:\n"
            f"    Scheduled (all components): £{total_scheduled:.2f}\n"
            f"    Outstanding debt (all): £{total_outstanding_debt:.2f}\n"
            f"    Total expected: £{total_expected:.2f}\n"
            f"    Actual paid: £{actual_paid:.2f}"
        )

        for comp_type, info in component_breakdown.items():
            logger.info(
                f"      [{comp_type}] Scheduled: £{info['scheduled']:.2f}, "
                f"Debt: £{info['outstanding_debt']:.2f}"
            )

        # Log transactions
        if pay_date in transaction_groups:
            for tx in transaction_groups[pay_date]["transactions"]:
                logger.debug(
                    f"      TX: £{tx['amount']:.2f} ({tx['type']}) - {tx['details']}"
                )

        # ═══════════════════════════════════════════════════════════════════
        # PAYMENT ALLOCATION LOGIC (BY DATE, NOT BY LINE)
        # ═══════════════════════════════════════════════════════════════════

        if actual_paid >= total_expected:
            # FULL PAYMENT - covers current + all debt
            for comp_type, info in component_breakdown.items():
                info["line"]["processed"] = True

                if debt_balance_by_component[comp_type]["amount"] > 0:
                    logger.info(
                        f"    ✓ [{comp_type}] Debt cleared: "
                        f"£{debt_balance_by_component[comp_type]['amount']:.2f} → £0.00"
                    )

                debt_balance_by_component[comp_type]["amount"] = Decimal("0")
                debt_balance_by_component[comp_type]["start_date"] = None

        else:
            # INSUFFICIENT PAYMENT - allocate shortfall proportionally
            total_shortfall = total_expected - actual_paid

            for comp_type, info in component_breakdown.items():
                info["line"]["processed"] = False

                # Calculate proportional shortfall for this component
                component_expected = info["scheduled"] + info["outstanding_debt"]
                proportion = (
                    component_expected / total_expected
                    if total_expected > 0
                    else Decimal("0")
                )
                component_shortfall = (total_shortfall * proportion).quantize(
                    Decimal("0.01")
                )

                # Track debt start date
                if debt_balance_by_component[comp_type]["start_date"] is None:
                    debt_balance_by_component[comp_type]["start_date"] = pay_date

                # Add shortfall to debt
                debt_balance_by_component[comp_type]["amount"] += component_shortfall

                logger.warning(
                    f"    ✗ [{comp_type}] Shortfall: £{component_shortfall:.2f}. "
                    f"New debt: £{debt_balance_by_component[comp_type]['amount']:.2f}"
                )

        # Track debt for reporting
        for comp_type in component_breakdown.keys():
            if comp_type not in debt_by_line_by_component:
                debt_by_line_by_component[comp_type] = []

            debt_by_line_by_component[comp_type].append(
                {
                    "payment_date": pay_date,
                    "processed": component_breakdown[comp_type]["line"]["processed"],
                    "debt_after": debt_balance_by_component[comp_type]["amount"],
                }
            )

    logger.info(f"\n{'=' * 70}")
    logger.info("Final Debt Summary:")
    for comp_type, debt_info in debt_balance_by_component.items():
        if debt_info["amount"] > 0:
            logger.info(
                f"  {comp_type}: £{debt_info['amount']:.2f} "
                f"(started: {debt_info['start_date']})"
            )
        else:
            logger.info(f"  {comp_type}: £0.00 (no debt)")
    logger.info(f"{'=' * 70}\n")

    return schedule_lines, debt_by_line_by_component, debt_balance_by_component


def generate_schedule_lines(
    cashflow_json,
    interest_json,
    expected_principal,
    start_date,
    term,
    agreement_ref=None,
    currency="GBP",
):
    """
    Generate schedule lines from CashFlow + InterestPayments.

    Returns: (schedule_lines, actual_pri_total, strategy_used_flag, actual_end_date)
    """
    schedule_lines = []

    # Parse JSON
    try:
        cashflow_data = json.loads(cashflow_json or "[]")
        interest_data = json.loads(interest_json or "[]")
    except Exception as e:
        logger.error(f"JSON parsing error: {e}")
        schedule_lines.append(
            {
                "componentTypeCode": "PRI",
                "paymentMoney": {
                    "amount": safe_amount(expected_principal),
                    "currencyCode": currency,
                },
                "paymentDate": start_date,
                "processed": False,
            }
        )
        return schedule_lines, Decimal(str(expected_principal)), False, start_date

    if not isinstance(cashflow_data, list):
        cashflow_data = [cashflow_data]
    if not isinstance(interest_data, list):
        interest_data = [interest_data]

    # Filter by agreement_ref
    if agreement_ref:
        cashflow_data = [
            x
            for x in cashflow_data
            if x.get("AGREEMENT_REF") == agreement_ref
            or x.get("AgreementRef") == agreement_ref
        ]
        interest_data = [
            x
            for x in interest_data
            if x.get("AGREEMENT_REF") == agreement_ref
            or x.get("AgreementRef") == agreement_ref
        ]

    # Flatten CashFlow schedule lines
    flat_schedule_lines = []
    for cf_entry in cashflow_data:
        sl_json = cf_entry.get("ScheduleLines")
        if not sl_json:
            continue
        try:
            sl_list = json.loads(sl_json) if isinstance(sl_json, str) else sl_json
            if isinstance(sl_list, list):
                flat_schedule_lines.extend(sl_list)
        except Exception as e:
            logger.error(f"Error parsing ScheduleLines: {e}")

    if not flat_schedule_lines:
        logger.warning("No schedule lines found in CashFlow")
        return [], Decimal("0"), False, start_date

    # Sort by DUE_DATE
    flat_schedule_lines.sort(key=lambda x: x.get("DUE_DATE", ""))

    # Build interest lookup by month
    interest_by_month = {}
    for ip_entry in interest_data:
        ip_list_str = ip_entry.get("InterestPayments")
        if ip_list_str:
            try:
                ips = (
                    json.loads(ip_list_str)
                    if isinstance(ip_list_str, str)
                    else ip_list_str
                )
            except:
                ips = [ip_entry]
        else:
            ips = [ip_entry]

        if not isinstance(ips, list):
            ips = [ips]

        for ip in ips:
            due_date_str = ip.get("DUE_DATE") or ip.get("due_date")
            if not due_date_str:
                continue

            try:
                due_date = datetime.strptime(str(due_date_str)[:10], "%Y-%m-%d")
            except ValueError:
                continue

            month_key = due_date.strftime("%Y-%m")
            interest_by_month.setdefault(month_key, Decimal("0"))

            interest_value = ip.get("InterestPaymentValue") or ip.get("VALUE") or 0
            interest_by_month[month_key] += abs(Decimal(str(interest_value)))

    # Process schedule lines
    actual_pri_total = Decimal("0")
    first_cf_date = None
    last_cf_date = None

    for idx, sl in enumerate(flat_schedule_lines):
        due_date_str = sl.get("DUE_DATE")
        if not due_date_str:
            continue

        try:
            pay_date = datetime.strptime(str(due_date_str)[:10], "%Y-%m-%d")
        except ValueError:
            continue

        payment_month = pay_date.strftime("%Y-%m")
        total_payment = abs(Decimal(str(sl.get("CASH_FLOW", 0))))

        if first_cf_date is None:
            first_cf_date = pay_date
        last_cf_date = pay_date

        # Get interest for this month
        monthly_interest = interest_by_month.get(payment_month, Decimal("0"))
        pri_amount = (total_payment - monthly_interest).quantize(Decimal("0.01"))

        # Add INT line
        if monthly_interest > 0:
            schedule_lines.append(
                {
                    "componentTypeCode": "INT",
                    "paymentMoney": {
                        "amount": safe_amount(monthly_interest),
                        "currencyCode": currency,
                    },
                    "paymentDate": pay_date.strftime("%Y-%m-%d"),
                    "processed": False,
                }
            )

        # Add PRI line
        if pri_amount > 0:
            schedule_lines.append(
                {
                    "componentTypeCode": "PRI",
                    "paymentMoney": {
                        "amount": safe_amount(pri_amount),
                        "currencyCode": currency,
                    },
                    "paymentDate": pay_date.strftime("%Y-%m-%d"),
                    "processed": False,
                }
            )
            actual_pri_total += pri_amount

    actual_end_date = last_cf_date.strftime("%Y-%m-%d") if last_cf_date else start_date

    return schedule_lines, actual_pri_total, False, actual_end_date


def calculate_component_balances(schedule_lines):
    """
    Calculate outstanding balances for each component based on unprocessed lines.

    Returns: {componentTypeCode: outstanding_amount}
    """
    balances = {}

    for line in schedule_lines:
        comp_type = line["componentTypeCode"]
        if comp_type not in balances:
            balances[comp_type] = Decimal("0")

        if not line.get("processed", False):
            amount = Decimal(str(line["paymentMoney"]["amount"]))
            balances[comp_type] += amount

    return balances


def build_component_with_debts(
    component_type,
    balance_amount,
    debt_info,
    apr=None,
):
    """
    Build component with proper debt tracking.

    debt_info: {amount: Decimal, start_date: str or None}
    """
    component = Component(
        componentTypeCode=component_type,
        paymentInterval=1,
        balanceMoney={
            "amount": safe_amount(balance_amount),
            "currencyCode": "GBP",
        },
        invoicedBalanceMoney={
            "amount": 0.00,
            "currencyCode": "GBP",
        },
    )

    # Set debt if exists
    if debt_info.get("amount", Decimal("0")) > 0 and debt_info.get("start_date"):
        component.debts = [
            {
                "debtMoney": {
                    "amount": safe_amount(debt_info["amount"]),
                    "currencyCode": "GBP",
                },
                "debtStartDate": debt_info["start_date"],
            }
        ]
    else:
        component.debts = None

    # INT-specific fields
    if component_type == "INT":
        component.calculationMethod = {
            "daysInMonth": "ACT",
            "daysInYear": "365",
        }
        component.rateTypeCode = "FIXED"
        component.rate = float(apr) if apr else 0.0
        component.marginRate = 0.0
        component.baseRate = 0.0

    return component


def _build_contract(
    agreement,
    person_id,
    schedule_lines,
    debt_by_component,
    component_balances,
    actual_end_date,
    start_date,
):
    """Build Contract dataclass from components"""
    agreement_ref = agreement.get("AGREEMENT_REF")
    principal = Decimal(str(agreement.get("AMOUNT_FINANCED", 0)))
    term = agreement.get("TERM_IN_MONTHS", agreement.get("TERM", 60))
    apr = agreement.get("APR") or 0.0
    monthly_payment = agreement.get("PAYMENT", 0)
    payment_day = agreement.get("PAYMENT_DAY", 1)

    try:
        prep_date_str = str(agreement.get("CREATION_SYSTEM_DATE", start_date))[:10]
        signing_date_str = str(agreement.get("CONTRACT_DATE", start_date))[:10]
    except (IndexError, TypeError):
        prep_date_str = start_date
        signing_date_str = start_date

    # Build components
    components = []

    # PRI Component
    pri_balance = component_balances.get("PRI", Decimal("0"))
    pri_debt = debt_by_component.get(
        "PRI", {"amount": Decimal("0"), "start_date": None}
    )
    pri_component = build_component_with_debts("PRI", pri_balance, pri_debt)
    components.append(pri_component)

    # ALIM Component
    alim_component = Component(
        componentTypeCode="ALIM",
        paymentInterval=1,
        balanceMoney={"amount": 0.00, "currencyCode": "GBP"},
        invoicedBalanceMoney={"amount": 0.00, "currencyCode": "GBP"},
    )
    components.append(alim_component)

    # INT Component
    int_balance = component_balances.get("INT", Decimal("0"))
    int_debt = debt_by_component.get(
        "INT", {"amount": Decimal("0"), "start_date": None}
    )
    int_component = build_component_with_debts("INT", int_balance, int_debt, apr=apr)
    components.append(int_component)

    # Repayment
    repayment = Repayment(
        paymentFreeMonths=None,
        monthlyRepaymentAmount={
            "amount": safe_amount(monthly_payment),
            "currencyCode": "GBP",
        },
        monthlyRepaymentRate=None,
        maxInvoiceMoney=None,
        minInvoiceMoney=None,
        invoiceDay=None,
        paymentDay=payment_day,
        previousInvoiceDate=prep_date_str,
    )

    # Build Contract
    contract = Contract(
        externalPersonId=person_id,
        tuumPersonId=None,
        externalContractId=agreement_ref,
        source={
            "sourceName": "MY-CONTRACT-DB",
            "sourceRef": agreement_ref,
        },
        contractNumber=agreement.get("AGREEMENT_CODE", agreement_ref),
        loanTypeCode=LOAN_TYPE_CODE,
        referenceNumber=None,
        preparationDate=prep_date_str,
        signingDate=signing_date_str,
        startDate=start_date,
        activationDate=start_date,
        endDate=actual_end_date,
        stopDate=None,
        statusCode="ACTIVE",
        period=term,
        apr=float(apr),
        scheduleTypeCode="ANNUITY",
        limitMoney={
            "amount": safe_amount(principal),
            "currencyCode": "GBP",
        },
        contractFeeMoney=None,
        contractMoney={
            "amount": safe_amount(principal),
            "currencyCode": "GBP",
        },
        countryCode=COUNTRY_CODE,
        tenantCode=TENANT_CODE,
        solvencyLevelCode=None,
        externalServicingAccountId=None,
        repayment=repayment,
        hasCollateral=False,
        initialLtv=None,
        currentLtv=None,
        limitUsageDate=None,
        penaltyGraceDays=0,
        penaltyGraceMoney=None,
        repaymentChannelCode=REPAYMENT_CHANNEL_CODE,
        contractConditions=None,
        components=components,
        scheduleLines=schedule_lines,
    )

    return contract


def map_agreement(row):
    """
    Main orchestrator: processes agreement from CSV row.

    Returns: List[Contract]
    """
    contracts = []
    person_id = row.get("IBCSurrogate", "UNKNOWN-ID")
    transaction_history_json = row.get("MaskedTransactionHistory", "[]")

    try:
        agreements = json.loads(row.get("MaskedAgreementHistory", "[]"))
    except Exception as e:
        logger.error(f"Error parsing MaskedAgreementHistory: {e}")
        return []

    if not isinstance(agreements, list):
        agreements = [agreements]

    # Parse transactions once per row
    transactions = parse_transaction_history(transaction_history_json)

    for agreement in agreements:
        try:
            agreement_ref = agreement.get("AGREEMENT_REF")
            principal = Decimal(str(agreement.get("AMOUNT_FINANCED", 0)))
            start_date_raw = agreement.get("CREATION_SYSTEM_DATE", "")
            start_date = str(start_date_raw)[:10] if start_date_raw else "2023-01-01"
            term = agreement.get("TERM_IN_MONTHS", agreement.get("TERM", 60))
            monthly_repayment = agreement.get("PAYMENT", 0)

            # Generate schedule lines
            schedule_lines, actual_pri, _, actual_end_date = generate_schedule_lines(
                cashflow_json=row.get("CashFlow", "[]"),
                interest_json=row.get("InterestPayments", "[]"),
                expected_principal=principal,
                start_date=start_date,
                term=term,
                agreement_ref=agreement_ref,
                currency="GBP",
            )

            if not schedule_lines:
                logger.warning(f"No schedule lines for {agreement_ref}")
                continue

            # Group transactions by posting date
            transaction_groups = group_transactions_by_posting_date(
                transactions,
                agreement_ref,
            )

            # Process schedule with transactions and track debt
            schedule_lines, debt_by_line, debt_by_component = (
                process_schedule_with_transactions(
                    schedule_lines,
                    Decimal(str(monthly_repayment)),
                    transaction_groups,
                    agreement_ref,
                )
            )

            # Calculate remaining balances
            component_balances = calculate_component_balances(schedule_lines)

            # Build contract
            contract = _build_contract(
                agreement=agreement,
                person_id=person_id,
                schedule_lines=schedule_lines,
                debt_by_component=debt_by_component,
                component_balances=component_balances,
                actual_end_date=actual_end_date,
                start_date=start_date,
            )

            contracts.append(contract)

        except Exception as e:
            logger.error(
                f"Error processing agreement {agreement.get('AGREEMENT_REF')}: {e}",
                exc_info=True,
            )

    return contracts
