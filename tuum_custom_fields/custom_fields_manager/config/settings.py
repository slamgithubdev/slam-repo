"""
Configuration settings for the Custom Fields Manager.
"""

from enum import Enum


class APIModule(Enum):
    """
    API modules with their full URLs.
    Currently only dev URLs are configured.
    """

    LOAN = {
        "dev": "https://Loan-api.billing-finance-dev.tuumplatform.com"
    }

    RISK = {
        "dev": "https://Risk-api.billing-finance-dev.tuumplatform.com"
    }

    PERSON = {
        "dev": "https://Person-api.billing-finance-dev.tuumplatform.com"
    }

    COLLATERAL = {
        "dev": "https://Collateral-api.billing-finance-dev.tuumplatform.com"
    }

    PAYMENT = {
        "dev": "https://Payment-api.billing-finance-dev.tuumplatform.com"
    }

    def get_url(self, env: str = "dev") -> str:
        """
        Get the URL for the specified environment.

        Args:
            env: Environment name (currently only 'dev' is configured)

        Returns:
            Full URL for the API
        """
        if env not in self.value:
            raise ValueError(
                f"Environment '{env}' not configured for {self.name}. "
                f"Available: {list(self.value.keys())}"
            )

        return self.value[env]


AUTH_URLS = {
    "dev": "https://auth-api.billing-finance-dev.tuumplatform.com/api/v1/employees/authorise"
}


def get_auth_url(env: str = "dev") -> str:
    """Get authentication URL for the environment"""
    if env not in AUTH_URLS:
        raise ValueError(
            f"Environment '{env}' not configured. Available: {list(AUTH_URLS.keys())}"
        )
    return AUTH_URLS[env]
