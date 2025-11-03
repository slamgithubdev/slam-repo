# main_parser.py

import csv
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from domain_config.contracts_config import (
    CONTRACT_CHUNK_FOLDER,
    CONTRACT_CHUNK_SIZE,
    LOG_FILE,
    LOG_LEVEL,
)
from domain_config.persons_config import CHUNK_SIZE as PERSON_CHUNK_SIZE
from domain_config.persons_config import PERSON_CHUNK_FOLDER
from domain_mapper.contracts_mapper import map_agreement
from domain_mapper.persons_mapper import map_person

# ═══════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ═══════════════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    "[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
console_handler.setFormatter(console_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)


def make_json_serializable(obj):
    """Recursively convert non-JSON-serializable objects"""
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, "__dict__"):
        return make_json_serializable(asdict(obj))
    else:
        return obj


def validate_pri_balance(contract_dict):
    """Validate PRI component balance equals sum of unprocessed PRI schedule lines"""
    pri_component = None
    for comp in contract_dict.get("components", []):
        if comp.get("componentTypeCode") == "PRI":
            pri_component = comp
            break

    if not pri_component:
        raise ValueError("PRI component not found")

    component_balance = Decimal(
        str(pri_component.get("balanceMoney", {}).get("amount", 0))
    )

    schedule_total = Decimal("0")
    for line in contract_dict.get("scheduleLines", []):
        if line.get("componentTypeCode") == "PRI" and not line.get("processed", True):
            schedule_total += Decimal(str(line["paymentMoney"]["amount"]))

    diff = abs(component_balance - schedule_total)
    if diff > Decimal("0.01"):
        raise ValueError(
            f"PRI Balance Mismatch: component={component_balance:.2f}, "
            f"future_schedules={schedule_total:.2f}, diff={diff:.2f}"
        )


def parse_csv_persons(csv_filepath):
    """Parse persons from CSV"""
    chunk_folder = Path(PERSON_CHUNK_FOLDER)
    chunk_folder.mkdir(parents=True, exist_ok=True)

    all_persons = []
    chunk_index = 1
    current_chunk = []
    processed_ids = set()  # Track to avoid duplicates

    logger.info("\n" + "=" * 70)
    logger.info("PARSING PERSONS")
    logger.info("=" * 70)

    try:
        with open(csv_filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row_idx, row in enumerate(reader):
                try:
                    person_id = row.get("IBCSurrogate")

                    # Skip if already processed (avoid duplicates)
                    if person_id in processed_ids:
                        continue

                    person = map_person(row)

                    if person:
                        processed_ids.add(person_id)
                        person_dict = make_json_serializable(asdict(person))
                        current_chunk.append(person_dict)
                        all_persons.append(person)

                        logger.debug(f"  ✓ Person: {person.externalPersonId}")

                        if len(current_chunk) >= PERSON_CHUNK_SIZE:
                            _write_persons_chunk(
                                chunk_folder, chunk_index, current_chunk
                            )
                            chunk_index += 1
                            current_chunk = []

                except Exception as e:
                    logger.warning(f"Error on person row {row_idx}: {e}")

        if current_chunk:
            _write_persons_chunk(chunk_folder, chunk_index, current_chunk)

    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_filepath}")
        return []
    except Exception as e:
        logger.error(f"Fatal error parsing persons: {e}", exc_info=True)
        return []

    logger.info(f"✓ Persons parsed: {len(all_persons)}")
    return all_persons


