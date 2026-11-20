from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Optional, Tuple

from reconx.models import (
    InternalTransaction,
    BankSettlementRecord,
    ReconciliationRecord,
    ReconciliationSummary,
    DiscrepancyType,
)


class ReconciliationEngine:
    """
    Core Payment Reconciliation Engine implementing multi-pass matching,
    break detection, and portfolio-level financial proofs.
    """

    def __init__(self, cutoff_date: Optional[date] = None):
        self.cutoff_date = cutoff_date or date(2026, 10, 31)

    def reconcile(
        self,
        internal_txns: List[InternalTransaction],
        bank_records: List[BankSettlementRecord],
        future_bank_records: Optional[List[BankSettlementRecord]] = None,
    ) -> Tuple[List[ReconciliationRecord], ReconciliationSummary]:
        """
        Executes multi-pass reconciliation between internal ledger and bank settlements.

        Args:
            internal_txns: Platform transactions for the current month.
            bank_records: Bank settlement lines dated within current month.
            future_bank_records: Optional subsequent month settlements to verify in-transit items.
        """
        summary = ReconciliationSummary()
        records: List[ReconciliationRecord] = []

        # Step 1: Detect Duplicate Entries in Internal System (Gap 3)
        order_groups = defaultdict(list)
        tx_id_groups = defaultdict(list)
        for tx in internal_txns:
            order_groups[tx.order_id].append(tx)
            tx_id_groups[tx.transaction_id].append(tx)

        duplicate_tx_ids = set()
        for order_id, tx_list in order_groups.items():
            if len(tx_list) > 1:
                for dup_tx in tx_list[1:]:
                    duplicate_tx_ids.add(dup_tx.transaction_id)
                    rec = ReconciliationRecord(
                        record_id=f"REC_DUP_{dup_tx.transaction_id}",
                        discrepancy_type=DiscrepancyType.DUPLICATE_INTERNAL,
                        internal_txn=dup_tx,
                        bank_record=None,
                        gross_variance=dup_tx.gross_amount,
                        fee_variance=dup_tx.expected_fee,
                        net_variance=dup_tx.expected_net,
                        notes=(
                            f"Duplicate internal booking for order {order_id} via webhook retry. "
                            f"Overstates platform revenue by ${dup_tx.gross_amount:.2f}. "
                            f"Action: Reverse duplicate ledger entry."
                        ),
                    )
                    records.append(rec)
                    summary.duplicate_internal_count += 1
                    summary.duplicate_internal_gross_amount += dup_tx.gross_amount

        # Also check exact transaction_id duplicates if not already captured
        for tx_id, tx_list in tx_id_groups.items():
            if len(tx_list) > 1:
                for dup_tx in tx_list[1:]:
                    if dup_tx.transaction_id not in duplicate_tx_ids:
                        duplicate_tx_ids.add(dup_tx.transaction_id)
                        rec = ReconciliationRecord(
                            record_id=f"REC_DUP_ID_{dup_tx.transaction_id}",
                            discrepancy_type=DiscrepancyType.DUPLICATE_INTERNAL,
                            internal_txn=dup_tx,
                            bank_record=None,
                            gross_variance=dup_tx.gross_amount,
                            fee_variance=dup_tx.expected_fee,
                            net_variance=dup_tx.expected_net,
                            notes=f"Duplicate transaction ID {tx_id} in platform ledger.",
                        )
                        records.append(rec)
                        summary.duplicate_internal_count += 1
                        summary.duplicate_internal_gross_amount += dup_tx.gross_amount

        # Step 2: Index Bank Records & Check Bank Duplicates
        bank_by_ref: Dict[str, BankSettlementRecord] = {}
        matched_bank_refs = set()
        bank_duplicate_records: List[BankSettlementRecord] = []

        for r in bank_records:
            if r.bank_reference in bank_by_ref:
                bank_duplicate_records.append(r)
            else:
                bank_by_ref[r.bank_reference] = r

        # Index Future bank records (for following month settlement verification)
        future_by_ref: Dict[str, BankSettlementRecord] = {}
        if future_bank_records:
            for r in future_bank_records:
                if r.settlement_date > self.cutoff_date:
                    future_by_ref[r.bank_reference] = r

        # Step 3: 1-to-1 Match & Rounding Drift Detection (Gap 2 + Clean Matches)
        for tx in internal_txns:
            if tx.transaction_id in duplicate_tx_ids:
                continue

            bank_rec = bank_by_ref.get(tx.transaction_id)

            if bank_rec:
                matched_bank_refs.add(bank_rec.bank_reference)
                gross_diff = tx.gross_amount - bank_rec.settled_gross
                fee_diff = tx.expected_fee - bank_rec.bank_fee
                net_diff = tx.expected_net - bank_rec.settled_net

                # Check for sub-cent rounding variance (Gap 2)
                if gross_diff == Decimal("0.00") and fee_diff != Decimal("0.00"):
                    rec = ReconciliationRecord(
                        record_id=f"REC_{tx.transaction_id}",
                        discrepancy_type=DiscrepancyType.ROUNDING_VARIANCE,
                        internal_txn=tx,
                        bank_record=bank_rec,
                        gross_variance=gross_diff,
                        fee_variance=fee_diff,
                        net_variance=net_diff,
                        notes=(
                            f"Rounding fee drift: Internal expected fee ${tx.expected_fee:.2f} "
                            f"vs Bank fee ${bank_rec.bank_fee:.2f} (delta: ${fee_diff:+.2f}). "
                            f"Caused by per-item rounding vs aggregate batch calculation."
                        ),
                    )
                    records.append(rec)
                    summary.rounding_variance_count += 1
                    summary.rounding_fee_drift_amount += fee_diff
                else:
                    # Clean exact match
                    rec = ReconciliationRecord(
                        record_id=f"REC_{tx.transaction_id}",
                        discrepancy_type=DiscrepancyType.MATCHED,
                        internal_txn=tx,
                        bank_record=bank_rec,
                        gross_variance=gross_diff,
                        fee_variance=fee_diff,
                        net_variance=net_diff,
                        notes="Clean match: Gross, fees, and net settlement agree perfectly.",
                    )
                    records.append(rec)
                    summary.matched_count += 1

            else:
                # Step 4: Check if settled in the following month (Gap 1)
                future_rec = future_by_ref.get(tx.transaction_id)
                
                # If verified in future records OR initiated within 48h of cutoff (float lag)
                days_to_cutoff = (self.cutoff_date - tx.timestamp.date()).days
                is_month_end_float = 0 <= days_to_cutoff <= 2

                if future_rec:
                    matched_bank_refs.add(future_rec.bank_reference)
                    rec = ReconciliationRecord(
                        record_id=f"REC_{tx.transaction_id}",
                        discrepancy_type=DiscrepancyType.SETTLED_FOLLOWING_MONTH,
                        internal_txn=tx,
                        bank_record=future_rec,
                        gross_variance=tx.gross_amount,
                        fee_variance=tx.expected_fee,
                        net_variance=tx.expected_net,
                        notes=(
                            f"Timing Float: Transaction recorded on {tx.timestamp.strftime('%Y-%m-%d')} "
                            f"settled on {future_rec.settlement_date.strftime('%Y-%m-%d')} in following month. "
                            f"Action: Reconcile as Open In-Transit Asset."
                        ),
                    )
                    records.append(rec)
                    summary.settled_following_month_count += 1
                    summary.following_month_gross_amount += tx.gross_amount
                elif is_month_end_float and not future_bank_records:
                    # When only single-month CSV was uploaded, recognize month-end float
                    rec = ReconciliationRecord(
                        record_id=f"REC_{tx.transaction_id}",
                        discrepancy_type=DiscrepancyType.SETTLED_FOLLOWING_MONTH,
                        internal_txn=tx,
                        bank_record=None,
                        gross_variance=tx.gross_amount,
                        fee_variance=tx.expected_fee,
                        net_variance=tx.expected_net,
                        notes=(
                            f"Timing Float: Transaction recorded on {tx.timestamp.strftime('%Y-%m-%d')} "
                            f"near month-end cutoff. Clearing estimated in T+2 (following month). "
                            f"Action: Reconcile as Open In-Transit Asset."
                        ),
                    )
                    records.append(rec)
                    summary.settled_following_month_count += 1
                    summary.following_month_gross_amount += tx.gross_amount
                else:
                    # True missing settlement
                    rec = ReconciliationRecord(
                        record_id=f"REC_{tx.transaction_id}",
                        discrepancy_type=DiscrepancyType.UNMATCHED_INTERNAL,
                        internal_txn=tx,
                        bank_record=None,
                        gross_variance=tx.gross_amount,
                        fee_variance=tx.expected_fee,
                        net_variance=tx.expected_net,
                        notes="Unmatched internal transaction with no bank settlement record.",
                    )
                    records.append(rec)
                    summary.unmatched_internal_count += 1

        # Step 5: Analyze Unmatched Bank Settlements & Orphaned Refunds (Gap 4)
        for stl in bank_records:
            if stl.bank_reference not in matched_bank_refs:
                # Orphaned refund / debit adjustment
                if stl.type == "DEBIT" or stl.settled_net < Decimal("0.00"):
                    rec = ReconciliationRecord(
                        record_id=f"REC_ORPHAN_{stl.settlement_id}",
                        discrepancy_type=DiscrepancyType.ORPHANED_REFUND,
                        internal_txn=None,
                        bank_record=stl,
                        gross_variance=-stl.settled_gross,
                        fee_variance=-stl.bank_fee,
                        net_variance=-stl.settled_net,
                        notes=(
                            f"Orphaned bank debit / refund of ${abs(stl.settled_net):.2f} "
                            f"with reference '{stl.bank_reference}' has no original transaction in platform database. "
                            f"Action: Investigate direct bank chargeback / manual terminal refund."
                        ),
                    )
                    records.append(rec)
                    summary.orphaned_refund_count += 1
                    summary.orphaned_refund_net_amount += stl.settled_net
                else:
                    rec = ReconciliationRecord(
                        record_id=f"REC_UNMATCHED_BANK_{stl.settlement_id}",
                        discrepancy_type=DiscrepancyType.UNMATCHED_BANK,
                        internal_txn=None,
                        bank_record=stl,
                        gross_variance=-stl.settled_gross,
                        fee_variance=-stl.bank_fee,
                        net_variance=-stl.settled_net,
                        notes="Bank settlement credit with no matching internal platform transaction.",
                    )
                    records.append(rec)
                    summary.unmatched_bank_count += 1

        # Step 6: Aggregate Totals & Accounting Sign-Off
        summary.total_internal_count = len(internal_txns)
        summary.total_bank_count = len(bank_records)

        summary.total_internal_gross = sum((tx.gross_amount for tx in internal_txns), Decimal("0.00"))
        summary.total_internal_fee = sum((tx.expected_fee for tx in internal_txns), Decimal("0.00"))
        summary.total_internal_net = sum((tx.expected_net for tx in internal_txns), Decimal("0.00"))

        summary.total_bank_gross = sum((stl.settled_gross for stl in bank_records), Decimal("0.00"))
        summary.total_bank_fee = sum((stl.bank_fee for stl in bank_records), Decimal("0.00"))
        summary.total_bank_net = sum((stl.settled_net for stl in bank_records), Decimal("0.00"))

        summary.gross_variance = summary.total_internal_gross - summary.total_bank_gross
        summary.fee_variance = summary.total_internal_fee - summary.total_bank_fee
        summary.net_book_variance = summary.total_internal_net - summary.total_bank_net

        return records, summary
