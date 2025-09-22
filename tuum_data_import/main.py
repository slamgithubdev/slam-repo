import json
from datetime import datetime, timedelta

import polars as pl


def parse_validity_range(years, months):
    today = datetime.today()
    move_in_date = today - timedelta(days=(years * 365 + months * 30))
    return move_in_date.strftime("%Y-%m-%d")


def map_row_to_person(row):
    addresses = []
    try:
        raw_addresses = row.get("AddressHistory", "[]")
        addr_list = json.loads(raw_addresses)
        for addr in addr_list:
            addr_obj = {
                "addressTypeCode": "R",
                "street1": addr.get("STREET2", ""),
                "street2": "",
                "cityCounty": addr.get("POSTTOWN", ""),
                "stateRegion": addr.get("COUNTY", ""),
                "zip": addr.get("POSTCODE", ""),
                "countryCode": "",
                "moveInDate": parse_validity_range(
                    addr.get("YEARS_AT", 0), addr.get("MONTHS_AT", 0)
                ),
                "validityRange": {
                    "startTime": datetime.utcnow().isoformat() + "Z",
                    "endTime": datetime.utcnow().isoformat() + "Z",
                },
            }
            addresses.append(addr_obj)
    except Exception:
        addresses = []

    person = {
        "externalPersonId": row.get("IBC_REF", ""),
        "source": {"sourceName": "MY-CUSTOMER-DB", "sourceRef": row.get("IBC_REF", "")},
        "personTypeCode": "P",
        "givenName": row.get("given_name", ""),
        "middleName": "",
        "surname": row.get("surname", ""),
        "name": row.get("short_name", ""),
        "birthDate": row.get("birth_date", ""),
        "email": row.get("email", ""),
        "phoneNumberCountryCode": row.get("phone_country_code", ""),
        "phoneNumber": row.get("phone_number", ""),
        "addresses": addresses,
    }
    return person


def chunked_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i : i + chunk_size]


if __name__ == "__main__":
    file_path = r"C:\Users\Danesh.Paul\Documents\tuum-data-migration\tuum_data_import\sql_results_anon.csv"
    df = pl.read_csv(file_path, null_values=["NULL", "null"])
    persons = [map_row_to_person(row) for row in df.iter_rows(named=True)]

    chunk_size = 50
    for idx, chunk in enumerate(chunked_list(persons, chunk_size), 1):
        output_json = {
            "source": {
                "sourceName": "Vienna-Dummy-Data",
                "sourceRef": "DAN-TEST-IMPORT-001",
            },
            "persons": chunk,
            "contracts": [],
            "accounts": [],
            "transactions": [],
        }
        filename = f"output_{idx}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(output_json, f, indent=2)

    print(
        f"Created {((len(persons) - 1) // chunk_size) + 1} output files with {chunk_size} persons each."
    )
