from datetime import date
from decimal import Decimal
from reconx.generator import SyntheticDataGenerator
from reconx.engine import ReconciliationEngine
from reconx.models import DiscrepancyType


def test_reconciliation_detects_all_4_gaps():
    gen = SyntheticDataGenerator(seed=42, base_count=200)
    internal, bank_oct, bank_all, metadata = gen.generate()

    engine = ReconciliationEngine(cutoff_date=date(2026, 10, 31))
    records, summary = engine.reconcile(
        internal_txns=internal,
        bank_records=bank_oct,
        future_bank_records=bank_all,
    )

    # 1. Gap 1: Transaction that settled following month
    assert summary.settled_following_month_count == len(metadata["gap_1_following_month"])
    following_month_recs = [r for r in records if r.discrepancy_type == DiscrepancyType.SETTLED_FOLLOWING_MONTH]
    assert len(following_month_recs) == len(metadata["gap_1_following_month"])
    for r in following_month_recs:
        assert r.bank_record.settlement_date >= date(2026, 11, 1)

    # 2. Gap 2: Rounding difference that only shows when summed
    assert summary.rounding_variance_count > 0
    assert summary.rounding_fee_drift_amount == metadata["gap_2_rounding_drift"]["drift_amount"]
    rounding_recs = [r for r in records if r.discrepancy_type == DiscrepancyType.ROUNDING_VARIANCE]
    assert len(rounding_recs) == summary.rounding_variance_count

    # 3. Gap 3: Duplicate entry in internal dataset
    assert summary.duplicate_internal_count == 1
    dup_recs = [r for r in records if r.discrepancy_type == DiscrepancyType.DUPLICATE_INTERNAL]
    assert len(dup_recs) == 1
    assert dup_recs[0].internal_txn.order_id == "ORD_DUP_888"

    # 4. Gap 4: Refund with no matching original transaction
    assert summary.orphaned_refund_count == 1
    orphan_recs = [r for r in records if r.discrepancy_type == DiscrepancyType.ORPHANED_REFUND]
    assert len(orphan_recs) == 1
    assert orphan_recs[0].bank_record.settlement_id == "STL_GAP4_ORPHAN_REFUND_999"


def test_reconciliation_financial_mathematical_proof():
    """
    Verifies that the books are 100% balanced once the 4 gaps are identified:
    Internal Gross - Duplicates - Next Month Settled + Orphaned Debits == October Bank Gross
    """
    gen = SyntheticDataGenerator(seed=123, base_count=500)
    internal, bank_oct, bank_all, _ = gen.generate()

    engine = ReconciliationEngine(cutoff_date=date(2026, 10, 31))
    records, summary = engine.reconcile(
        internal_txns=internal,
        bank_records=bank_oct,
        future_bank_records=bank_all,
    )

    # Assert 100% mathematical invariance
    assert summary.is_fully_explained is True

    # Calculate exact equality
    reconstructed_bank_gross = (
        summary.total_internal_gross
        - summary.duplicate_internal_gross_amount
        - summary.following_month_gross_amount
        + summary.orphaned_refund_net_amount
    )
    assert reconstructed_bank_gross == summary.total_bank_gross

