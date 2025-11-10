# domain_mapper/contracts_mapper.py

import csv
import json
import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

from domain_config.contracts_config import (
    COUNTRY_CODE,
    IMPORT_DATE,
    LOAN_TYPE_CODE,
    REPAYMENT_CHANNEL_CODE,
    TENANT_CODE,
)
from domain_dataclass.contracts_dataclass import Component, Contract, Repayment
from utils.utils import replace_prefix_with_timestamp

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


def group_transactions_by_posting_date(transactions):
    """Group transactions by posting date and calculate total amount"""
    from collections import defaultdict

    grouped = defaultdict(list)
    for txn in transactions:
        posting_date = txn.get("POSTING_DATE", "")[:10]
        if posting_date:
            grouped[posting_date].append(txn)

    return grouped


def calculate_processed_amounts(transactions, cashflow_schedule):
    """
    Calculate which payments have been processed based on transaction history.
    Returns dict mapping payment dates to processed amounts.
    """
    grouped_txns = group_transactions_by_posting_date(transactions)
    processed_payments = {}

    for payment_date, txns in grouped_txns.items():
        total_amount = sum(abs(Decimal(str(txn.get("AMOUNT", 0)))) for txn in txns)
        processed_payments[payment_date] = total_amount

    return processed_payments


def generate_schedule_lines(
    cashflow_json,
    interest_json,
    expected_principal,
    start_date,
    term,
    agreement_ref=None,
    currency="GBP",
    transaction_history=None,
):
    """
    Generate schedule lines with adaptive deferred interest strategy.

    Strategy:
    1. Identify pre-contract interest (charges before first payment)
    2. Determine optimal spread period (12, 24, 36, or all payments)
    3. Allocate deferred interest evenly across spread period
    4. Match month interest to payment dates
    5. Mark past payments as processed
    6. Validate every penny is accounted for
    7. Adjust first PRI line to match expected principal exactly

    Returns: (schedule_lines, pri_total, is_fallback, end_date)
    """

    schedule_lines = []
    today_str = date.today().isoformat()  # "2025-11-09"

    try:
        # ═══════════════════════════════════════════════════════════════════
        # STEP 1: Parse JSON data
        # ═══════════════════════════════════════════════════════════════════
        cashflow_data = json.loads(cashflow_json or "[]")
        interest_data = json.loads(interest_json or "[]")

        if not isinstance(cashflow_data, list):
            cashflow_data = [cashflow_data]
        if not isinstance(interest_data, list):
            interest_data = [interest_data]

        # Filter by agreement_ref if provided
        if agreement_ref:
            cashflow_data = [
                x for x in cashflow_data if x.get("AgreementRef") == agreement_ref
            ]
            interest_data = [
                x for x in interest_data if x.get("AgreementRef") == agreement_ref
            ]

        # ═══════════════════════════════════════════════════════════════════
        # STEP 2: Extract instalments from cashflow
        # ═══════════════════════════════════════════════════════════════════
        flat_schedule_lines = []
        for cf_entry in cashflow_data:
            sl_json = cf_entry.get("ScheduleLines", "[]")
            try:
                sl_list = json.loads(sl_json) if isinstance(sl_json, str) else sl_json
                if isinstance(sl_list, list):
                    flat_schedule_lines.extend(sl_list)
            except Exception as e:
                logger.error(f"Error parsing ScheduleLines: {e}")

        # Filter for INSTALMENT entries only
        instalments = [
            sl
            for sl in flat_schedule_lines
            if sl.get("FINANCE_DETAIL_BEH_CODE") == "INSTALMENT"
        ]
        instalments.sort(key=lambda x: x.get("DUE_DATE", ""))

        if not instalments:
            logger.warning(f"No instalments found for {agreement_ref}")
            return _create_fallback_schedule(
                expected_principal,
                start_date,
                currency,
                instalments=None,
                all_interest_charges=None,
            )

        logger.info(f"Found {len(instalments)} instalments")

        # ═══════════════════════════════════════════════════════════════════
        # STEP 3: Extract finance charges (interest) from interest payments
        # ═══════════════════════════════════════════════════════════════════
        all_interest_charges = []

        for ip_entry in interest_data:
            ip_list_str = ip_entry.get("InterestPayments", "[]")
            try:
                ips = (
                    json.loads(ip_list_str)
                    if isinstance(ip_list_str, str)
                    else ip_list_str
                )
            except:
                ips = [ip_entry]

            if not isinstance(ips, list):
                ips = [ips]

            for ip in ips:
                if ip.get("FINANCE_DETAIL_BEH_CODE") == "FINANCE_CHARGE":
                    due_date_str = ip.get("DUE_DATE", "")[:10]
                    if not due_date_str:
                        continue

                    amount = abs(Decimal(str(ip.get("InterestPaymentValue", 0))))

                    all_interest_charges.append(
                        {
                            "date": due_date_str,
                            "amount": amount,
                        }
                    )

        all_interest_charges.sort(key=lambda x: x["date"])
        logger.info(f"Found {len(all_interest_charges)} finance charges")

        # ═══════════════════════════════════════════════════════════════════
        # STEP 4: Identify pre-contract interest and determine spread period
        # ═══════════════════════════════════════════════════════════════════
        first_payment_date = instalments[0].get("DUE_DATE", "")[:10]

        pre_contract_interest = sum(
            ic["amount"]
            for ic in all_interest_charges
            if ic["date"] < first_payment_date
        )

        logger.info(f"Pre-contract interest: £{pre_contract_interest:.2f}")

        if pre_contract_interest == Decimal("0"):
            # No pre-contract interest - simple month matching
            spread_period = 0
            logger.info("No pre-contract interest - using simple month matching")
        else:
            # Determine optimal spread period using adaptive algorithm
            spread_period = _calculate_optimal_spread_period(
                pre_contract_interest=pre_contract_interest,
                instalments=instalments,
                all_interest_charges=all_interest_charges,
                first_payment_date=first_payment_date,
            )

            if spread_period is None:
                logger.error("Cannot maintain positive PRI with any spread period")
                return _create_fallback_schedule(
                    expected_principal,
                    start_date,
                    currency,
                    instalments=instalments,
                    all_interest_charges=all_interest_charges,
                )

            logger.info(f"Using {spread_period}-month spread period")

        # ═══════════════════════════════════════════════════════════════════
        # STEP 5: Generate schedule lines with penny-perfect tracking
        # ═══════════════════════════════════════════════════════════════════
        deferred_per_payment = (
            (pre_contract_interest / spread_period).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if spread_period > 0
            else Decimal("0")
        )

        # Initialize penny-tracking accumulators
        total_deferred_allocated = Decimal("0")
        total_month_interest_used = Decimal("0")
        total_pri_calculated = Decimal("0")
        total_int_calculated = Decimal("0")

        deferred_allocated = Decimal("0")

        # Parse transaction history if provided
        processed_payments = {}
        if transaction_history:
            transactions = parse_transaction_history(transaction_history)
            processed_payments = calculate_processed_amounts(transactions, instalments)

        for idx, inst in enumerate(instalments):
            due_date_str = inst.get("DUE_DATE", "")[:10]
            payment_month = due_date_str[:7]  # YYYY-MM
            payment_amount = abs(Decimal(str(inst.get("CASH_FLOW", 0))))

            # Match interest charges by calendar month (excluding pre-contract)
            month_interest = sum(
                ic["amount"]
                for ic in all_interest_charges
                if ic["date"][:7] == payment_month and ic["date"] >= first_payment_date
            )

            # Calculate deferred portion (CRITICAL: last spread payment gets remainder)
            if spread_period > 0 and idx < spread_period:
                if idx == spread_period - 1:
                    # Last payment in spread: allocate exact remainder to avoid rounding errors
                    deferred_portion = pre_contract_interest - deferred_allocated
                else:
                    deferred_portion = deferred_per_payment

                deferred_allocated += deferred_portion
            else:
                deferred_portion = Decimal("0")

            total_interest = month_interest + deferred_portion
            pri_amount = (payment_amount - total_interest).quantize(Decimal("0.01"))

            # SAFETY CHECK: Ensure PRI is positive
            if pri_amount < 0:
                logger.error(f"NEGATIVE PRI at payment {idx + 1}: £{pri_amount:.2f}")
                logger.error(f"  Payment date: {due_date_str}")
                logger.error(f"  Payment amount: £{payment_amount:.2f}")
                logger.error(f"  Month interest: £{month_interest:.2f}")
                logger.error(f"  Deferred interest: £{deferred_portion:.2f}")

                # Log the specific cashflow causing the issue
                logger.error(f"\n  Cashflow entry details:")
                logger.error(f"    DUE_DATE: {inst.get('DUE_DATE')}")
                logger.error(f"    CASH_FLOW: {inst.get('CASH_FLOW')}")
                logger.error(
                    f"    FINANCE_DETAIL_BEH_CODE: {inst.get('FINANCE_DETAIL_BEH_CODE')}"
                )

                # Log interest charges for this month
                logger.error(f"\n  Interest charges for month {payment_month}:")
                month_charges = [
                    ic for ic in all_interest_charges if ic["date"][:7] == payment_month
                ]
                if month_charges:
                    for ic in month_charges:
                        logger.error(
                            f"    Date: {ic['date']}, Amount: £{ic['amount']:.2f}"
                        )
                else:
                    logger.error(f"    No interest charges found for this month")

                logger.error("\nUsing fallback schedule")
                return _create_fallback_schedule(
                    expected_principal,
                    start_date,
                    currency,
                    instalments=instalments,
                    all_interest_charges=all_interest_charges,
                )

            # Track for validation
            total_month_interest_used += month_interest
            total_deferred_allocated += deferred_portion
            total_pri_calculated += pri_amount
            total_int_calculated += total_interest

            # ═══════════════════════════════════════════════════════════════
            # CRITICAL: Determine if payment is in the past (PROCESSED)
            # ═══════════════════════════════════════════════════════════════
            # Check transaction history first, then fall back to date comparison
            if due_date_str in processed_payments:
                is_processed = True
            else:
                is_processed = due_date_str < today_str

            # Create INT schedule line (if interest exists)
            if total_interest > 0:
                schedule_lines.append(
                    {
                        "componentTypeCode": "INT",
                        "paymentMoney": {
                            "amount": safe_amount(total_interest),
                            "currencyCode": currency,
                        },
                        "paymentDate": due_date_str,
                        "processed": is_processed,  # ← FIXED: Mark past payments as processed
                    }
                )

            # Create PRI schedule line
            schedule_lines.append(
                {
                    "componentTypeCode": "PRI",
                    "paymentMoney": {
                        "amount": safe_amount(pri_amount),
                        "currencyCode": currency,
                    },
                    "paymentDate": due_date_str,
                    "processed": is_processed,  # ← FIXED: Mark past payments as processed
                }
            )

        # ═══════════════════════════════════════════════════════════════════
        # STEP 6: COMPREHENSIVE VALIDATION
        # ═══════════════════════════════════════════════════════════════════
        expected_pri = Decimal(str(expected_principal))

        # Calculate source totals
        total_interest_source = sum(ic["amount"] for ic in all_interest_charges)
        month_interest_source = sum(
            ic["amount"]
            for ic in all_interest_charges
            if ic["date"] >= first_payment_date
        )

        # Log validation results
        logger.info("=" * 70)
        logger.info("VALIDATION REPORT:")
        logger.info(
            f"  Pre-contract: £{pre_contract_interest:.2f} → £{total_deferred_allocated:.2f} "
            + f"(diff: £{abs(pre_contract_interest - total_deferred_allocated):.4f})"
        )
        logger.info(
            f"  Month interest: £{month_interest_source:.2f} → £{total_month_interest_used:.2f}"
        )
        logger.info(
            f"  Total interest: £{total_interest_source:.2f} → £{total_int_calculated:.2f}"
        )
        logger.info(
            f"  Principal: £{expected_pri:.2f} vs £{total_pri_calculated:.2f} "
            + f"(diff: £{abs(expected_pri - total_pri_calculated):.2f})"
        )

        # Validation checks
        pre_contract_valid = abs(
            pre_contract_interest - total_deferred_allocated
        ) < Decimal("0.01")
        principal_valid = abs(expected_pri - total_pri_calculated) < Decimal("1.00")

        if not (pre_contract_valid and principal_valid):
            logger.error("Validation checks FAILED!")
            logger.error(f"  Pre-contract valid: {pre_contract_valid}")
            logger.error(f"  Principal valid: {principal_valid}")

            # Log detailed discrepancies
            logger.error(f"\n  Validation details:")
            logger.error(f"    Expected principal: £{expected_pri:.2f}")
            logger.error(f"    Calculated principal: £{total_pri_calculated:.2f}")
            logger.error(
                f"    Difference: £{abs(expected_pri - total_pri_calculated):.2f}"
            )

            if not pre_contract_valid:
                logger.error(
                    f"    Pre-contract allocated: £{total_deferred_allocated:.2f}"
                )
                logger.error(f"    Pre-contract expected: £{pre_contract_interest:.2f}")

            return _create_fallback_schedule(
                expected_principal,
                start_date,
                currency,
                instalments=instalments,
                all_interest_charges=all_interest_charges,
            )

        # ═══════════════════════════════════════════════════════════════════
        # STEP 7: Final adjustment to match expected principal EXACTLY
        # ═══════════════════════════════════════════════════════════════════
        pri_difference = expected_pri - total_pri_calculated

        if abs(pri_difference) >= Decimal("0.01"):
            logger.info(
                f"Applying final adjustment: £{pri_difference:.2f} to first PRI line"
            )

            # Find and adjust first PRI line
            for line in schedule_lines:
                if line["componentTypeCode"] == "PRI":
                    original = Decimal(str(line["paymentMoney"]["amount"]))
                    adjusted = original + pri_difference
                    line["paymentMoney"]["amount"] = safe_amount(adjusted)

                    logger.info(f"  First PRI: £{original:.2f} → £{adjusted:.2f}")
                    total_pri_calculated = expected_pri
                    break

        logger.info(f"✓ Final principal: £{total_pri_calculated:.2f}")
        logger.info("=" * 70)

        last_payment_date = instalments[-1].get("DUE_DATE", "")[:10]

        return schedule_lines, total_pri_calculated, False, last_payment_date

    except Exception as e:
        logger.error(f"Error generating schedule lines: {e}", exc_info=True)
        return _create_fallback_schedule(
            expected_principal,
            start_date,
            currency,
            instalments=None,
            all_interest_charges=None,
        )


