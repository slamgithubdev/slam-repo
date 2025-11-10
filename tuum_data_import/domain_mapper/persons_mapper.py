import json
import random
import string
from dataclasses import asdict, is_dataclass
from datetime import datetime

from dateutil.relativedelta import relativedelta
from dateutil.tz import tzutc

from domain_config.persons_config import (
    ADDRESS_TYPE_CODE,
    COUNTRY_CODE,
    PERSON_TYPE_CODE,
    PHONE_DEFAULT_CC,
    SOURCE_NAME_PERSON,
)
from domain_dataclass.persons_dataclass import (
    Address,
    Employment,
    IdentificationNumber,
    Person,
    Source,
    ValidityRange,
)
from utils.utils import replace_prefix_with_timestamp


def iso_now_utc():
    return datetime.now(tz=tzutc()).isoformat()


def generate_id_number(length=11):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def parse_validity_dates():
    now_iso = iso_now_utc()
    return ValidityRange(startTime=now_iso, endTime=now_iso)


def parse_validity_range(years, months):
    today = datetime.today()
    past_date = today - relativedelta(years=years, months=months)
    return past_date.strftime("%Y-%m-%d")


def map_address_list(address_json_str):
    addresses = []
    try:
        addr_list = json.loads(address_json_str)
        for addr in addr_list:
            move_in_date_str = parse_validity_range(
                addr.get("YEARS_AT", 0), addr.get("MONTHS_AT", 0)
            )
            street = addr.get("STREET1") or addr.get("STREET2") or "UNKNOWN STREET"
            address = Address(
                addressTypeCode=ADDRESS_TYPE_CODE,
                street1=street,
                street2="",
                cityCounty=addr.get("POSTTOWN", ""),
                stateRegion=addr.get("COUNTY", ""),
                zip=addr.get("POSTCODE", ""),
                countryCode=COUNTRY_CODE,
                moveInDate=move_in_date_str,
                validityRange=parse_validity_dates(),
            )
            addresses.append(address)
    except Exception:
        addresses = []
    return addresses


def map_identification_numbers(ext_id):
    id_num = ext_id[-12:] if ext_id and len(ext_id) >= 12 else generate_id_number()
    transformed_id_num = replace_prefix_with_timestamp(id_num)
    validity = parse_validity_dates()
    return [
        IdentificationNumber(
            idNumber=transformed_id_num,
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
    transformed_ext_id = replace_prefix_with_timestamp(ext_id)

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
        externalPersonId=transformed_ext_id,
        source=Source(sourceName=SOURCE_NAME_PERSON, sourceRef=ext_id),
        personTypeCode=PERSON_TYPE_CODE,
        givenName=person_info.get("given_name", ""),
        middleName="",
        surname=person_info.get("surname", ""),
        name="",
        birthDate=person_info.get("birth_date", ""),
        email=contact_info.get("email", ""),
        phoneNumberCountryCode=phone_cc,
        phoneNumber=contact_info.get("masked_phone", ""),
        addresses=map_address_list(row.get("MaskedAddressHistory", "[]")),
        identificationNumbers=map_identification_numbers(ext_id),
        # employmentHistory=map_employment_history(row.get("EmploymentHistory", "[]")),
    )
    return person