def parse_csv_contracts(csv_filepath):
    """Parse contracts from CSV"""
    chunk_folder = Path(CONTRACT_CHUNK_FOLDER)
    chunk_folder.mkdir(parents=True, exist_ok=True)

    all_contracts = []
    chunk_index = 1
    current_chunk = []

    logger.info("\n" + "=" * 70)
    logger.info("PARSING CONTRACTS")
    logger.info("=" * 70)

    try:
        with open(csv_filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row_idx, row in enumerate(reader):
                try:
                    logger.info(
                        f"\n[Row {row_idx}] Processing: {row.get('IBCSurrogate')}"
                    )

                    mapped_contracts = map_agreement(row)

                    for contract in mapped_contracts:
                        contract_dict = make_json_serializable(asdict(contract))

                        try:
                            validate_pri_balance(contract_dict)
                            logger.info(f"  ✓ Validation passed")
                        except ValueError as ve:
                            logger.error(f"  ✗ Validation failed: {ve}")
                            continue

                        current_chunk.append(contract_dict)
                        all_contracts.append(contract)

                        logger.info(
                            f"  ✓ Contract added: {contract.externalContractId}"
                        )

                    if len(current_chunk) >= CONTRACT_CHUNK_SIZE:
                        _write_contracts_chunk(chunk_folder, chunk_index, current_chunk)
                        chunk_index += 1
                        current_chunk = []

                except Exception as e:
                    logger.error(f"Error on row {row_idx}: {e}", exc_info=True)

        if current_chunk:
            _write_contracts_chunk(chunk_folder, chunk_index, current_chunk)

    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_filepath}")
        return []
    except Exception as e:
        logger.error(f"Fatal error parsing contracts: {e}", exc_info=True)
        return []

    logger.info(f"✓ Contracts parsed: {len(all_contracts)}")
    return all_contracts


def _write_persons_chunk(chunk_folder, chunk_index, chunk_data):
    """Write persons chunk to JSON file"""
    chunk_file = chunk_folder / f"persons_{chunk_index:04d}.json"

    try:
        output = {"persons": chunk_data}

        with open(chunk_file, "w", encoding="utf-8") as cf:
            json.dump(output, cf, indent=2, default=str)

        logger.info(
            f"✓ Persons chunk written: {chunk_file} ({len(chunk_data)} persons)"
        )

    except Exception as e:
        logger.error(f"Error writing persons chunk {chunk_index}: {e}", exc_info=True)


def _write_contracts_chunk(chunk_folder, chunk_index, chunk_data):
    """Write contracts chunk to JSON file"""
    chunk_file = chunk_folder / f"contracts_{chunk_index:04d}.json"

    try:
        output = {"contracts": chunk_data}

        with open(chunk_file, "w", encoding="utf-8") as cf:
            json.dump(output, cf, indent=2, default=str)

        logger.info(
            f"✓ Contracts chunk written: {chunk_file} ({len(chunk_data)} contracts)"
        )

    except Exception as e:
        logger.error(f"Error writing contracts chunk {chunk_index}: {e}", exc_info=True)


def main():
    """Main entry point - processes persons and contracts"""
    csv_file = "anon_data_attempt1.csv"

    if not os.path.exists(csv_file):
        logger.error(f"✗ CSV file not found: {csv_file}")
        return

    logger.info("=" * 70)
    logger.info("TUUM DATA MIGRATION PARSER")
    logger.info("=" * 70)
    logger.info(f"CSV file: {os.path.abspath(csv_file)}")
    logger.info(f"Persons output: {os.path.abspath(PERSON_CHUNK_FOLDER)}")
    logger.info(f"Contracts output: {os.path.abspath(CONTRACT_CHUNK_FOLDER)}")
    logger.info(f"Log file: {os.path.abspath(LOG_FILE)}")

    # Parse persons first
    persons = parse_csv_persons(csv_file)

    # Parse contracts
    contracts = parse_csv_contracts(csv_file)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("IMPORT SUMMARY")
    logger.info("=" * 70)
    logger.info(f"✓ Persons parsed: {len(persons)}")
    logger.info(f"✓ Contracts parsed: {len(contracts)}")
    logger.info(f"✓ Output folder (persons): {os.path.abspath(PERSON_CHUNK_FOLDER)}")
    logger.info(
        f"✓ Output folder (contracts): {os.path.abspath(CONTRACT_CHUNK_FOLDER)}"
    )
    logger.info(f"✓ Log file: {os.path.abspath(LOG_FILE)}")
    logger.info("=" * 70 + "\n")


if __name__ == "__main__":
    main()
