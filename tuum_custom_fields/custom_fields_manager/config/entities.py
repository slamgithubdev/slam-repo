"""
Entity registry - maps API modules to their available entities.
"""

from custom_fields_manager.config.settings import APIModule


ENTITY_REGISTRY = {
    "LOAN": {
        "module": APIModule.LOAN,
        "entities": [
            "LOAN.APPLICATION",
            "LOAN.CONTRACT_HEADER",
            "LOAN.LOAN_TYPE",
            "LOAN.OFFER",
            "LOAN.RECEIVABLE"
        ]
    },
    "RISK": {
        "module": APIModule.RISK,
        "entities": [
            "RISK.SCORING_DECISION",
            "RISK.SCORING_REQUEST"
        ]
    },
    "PERSON": {
        "module": APIModule.PERSON,
        "entities": [
            "PERSON.PERSON",
            "PERSON.PERSON_RELATIONSHIP"
        ]
    },
    "COLLATERAL": {
        "module": APIModule.COLLATERAL,
        "entities": [
            "COLLATERAL.ASSET",
            "COLLATERAL.COLLATERAL_AGREEMENT"
        ]
    },
    "PAYMENT": {
        "module": APIModule.PAYMENT,
        "entities": [
            "PAYMENT.PAYMENT"
        ]
    }
}
