from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class ValidityRange:
    startTime: str
    endTime: str


@dataclass
class Address:
    addressTypeCode: str
    street1: str
    street2: str
    cityCounty: str
    stateRegion: str
    zip: str
    countryCode: str
    moveInDate: str
    validityRange: ValidityRange


@dataclass
class IdentificationNumber:
    idNumber: str
    idCountryCode: str
    primary: bool
    validityRange: ValidityRange


@dataclass
class Source:
    sourceName: str
    sourceRef: str


@dataclass
class Employment:
    personId: str
    jobTitle: str
    employer: str
    yearsAt: int
    monthsAt: int


@dataclass
class Person:
    externalPersonId: str
    source: Source
    personTypeCode: str
    givenName: str
    middleName: str
    surname: str
    name: str
    birthDate: str
    email: str
    phoneNumberCountryCode: str
    phoneNumber: str
    addresses: List[Address] = field(default_factory=list)
    identificationNumbers: List[IdentificationNumber] = field(default_factory=list)
    # employmentHistory: List[Employment] = field(default_factory=list) # for later use, add as custom field