def _calculate_optimal_spread_period(
    pre_contract_interest,
    instalments,
    all_interest_charges,
    first_payment_date,
):
    """
    Calculate optimal spread period using adaptive algorithm.
    Tries 12, 24, 36, then all payments.
    Returns None if no valid period found (data integrity issue).
    """
    # Calculate maximum monthly interest (worst case)
    monthly_totals = {}
    for ic in all_interest_charges:
        if ic["date"] >= first_payment_date:
            month = ic["date"][:7]
            monthly_totals[month] = (
                monthly_totals.get(month, Decimal("0")) + ic["amount"]
            )

    max_monthly_interest = (
        max(monthly_totals.values()) if monthly_totals else Decimal("0")
    )

    payment_amount = abs(Decimal(str(instalments[0]["CASH_FLOW"])))
    min_required_pri = payment_amount * Decimal(
        "0.10"
    )  # Keep at least 10% as principal

    logger.info(f"Adaptive spread calculation:")
    logger.info(f"  Payment amount: £{payment_amount:.2f}")
    logger.info(f"  Max monthly interest: £{max_monthly_interest:.2f}")
    logger.info(f"  Min required PRI (10%): £{min_required_pri:.2f}")

    # Try each candidate period
    for candidate_period in [12, 24, 36, len(instalments)]:
        deferred_per_payment = pre_contract_interest / candidate_period

        # Test worst-case payment (highest interest month)
        test_pri = payment_amount - max_monthly_interest - deferred_per_payment

        logger.info(f"  Testing {candidate_period}-month spread: PRI = £{test_pri:.2f}")

        if test_pri >= min_required_pri:
            logger.info(f"  ✓ Using {candidate_period}-month spread")
            return candidate_period

    # If we get here, even all-payment spread fails
    logger.error("  ✗ No valid spread period found - data integrity issue")
    return None


