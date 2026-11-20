from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional
from datetime import datetime, date


class DiscrepancyType(str, Enum):
    MATCHED = "MATCHED"
    SETTLED_FOLLOWING_MONTH = "SETTLED_FOLLOWING_MONTH"
    ROUNDING_VARIANCE = "ROUNDING_VARIANCE"
    DUPLICATE_INTERNAL = "DUPLICATE_INTERNAL"
    ORPHANED_REFUND = "ORPHANED_REFUND"
    UNMATCHED_INTERNAL = "UNMATCHED_INTERNAL"
    UNMATCHED_BANK = "UNMATCHED_BANK"

    @property
    def display_name(self) -> str:
        names = {
            self.MATCHED: "Clean Match",
            self.SETTLED_FOLLOWING_MONTH: "Settled Following Month (Timing Lag)",
            self.ROUNDING_VARIANCE: "Rounding Variance (Fee Drift)",
            self.DUPLICATE_INTERNAL: "Duplicate Internal Entry (Webhook Glitch)",
            self.ORPHANED_REFUND: "Orphaned Bank Refund (Missing Original)",
            self.UNMATCHED_INTERNAL: "Unmatched Internal Transaction",
            self.UNMATCHED_BANK: "Unmatched Bank Settlement",
        }
        return names.get(self, self.value)

    @property
    def badge_color(self) -> str:
        colors = {
            self.MATCHED: "green",
            self.SETTLED_FOLLOWING_MONTH: "blue",
            self.ROUNDING_VARIANCE: "orange",
            self.DUPLICATE_INTERNAL: "purple",
            self.ORPHANED_REFUND: "red",
            self.UNMATCHED_INTERNAL: "gray",
            self.UNMATCHED_BANK: "gray",
        }
        return colors.get(self, "gray")


@dataclass
class InternalTransaction:
    transaction_id: str
    order_id: str
    customer_id: str
    timestamp: datetime
    type: str  # PAYMENT, REFUND
    gross_amount: Decimal
    expected_fee: Decimal
    expected_net: Decimal
    status: str = "SUCCESS"

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "order_id": self.order_id,
            "customer_id": self.customer_id,
            "timestamp": self.timestamp.isoformat(),
            "type": self.type,
            "gross_amount": float(self.gross_amount),
            "expected_fee": float(self.expected_fee),
            "expected_net": float(self.expected_net),
            "status": self.status,
        }


@dataclass
class BankSettlementRecord:
    settlement_id: str
    bank_reference: str
    settlement_date: date
    type: str  # CREDIT, DEBIT
    settled_gross: Decimal
    bank_fee: Decimal
    settled_net: Decimal
    bank_status: str = "SETTLED"

    def to_dict(self) -> dict:
        return {
            "settlement_id": self.settlement_id,
            "bank_reference": self.bank_reference,
            "settlement_date": self.settlement_date.isoformat(),
            "type": self.type,
            "settled_gross": float(self.settled_gross),
            "bank_fee": float(self.bank_fee),
            "settled_net": float(self.settled_net),
            "bank_status": self.bank_status,
        }


@dataclass
class ReconciliationRecord:
    record_id: str
    discrepancy_type: DiscrepancyType
    internal_txn: Optional[InternalTransaction] = None
    bank_record: Optional[BankSettlementRecord] = None
    gross_variance: Decimal = Decimal("0.00")  # internal_gross - bank_gross
    fee_variance: Decimal = Decimal("0.00")    # expected_fee - bank_fee
    net_variance: Decimal = Decimal("0.00")    # expected_net - settled_net
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "status": self.discrepancy_type.value,
            "status_label": self.discrepancy_type.display_name,
            "internal_tx_id": self.internal_txn.transaction_id if self.internal_txn else None,
            "order_id": self.internal_txn.order_id if self.internal_txn else None,
            "internal_timestamp": self.internal_txn.timestamp.isoformat() if self.internal_txn else None,
            "internal_gross": float(self.internal_txn.gross_amount) if self.internal_txn else None,
            "internal_fee": float(self.internal_txn.expected_fee) if self.internal_txn else None,
            "internal_net": float(self.internal_txn.expected_net) if self.internal_txn else None,
            "bank_settlement_id": self.bank_record.settlement_id if self.bank_record else None,
            "bank_reference": self.bank_record.bank_reference if self.bank_record else None,
            "settlement_date": self.bank_record.settlement_date.isoformat() if self.bank_record else None,
            "bank_gross": float(self.bank_record.settled_gross) if self.bank_record else None,
            "bank_fee": float(self.bank_record.bank_fee) if self.bank_record else None,
            "bank_net": float(self.bank_record.settled_net) if self.bank_record else None,
            "gross_variance": float(self.gross_variance),
            "fee_variance": float(self.fee_variance),
            "net_variance": float(self.net_variance),
            "notes": self.notes,
        }


@dataclass
class ReconciliationSummary:
    # Volume & Counts
    total_internal_count: int = 0
    total_bank_count: int = 0
    matched_count: int = 0
    
    # Gap Counts
    settled_following_month_count: int = 0
    rounding_variance_count: int = 0
    duplicate_internal_count: int = 0
    orphaned_refund_count: int = 0
    unmatched_internal_count: int = 0
    unmatched_bank_count: int = 0
    
    # Financial Totals - Internal
    total_internal_gross: Decimal = Decimal("0.00")
    total_internal_fee: Decimal = Decimal("0.00")
    total_internal_net: Decimal = Decimal("0.00")
    
    # Financial Totals - Bank (October)
    total_bank_gross: Decimal = Decimal("0.00")
    total_bank_fee: Decimal = Decimal("0.00")
    total_bank_net: Decimal = Decimal("0.00")
    
    # Gaps Dollar Amounts
    following_month_gross_amount: Decimal = Decimal("0.00")
    rounding_fee_drift_amount: Decimal = Decimal("0.00")
    duplicate_internal_gross_amount: Decimal = Decimal("0.00")
    orphaned_refund_net_amount: Decimal = Decimal("0.00")
    
    # Variances
    net_book_variance: Decimal = Decimal("0.00")  # internal_net - bank_net
    gross_variance: Decimal = Decimal("0.00")     # internal_gross - bank_gross
    fee_variance: Decimal = Decimal("0.00")       # internal_fee - bank_fee

    @property
    def match_rate_pct(self) -> float:
        if self.total_internal_count == 0:
            return 0.0
        return round((self.matched_count / self.total_internal_count) * 100, 2)

    @property
    def is_fully_explained(self) -> bool:
        """Verifies if every cent of variance between internal and bank books is mathematically accounted for."""
        # Gross reconciliation check:
        # Internal Gross - Duplicate Gross - Settled Following Month Gross + Orphaned Bank Debits (negative) == Bank Gross
        explained_bank_gross = (
            self.total_internal_gross 
            - self.duplicate_internal_gross_amount 
            - self.following_month_gross_amount
            + Decimal(str(self.orphaned_refund_net_amount))
        )
        return (explained_bank_gross == self.total_bank_gross)

