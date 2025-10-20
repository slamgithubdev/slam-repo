import json
import os
import random
import string
from dataclasses import asdict, is_dataclass
from datetime import datetime

import polars as pl
from dateutil.relativedelta import relativedelta
from dateutil.tz import tzutc

from dataclass_person import (
    Address,
    Employment,
    IdentificationNumber,
    Person,
    Source,
    ValidityRange,
)
from domain_person_config import (
    ADDRESS_TYPE_CODE,
    CHUNK_SIZE,
    COUNTRY_CODE,
    PERSON_CHUNK_FOLDER,
    PERSON_TYPE_CODE,
    PHONE_DEFAULT_CC,
    SOURCE_NAME_PERSON,
)


def iso_now_utc():
    return datetime.now(tz=tzutc()).isoformat()


def generate_id_number(length=11):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def parse_validity_dates():
    now_iso = iso_now_utc()
    return ValidityRange(startTime=now_iso, endTime=now_iso)


def parse_validity_range(years, months):
    """
    Calculate a past date by subtracting given years and months from today's date.
    Args:
        years (int): Number of years to subtract.
        months (int): Number of months to subtract.
    Returns:
        str: Date string in 'YYYY-MM-DD' format representing the calculated past date.
    """
    today = datetime.today()
    past_date = today - relativedelta(years=years, months=months)
    return past_date.strftime("%Y-%m-%d")


def map_address_list(address_json_str):
    addresses = []
    try:
        addr_list = json.loads(address_json_str)
        for addr in addr_list:
            move_in_date = addr.get("YEARS_AT", 0)
            # Compute moveInDate as string; if months/years available, calculate proper date if required
            street = addr.get("STREET1") or addr.get("STREET2") or "UNKNOWN STREET"
            address = Address(
                addressTypeCode=ADDRESS_TYPE_CODE,
                street1=street,
                street2="",
                cityCounty=addr.get("POSTTOWN", ""),
                stateRegion=addr.get("COUNTY", ""),
                zip=addr.get("POSTCODE", ""),
                countryCode=COUNTRY_CODE,
                moveInDate=parse_validity_range(
                    addr.get("YEARS_AT", 0), addr.get("MONTHS_AT", 0)
                ),
                validityRange=parse_validity_dates(),
            )
            addresses.append(address)
    except Exception:
        addresses = []
    return addresses


def map_identification_numbers(ext_id):
    id_num = ext_id[-12:] if ext_id and len(ext_id) >= 12 else generate_id_number()
    validity = parse_validity_dates()
    return [
        IdentificationNumber(
            idNumber=id_num,
            idCountryCode=COUNTRY_CODE,
            primary=True,
            validityRange=validity,
        )
    ]


def map_employment_history(employment_json_str):
    employment_list = []
    try:
        data = json.loads(employment_json_str)
        for emp in data:
            employment_list.append(
                Employment(
                    personId=emp.get("Person_ID", ""),
                    jobTitle=emp.get("JOB TITLE", "").strip(),
                    employer=emp.get("EMPLOYER", "").strip(),
                    yearsAt=int(emp.get("YEARS_AT", 0)),
                    monthsAt=int(emp.get("MONTHS_AT", 0)),
                )
            )
    except Exception:
        employment_list = []
    return employment_list


def map_person(row):
    ext_id = row.get("IBCSurrogate") or "UNKNOWN-ID"

    # Parse nested JSON strings in columns
    person_info = {}
    contact_info = {}

    try:
        person_info = json.loads(row.get("MaskedPersonInfo", "{}"))
    except Exception:
        pass

    try:
        contact_info = json.loads(row.get("MaskedContactInfo", "{}"))
    except Exception:
        pass

    phone_cc_raw = contact_info.get("phone_country_code", PHONE_DEFAULT_CC)
    phone_cc = (
        phone_cc_raw.strip() if isinstance(phone_cc_raw, str) else PHONE_DEFAULT_CC
    )

    person = Person(
        externalPersonId=ext_id,  # based off surrogate key
        source=Source(
            sourceName=SOURCE_NAME_PERSON, sourceRef=ext_id
        ),  # based off surrogate key
        personTypeCode=PERSON_TYPE_CODE,
        givenName=person_info.get("given_name", ""),
        middleName="",
        surname=person_info.get("surname", ""),
        name=person_info.get("short_name", ""),
        birthDate=person_info.get("birth_date", ""),
        email=contact_info.get("email", ""),
        phoneNumberCountryCode=phone_cc,
        phoneNumber=contact_info.get("masked_phone", ""),
        addresses=map_address_list(row.get("MaskedAddressHistory", "[]")),
        identificationNumbers=map_identification_numbers(
            ext_id=ext_id
        ),  # Related to registration number or Social Security Number/Passport number etc. Currently based off last 12 digits of surrogate key.
        # employmentHistory=map_employment_history(row.get("EmploymentHistory", "[]")), add custom field
    )
    return person


def chunks(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def save_json_chunks(data_list, folder, prefix, chunk_size):
    os.makedirs(folder, exist_ok=True)
    for idx, chunk in enumerate(chunks(data_list, chunk_size), 1):
        serializable_chunk = [
            asdict(item) if is_dataclass(item) else item for item in chunk
        ]
        filename = os.path.join(folder, f"{prefix}_{idx}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(serializable_chunk, f, indent=2)


def main():
    file_path = r"C:\Users\Danesh.Paul\Documents\tuum-data-migration\tuum_data_import\anon_data_attempt1.csv"  # Set your actual CSV path here
    df = pl.read_csv(
        file_path, null_values=["NULL", "null"], truncate_ragged_lines=True
    )

    persons = [map_person(row) for row in df.iter_rows(named=True)]

    save_json_chunks(persons, PERSON_CHUNK_FOLDER, "person", CHUNK_SIZE)


if __name__ == "__main__":
    main()