def _create_fallback_schedule(
    expected_principal,
    start_date,
    currency,
    instalments=None,
    all_interest_charges=None,
):
    """
    Fallback schedule for contracts with data issues.
    Creates INT and PRI lines on the FINAL payment date with totals.

    Strategy:
    - Total INT = sum of all finance charges
    - Total PRI = sum of all instalments - total INT
    - Both lines dated at last instalment date
    - Both marked as processed: false (future payment)
    """
    logger.warning("🚨 Creating FALLBACK schedule with INT + PRI on final date")
    logger.warning("This contract requires manual review")

    today_str = date.today().isoformat()

    # Calculate totals
    if instalments and all_interest_charges:
        # Calculate total interest
        total_interest = sum(ic["amount"] for ic in all_interest_charges)

        # Calculate total payments
        total_payments = sum(
            abs(Decimal(str(inst.get("CASH_FLOW", 0)))) for inst in instalments
        )

        # Calculate principal (Total payments - Total interest)
        total_principal = total_payments - total_interest

        # Use last instalment date
        last_instalment_date = (
            instalments[-1].get("DUE_DATE", "")[:10] if instalments else start_date
        )

        # Determine if fallback date is in the past
        is_processed = last_instalment_date < today_str

        logger.info(f"Fallback schedule calculation:")
        logger.info(f"  Total payments (all instalments): £{total_payments:.2f}")
        logger.info(f"  Total interest (all charges): £{total_interest:.2f}")
        logger.info(f"  Total principal (payments - interest): £{total_principal:.2f}")
        logger.info(f"  Final payment date: {last_instalment_date}")
        logger.info(f"  Marked as processed: {is_processed}")

        # Create schedule lines on FINAL date
        schedule_lines = [
            {
                "componentTypeCode": "INT",
                "paymentMoney": {
                    "amount": safe_amount(total_interest),
                    "currencyCode": currency,
                },
                "paymentDate": last_instalment_date,
                "processed": is_processed,
            },
            {
                "componentTypeCode": "PRI",
                "paymentMoney": {
                    "amount": safe_amount(total_principal),
                    "currencyCode": currency,
                },
                "paymentDate": last_instalment_date,
                "processed": is_processed,
            },
        ]

        return (
            schedule_lines,
            total_principal,
            True,  # is_fallback flag
            last_instalment_date,
        )

    else:
        # Absolute fallback - no data available
        logger.error("No instalment/interest data available - using minimal fallback")

        return (
            [
                {
                    "componentTypeCode": "PRI",
                    "paymentMoney": {
                        "amount": safe_amount(expected_principal),
                        "currencyCode": currency,
                    },
                    "paymentDate": start_date,
                    "processed": start_date < today_str,
                }
            ],
            Decimal(str(expected_principal)),
            True,
            start_date,
        )


