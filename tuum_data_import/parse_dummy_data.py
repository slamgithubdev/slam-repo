import json
import os
import random
import string
from datetime import datetime, timedelta, timezone

import polars as pl
from dateutil.relativedelta import relativedelta


def parse_validity_range(years, months):
    today = datetime.today()
    past_date = today - timedelta(days=years * 365 + months * 30)
    return past_date.strftime("%Y-%m-%d")


def generate_id_number(length=11):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def generate_schedule_lines_simple(end_date_str, principal, currency="GBP"):
    """
    Generates a single schedule line with total principal amount on the end date.

    Args:
        end_date_str (str): Final payment date in 'YYYY-MM-DD' format.
        principal (float): Total loan principal amount.
        currency (str): Currency code.

    Returns:
        List[dict]: Single-item list with the schedule line.
    """
    return [
        {
            "componentTypeCode": "PRI",
            "paymentMoney": {
                "amount": round(principal, 2),
                "currencyCode": currency,
            },
            "paymentDate": end_date_str,
        }
    ]


def map_person(row):
    addresses = []
    try:
        address_list = json.loads(row.get("AddressHistory", "[]"))
        for addr in address_list:
            street = addr.get("STREET1") or addr.get("STREET2") or "UNKNOWN STREET"
            country = "GB"
            address_obj = {
                "addressTypeCode": "R",
                "street1": street,
                "street2": "",
                "cityCounty": addr.get("POSTTOWN", ""),
                "stateRegion": addr.get("COUNTY", ""),
                "zip": addr.get("POSTCODE", ""),
                "countryCode": country,
                "moveInDate": parse_validity_range(
                    addr.get("YEARS_AT", 0), addr.get("MONTHS_AT", 0)
                ),
                "validityRange": {
                    "startTime": datetime.now(timezone.utc).isoformat(),
                    "endTime": datetime.now(timezone.utc).isoformat(),
                },
            }
            addresses.append(address_obj)
    except Exception:
        addresses = []

    ext_id = row.get("SurrogateKey") or "UNKNOWN-ID"
    id_number = generate_id_number()
    phone_cc_raw = row.get("phone_country_code")
    phone_cc = (
        phone_cc_raw.strip()
        if phone_cc_raw and isinstance(phone_cc_raw, str)
        else "+44"
    )

    phone_num = row.get("phone_number") or "0000000000"

    identification_numbers = [
        {
            "idNumber": id_number,
            "idCountryCode": "GB",
            "primary": True,
            "validityRange": {
                "startTime": datetime.now(timezone.utc).isoformat(),
                "endTime": datetime.now(timezone.utc).isoformat(),
            },
        }
    ]

    person = {
        "externalPersonId": ext_id,
        "source": {
            "sourceName": "MY-CUSTOMER-DB",
            "sourceRef": ext_id,
        },
        "personTypeCode": "P",
        "givenName": row.get("given_name", ""),
        "middleName": "",
        "surname": row.get("surname", ""),
        "name": row.get("short_name", ""),
        "birthDate": row.get("birth_date", ""),
        "email": row.get("email", ""),
        "phoneNumberCountryCode": phone_cc,
        "phoneNumber": phone_num,
        "addresses": addresses,
        "identificationNumbers": identification_numbers,
    }
    return person


