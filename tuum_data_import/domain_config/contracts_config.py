# domain_config/contracts_config.py

from datetime import datetime

COUNTRY_CODE = "GB"
TENANT_CODE = "MB"
LOAN_TYPE_CODE = "BF_DEMO_2"
CONTRACT_CHUNK_FOLDER = "./chunks_contracts"
CONTRACT_CHUNK_SIZE = 2
REPAYMENT_CHANNEL_CODE = "PAYMENT_ROUTER_WITH_IBAN"

# Logging
LOG_FILE = "parser_app.log"
LOG_LEVEL = "INFO"

# Import date (today)
IMPORT_DATE = datetime.now().date()
