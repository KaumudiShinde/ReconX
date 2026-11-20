import csv
import io
from datetime import datetime, date
from decimal import Decimal
from typing import List, Union
from reconx.models import InternalTransaction, BankSettlementRecord


def parse_internal_csv(content: Union[str, bytes, io.StringIO, io.BytesIO]) -> List[InternalTransaction]:
    """Parses internal transactions CSV content into InternalTransaction domain models."""
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    if isinstance(content, str):
        stream = io.StringIO(content)
    else:
        stream = content

    reader = csv.DictReader(stream)
    records = []
    for row in reader:
        # Handle timestamp parsing
        ts_str = row.get("timestamp", "").strip()
        try:
            ts = datetime.fromisoformat(ts_str)
        except Exception:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")

        gross = Decimal(str(row.get("gross_amount", "0.00")).strip())
        expected_fee = Decimal(str(row.get("expected_fee", "0.00")).strip())
        expected_net = Decimal(str(row.get("expected_net", "0.00")).strip())

        records.append(
            InternalTransaction(
                transaction_id=str(row.get("transaction_id", "")).strip(),
                order_id=str(row.get("order_id", "")).strip(),
                customer_id=str(row.get("customer_id", "")).strip(),
                timestamp=ts,
                type=str(row.get("type", "PAYMENT")).strip(),
                gross_amount=gross,
                expected_fee=expected_fee,
                expected_net=expected_net,
                status=str(row.get("status", "SUCCESS")).strip(),
            )
        )
    return records


def parse_bank_csv(content: Union[str, bytes, io.StringIO, io.BytesIO]) -> List[BankSettlementRecord]:
    """Parses bank settlement CSV content into BankSettlementRecord domain models."""
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    if isinstance(content, str):
        stream = io.StringIO(content)
    else:
        stream = content

    reader = csv.DictReader(stream)
    records = []
    for row in reader:
        date_str = row.get("settlement_date", "").strip()
        try:
            stl_date = date.fromisoformat(date_str)
        except Exception:
            stl_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        gross = Decimal(str(row.get("settled_gross", "0.00")).strip())
        fee = Decimal(str(row.get("bank_fee", "0.00")).strip())
        net = Decimal(str(row.get("settled_net", "0.00")).strip())

        records.append(
            BankSettlementRecord(
                settlement_id=str(row.get("settlement_id", "")).strip(),
                bank_reference=str(row.get("bank_reference", "")).strip(),
                settlement_date=stl_date,
                type=str(row.get("type", "CREDIT")).strip(),
                settled_gross=gross,
                bank_fee=fee,
                settled_net=net,
                bank_status=str(row.get("bank_status", "SETTLED")).strip(),
            )
        )
    return records