def map_agreement(row):
    contracts = []
    try:
        ext_id = row.get("SurrogateKey")
        agreements = json.loads(row.get("AgreementHistory", "[]"))
        for agreement in agreements:
            term = agreement.get("TERM", 0)
            payment = agreement.get("PAYMENT", 0)
            principal = agreement.get("AMOUNT_FINANCED", 0)

            start_date = agreement.get("CREATION_SYSTEM_DATE", "")[:10]

            # Calculate end_date as start_date + term months, or take from data if available
            end_date_obj = datetime.strptime(start_date, "%Y-%m-%d") + relativedelta(
                months=term
            )
            end_date = end_date_obj.strftime("%Y-%m-%d")

            schedule_lines = generate_schedule_lines_simple(end_date, principal)

            components = [
                {
                    "componentTypeCode": "PRI",
                    "paymentInterval": 1,
                    "balanceMoney": {"amount": principal, "currencyCode": "GBP"},
                    "invoicedBalanceMoney": {"amount": 0, "currencyCode": "GBP"},
                },
                {
                    "componentTypeCode": "ALIM",
                    "balanceMoney": {"amount": 0, "currencyCode": "GBP"},
                    "invoicedBalanceMoney": {"amount": 0, "currencyCode": "GBP"},
                },
                {
                    "componentTypeCode": "INT",
                    "paymentInterval": 1,
                    "balanceMoney": {"amount": 0, "currencyCode": "GBP"},
                    "invoicedBalanceMoney": {"amount": 0, "currencyCode": "GBP"},
                    "calculationMethod": {"daysInMonth": "ACT", "daysInYear": "365"},
                    "rateTypeCode": "FIXED",
                    "rate": agreement.get("APR", 0),
                    "rateBaseCode": None,
                    "marginRate": 0,
                    "baseRate": 0,
                },
            ]

            contract = {
                "externalPersonId": ext_id,
                "tuumPersonId": None,
                "externalContractId": ext_id,
                "source": {
                    "sourceName": "MY-CONTRACT-DB",
                    "sourceRef": ext_id,
                },
                "contractNumber": ext_id,
                "loanTypeCode": "BF_DEMO_2",
                "referenceNumber": None,
                "preparationDate": start_date,
                "signingDate": start_date,
                "startDate": start_date,
                "activationDate": start_date,
                "endDate": end_date,
                "stopDate": None,
                "statusCode": "ACTIVE",
                "period": term,
                "apr": agreement.get("APR"),
                "scheduleTypeCode": "ANNUITY",
                "limitMoney": {"amount": principal, "currencyCode": "GBP"},
                "contractFeeMoney": None,
                "contractMoney": {"amount": principal, "currencyCode": "GBP"},
                "countryCode": "GB",
                "tenantCode": "MB",
                "solvencyLevelCode": None,
                "externalServicingAccountId": None,
                "repayment": {
                    "paymentFreeMonths": None,
                    "monthlyRepaymentAmount": {
                        "amount": payment,
                        "currencyCode": "GBP",
                    },
                    "monthlyRepaymentRate": None,
                    "maxInvoiceMoney": None,
                    "minInvoiceMoney": None,
                    "invoiceDay": None,
                    "paymentDay": 1,
                    "previousInvoiceDate": (
                        datetime.strptime(start_date, "%Y-%m-%d")
                        + relativedelta(months=1)
                    )
                    .replace(day=1)
                    .strftime("%Y-%m-%d"),
                },
                "hasCollateral": False,
                "initialLtv": None,
                "currentLtv": None,
                "limitUsageDate": None,
                "penaltyGraceDays": None,
                "penaltyGraceMoney": None,
                "repaymentChannelCode": "PAYMENT_ROUTER_WITH_IBAN",
                "contractConditions": None,
                "components": components,
                "coBorrowers": None,
                "scheduleLines": schedule_lines,
                "customFields": None,
            }
            contracts.append(contract)
    except Exception as e:
        print(f"Error processing row {ext_id}: {e}")
    return contracts


def chunks(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def main():
    person_folder = "person_chunks"
    contract_folder = "contract_chunks"
    os.makedirs(person_folder, exist_ok=True)
    os.makedirs(contract_folder, exist_ok=True)

    file_path = (
        r"C:\Users\Danesh.Paul\Documents\tuum-data-migration\tuum_data_import\top50.csv"
    )
    df = pl.read_csv(
        file_path, null_values=["NULL", "null"], truncate_ragged_lines=True
    )

    persons = [map_person(row) for row in df.iter_rows(named=True)]
    contracts = []
    for row in df.iter_rows(named=True):
        contracts.extend(map_agreement(row))

    chunk_size = 2

    for idx, chunk in enumerate(chunks(persons, chunk_size), 1):
        with open(
            os.path.join(person_folder, f"person_{idx}.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(chunk, f, indent=2)

    for idx, chunk in enumerate(chunks(contracts, chunk_size), 1):
        with open(
            os.path.join(contract_folder, f"contract_{idx}.json"), "w", encoding="utf-8"
        ) as f:
            json.dump({"contracts": chunk}, f, indent=2)


if __name__ == "__main__":
    main()
