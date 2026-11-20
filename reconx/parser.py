import csv
import io
import re
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Union, Dict, Any, Optional
from reconx.models import InternalTransaction, BankSettlementRecord


def _normalize_key(key: str) -> str:
    """Normalizes arbitrary column names (e.g., 'Gross Amount ($)' -> 'gross_amount')."""
    k = key.lower().strip()
    k = re.sub(r"[^\w\s]", "", k)
    k = re.sub(r"\s+", "_", k)
    return k


def _get_val(row_norm: Dict[str, Any], candidates: List[str], default: Any = None) -> Any:
    for c in candidates:
        if c in row_norm and row_norm[c] not in (None, ""):
            return row_norm[c]
    return default


def _parse_decimal(val: Any, default: str = "0.00") -> Decimal:
    if val is None or val == "":
        return Decimal(default)
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal(default)


def _parse_timestamp(val: Any) -> datetime:
    if not val:
        return datetime(2026, 10, 15, 12, 0, 0)
    s = str(val).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime(2026, 10, 15, 12, 0, 0)


def _parse_date(val: Any) -> date:
    if not val:
        return date(2026, 10, 15)
    s = str(val).strip()
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return date(2026, 10, 15)


def parse_internal_csv(content: Union[str, bytes, io.StringIO, io.BytesIO]) -> List[InternalTransaction]:
    """Parses internal transactions CSV content with resilient header mapping."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    if isinstance(content, str):
        stream = io.StringIO(content)
    else:
        stream = content

    reader = csv.DictReader(stream)
    records = []
    row_idx = 1

    for row in reader:
        row_norm = {_normalize_key(k): v for k, v in row.items() if k}
        
        tx_id = _get_val(row_norm, ["transaction_id", "tx_id", "txn_id", "id", "reference_id"], f"TXN_{row_idx:05d}")
        order_id = _get_val(row_norm, ["order_id", "order", "ord_id"], f"ORD_{row_idx:05d}")
        customer_id = _get_val(row_norm, ["customer_id", "customer", "cust_id", "user_id"], "CUST_DEFAULT")
        ts = _parse_timestamp(_get_val(row_norm, ["timestamp", "date", "created_at", "datetime", "tx_date"]))
        tx_type = _get_val(row_norm, ["type", "tx_type", "payment_type"], "PAYMENT")
        
        gross = _parse_decimal(_get_val(row_norm, ["gross_amount", "gross", "amount", "settled_gross", "value"]))
        
        # Calculate fee/net if not provided
        fee_raw = _get_val(row_norm, ["expected_fee", "fee", "processing_fee", "bank_fee"])
        if fee_raw is not None and fee_raw != "":
            expected_fee = _parse_decimal(fee_raw)
        else:
            expected_fee = (gross * Decimal("0.0215")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
        net_raw = _get_val(row_norm, ["expected_net", "net", "net_amount", "settled_net"])
        if net_raw is not None and net_raw != "":
            expected_net = _parse_decimal(net_raw)
        else:
            expected_net = gross - expected_fee
            
        status = _get_val(row_norm, ["status", "state", "tx_status"], "SUCCESS")

        records.append(
            InternalTransaction(
                transaction_id=str(tx_id),
                order_id=str(order_id),
                customer_id=str(customer_id),
                timestamp=ts,
                type=str(tx_type),
                gross_amount=gross,
                expected_fee=expected_fee,
                expected_net=expected_net,
                status=str(status),
            )
        )
        row_idx += 1

    return records


def parse_bank_csv(content: Union[str, bytes, io.StringIO, io.BytesIO]) -> List[BankSettlementRecord]:
    """Parses bank settlement CSV content with resilient header mapping."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    if isinstance(content, str):
        stream = io.StringIO(content)
    else:
        stream = content

    reader = csv.DictReader(stream)
    records = []
    row_idx = 1

    for row in reader:
        row_norm = {_normalize_key(k): v for k, v in row.items() if k}
        
        stl_id = _get_val(row_norm, ["settlement_id", "stl_id", "id", "bank_id"], f"STL_{row_idx:05d}")
        bank_ref = _get_val(row_norm, ["bank_reference", "reference", "bank_ref", "transaction_id", "tx_id"], f"REF_{row_idx:05d}")
        stl_date = _parse_date(_get_val(row_norm, ["settlement_date", "date", "clearing_date", "value_date"]))
        rec_type = _get_val(row_norm, ["type", "rec_type", "credit_debit"], "CREDIT")
        
        gross = _parse_decimal(_get_val(row_norm, ["settled_gross", "gross", "amount", "gross_amount"]))
        fee = _parse_decimal(_get_val(row_norm, ["bank_fee", "fee", "charges", "expected_fee"]))
        
        net_raw = _get_val(row_norm, ["settled_net", "net", "net_amount", "amount_settled"])
        if net_raw is not None and net_raw != "":
            settled_net = _parse_decimal(net_raw)
        else:
            settled_net = gross - fee
            
        bank_status = _get_val(row_norm, ["bank_status", "status", "clearing_status"], "SETTLED")

        records.append(
            BankSettlementRecord(
                settlement_id=str(stl_id),
                bank_reference=str(bank_ref),
                settlement_date=stl_date,
                type=str(rec_type),
                settled_gross=gross,
                bank_fee=fee,
                settled_net=settled_net,
                bank_status=str(bank_status),
            )
        )
        row_idx += 1

    return records