def map_contract_from_csv_row(row):
    """
    Main entry point: Map CSV row to Contract dataclass.
    Matches success_1.json structure exactly.
    """
    try:
        # Parse agreement history
        agreement_history = json.loads(row.get("MaskedAgreementHistory", "[]"))
        if isinstance(agreement_history, list) and agreement_history:
            agreement_history = agreement_history[0]

        # Extract key fields
        agreement_surrogate_ref = agreement_history.get("AgreementSurrogateRef", "")
        agreement_ref = agreement_history.get("AGREEMENT_REF", "")
        external_contract_id = agreement_surrogate_ref or agreement_ref
        external_person_id = row.get("IBCSurrogate", "")

        transformed_external_id = replace_prefix_with_timestamp(external_person_id)
        transformed_contract_id = replace_prefix_with_timestamp(external_contract_id)

        # Contract financial details
        principal = float(agreement_history.get("AMOUNT_FINANCED", 0))
        apr = float(agreement_history.get("APR", 0))
        term = int(agreement_history.get("TERM", 0))
        monthly_payment = float(agreement_history.get("PAYMENT", 0))

        # Extract payment day from agreement or use default
        payment_day_str = agreement_history.get("PAYMENT_DAY", "1")
        try:
            payment_day = int(payment_day_str)
        except:
            payment_day = 1

        # Dates
        creation_date_str = agreement_history.get("CREATIONSYSTEMDATE", "")[:10]
        contract_date_str = agreement_history.get("CONTRACT_DATE", "")[:10]

        # Use CONTRACT_DATE for signing/start/activation, CREATION for preparation
        preparation_date = (
            creation_date_str
            if creation_date_str
            else datetime.now().strftime("%Y-%m-%d")
        )
        signing_date = contract_date_str if contract_date_str else preparation_date
        start_date = signing_date
        activation_date = signing_date

        # Generate schedule lines
        schedule_lines, actual_pri, is_fallback, end_date = generate_schedule_lines(
            cashflow_json=row.get("CashFlow", "[]"),
            interest_json=row.get("InterestPayments", "[]"),
            expected_principal=principal,
            start_date=start_date,
            term=term,
            agreement_ref=agreement_ref,
            transaction_history=row.get("MaskedTransactionHistory"),
        )

        # Get first payment date for previousInvoiceDate
        first_payment_date = None
        if schedule_lines:
            for line in schedule_lines:
                if line.get("componentTypeCode") == "PRI":
                    first_payment_date = line.get("paymentDate")
                    break

        # ═══════════════════════════════════════════════════════════════════
        # CRITICAL FIX: Calculate component balances from UNPROCESSED lines only
        # ═══════════════════════════════════════════════════════════════════
        pri_balance = sum(
            Decimal(str(line["paymentMoney"]["amount"]))
            for line in schedule_lines
            if line.get("componentTypeCode") == "PRI"
            and not line.get("processed", False)
        )

        int_balance = sum(
            Decimal(str(line["paymentMoney"]["amount"]))
            for line in schedule_lines
            if line.get("componentTypeCode") == "INT"
            and not line.get("processed", False)
        )

        logger.info("Component balances (unprocessed only):")
        logger.info(f"  PRI balance: £{pri_balance:.2f}")
        logger.info(f"  INT balance: £{int_balance:.2f}")

        # Create Contract object matching success_1.json structure
        contract = Contract(
            # Identifiers
            externalPersonId=transformed_external_id,
            externalContractId=transformed_contract_id,
            contractNumber=transformed_contract_id,  # Same as externalContractId
            # Source
            source={
                "sourceName": "MY-CONTRACT-DB",  # Your legacy system name
                "sourceRef": transformed_external_id,  # IBCSurrogate
            },
            # Loan type and status
            loanTypeCode=LOAN_TYPE_CODE,  # From config
            statusCode="ACTIVE",  # Static
            scheduleTypeCode="ANNUITY",  # Static
            # Dates
            preparationDate=preparation_date,
            signingDate=signing_date,
            startDate=start_date,
            activationDate=activation_date,
            endDate=end_date,
            # Financial
            period=term,
            apr=apr,
            limitMoney={"amount": principal, "currencyCode": "GBP"},
            contractMoney={"amount": principal, "currencyCode": "GBP"},
            # Location
            countryCode=COUNTRY_CODE,  # "GB"
            tenantCode=TENANT_CODE,  # Your tenant code
            # Repayment
            repayment=Repayment(
                monthlyRepaymentAmount={
                    "amount": monthly_payment,
                    "currencyCode": "GBP",
                },
                paymentDay=payment_day,
                previousInvoiceDate=first_payment_date,  # First payment date
                monthlyRepaymentRate=None,
                paymentFreeMonths=None,
                maxInvoiceMoney=None,
                minInvoiceMoney=None,
                invoiceDay=None,
            ),
            repaymentChannelCode=REPAYMENT_CHANNEL_CODE,
            # Components with CORRECTED balances
            components=[
                # Principal component - balance = sum of UNPROCESSED PRI lines
                Component(
                    componentTypeCode="PRI",
                    paymentInterval=1,
                    balanceMoney={
                        "amount": safe_amount(pri_balance),
                        "currencyCode": "GBP",
                    },
                    invoicedBalanceMoney={"amount": 0, "currencyCode": "GBP"},
                ),
                # ALIM component (credit limit - required by Tuum)
                Component(
                    componentTypeCode="ALIM",
                    balanceMoney={"amount": 0, "currencyCode": "GBP"},
                    invoicedBalanceMoney={"amount": 0, "currencyCode": "GBP"},
                ),
                # Interest component - balance = sum of UNPROCESSED INT lines
                Component(
                    componentTypeCode="INT",
                    paymentInterval=1,
                    balanceMoney={
                        "amount": safe_amount(int_balance),
                        "currencyCode": "GBP",
                    },
                    invoicedBalanceMoney={"amount": 0, "currencyCode": "GBP"},
                    calculationMethod={"daysInMonth": "ACT", "daysInYear": "365"},
                    rateTypeCode="FIXED",
                    rate=apr,
                    rateBaseCode=None,
                    marginRate=0,
                    baseRate=0,
                ),
            ],
            # Schedule lines
            scheduleLines=schedule_lines,
        )

        if is_fallback:
            logger.warning(f"Contract {external_contract_id} used fallback schedule")

        return contract

    except Exception as e:
        logger.error(f"Error mapping contract: {e}", exc_info=True)
        return None
