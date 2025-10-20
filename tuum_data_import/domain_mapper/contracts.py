import json
from datetime import datetime

from dateutil.relativedelta import relativedelta

from domain_config.contracts import COUNTRY_CODE
from domain_dataclass.contracts import Component, Contract, Repayment


def generate_schedule_lines_simple(end_date_str, principal, currency="GBP"):
    return [
        {
            "componentTypeCode": "PRI",
            "paymentMoney": {"amount": round(principal, 2), "currencyCode": currency},
            "paymentDate": end_date_str,
        }
    ]


def map_agreement(row):
    contracts = []
    try:
        ext_id = row.get("SurrogateKey")
        agreements = json.loads(row.get("MaskedAgreementHistory", "[]"))
        for agreement in agreements:
            term = agreement.get("TERM", 0)
            payment = agreement.get("PAYMENT", 0)
            principal = agreement.get("AMOUNT_FINANCED", 0)
            start_date = agreement.get("CREATION_SYSTEM_DATE", "")[:10]

            end_date_obj = datetime.strptime(start_date, "%Y-%m-%d") + relativedelta(
                months=term
            )
            end_date = end_date_obj.strftime("%Y-%m-%d")

            schedule_lines = generate_schedule_lines_simple(end_date, principal)

            components = [
                Component(
                    componentTypeCode="PRI",
                    paymentInterval=1,
                    balanceMoney={"amount": principal, "currencyCode": "GBP"},
                    invoicedBalanceMoney={"amount": 0, "currencyCode": "GBP"},
                ),
                Component(
                    componentTypeCode="ALIM",
                    balanceMoney={"amount": 0, "currencyCode": "GBP"},
                    invoicedBalanceMoney={"amount": 0, "currencyCode": "GBP"},
                ),
                Component(
                    componentTypeCode="INT",
                    paymentInterval=1,
                    balanceMoney={"amount": 0, "currencyCode": "GBP"},
                    invoicedBalanceMoney={"amount": 0, "currencyCode": "GBP"},
                    calculationMethod={"daysInMonth": "ACT", "daysInYear": "365"},
                    rateTypeCode="FIXED",
                    rate=agreement.get("APR", 0),
                    rateBaseCode=None,
                    marginRate=0,
                    baseRate=0,
                ),
            ]

            repayment = Repayment(
                paymentFreeMonths=None,
                monthlyRepaymentAmount={"amount": payment, "currencyCode": "GBP"},
                monthlyRepaymentRate=None,
                maxInvoiceMoney=None,
                minInvoiceMoney=None,
                invoiceDay=None,
                paymentDay=1,
                previousInvoiceDate=(
                    datetime.strptime(start_date, "%Y-%m-%d") + relativedelta(months=1)
                )
                .replace(day=1)
                .strftime("%Y-%m-%d"),
            )

            contract = Contract(
                externalPersonId=ext_id,
                tuumPersonId=None,
                externalContractId=ext_id,
                source={"sourceName": "MY-CONTRACT-DB", "sourceRef": ext_id},
                contractNumber=ext_id,
                loanTypeCode="BF_DEMO_2",
                referenceNumber=None,
                preparationDate=start_date,
                signingDate=start_date,
                startDate=start_date,
                activationDate=start_date,
                endDate=end_date,
                stopDate=None,
                statusCode="ACTIVE",
                period=term,
                apr=agreement.get("APR"),
                scheduleTypeCode="ANNUITY",
                limitMoney={"amount": principal, "currencyCode": "GBP"},
                contractFeeMoney=None,
                contractMoney={"amount": principal, "currencyCode": "GBP"},
                countryCode=COUNTRY_CODE,
                tenantCode="MB",
                solvencyLevelCode=None,
                externalServicingAccountId=None,
                repayment=repayment,
                hasCollateral=False,
                initialLtv=None,
                currentLtv=None,
                limitUsageDate=None,
                penaltyGraceDays=None,
                penaltyGraceMoney=None,
                repaymentChannelCode="PAYMENT_ROUTER_WITH_IBAN",
                contractConditions=None,
                components=components,
                coBorrowers=None,
                scheduleLines=schedule_lines,
                customFields=None,
            )
            contracts.append(contract)
    except Exception as e:
        print(f"Error processing row {ext_id}: {e}")
    return contracts
