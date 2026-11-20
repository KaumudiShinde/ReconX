from datetime import date
from decimal import Decimal
from reconx.generator import SyntheticDataGenerator
from reconx.engine import ReconciliationEngine
from reconx.models import DiscrepancyType
from reconx.parser import parse_internal_csv, parse_bank_csv


def test_reconciliation_detects_all_4_gaps():
    gen = SyntheticDataGenerator(seed=42, base_count=200, plant_gaps=True)
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
    gen = SyntheticDataGenerator(seed=123, base_count=500, plant_gaps=True)
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


def test_clean_control_group_zero_gaps():
    """Verifies that when plant_gaps=False, 100% of transactions match cleanly."""
    gen = SyntheticDataGenerator(seed=77, base_count=150, plant_gaps=False)
    internal, bank_oct, bank_all, metadata = gen.generate()

    engine = ReconciliationEngine(cutoff_date=date(2026, 10, 31))
    records, summary = engine.reconcile(
        internal_txns=internal,
        bank_records=bank_oct,
        future_bank_records=bank_all,
    )

    assert summary.match_rate_pct == 100.0
    assert summary.matched_count == len(internal)
    assert summary.settled_following_month_count == 0
    assert summary.rounding_variance_count == 0
    assert summary.duplicate_internal_count == 0
    assert summary.orphaned_refund_count == 0
    assert summary.gross_variance == Decimal("0.00")
    assert summary.is_fully_explained is True


def test_flexible_csv_parser_and_inference():
    """Verifies that the parser handles non-standard column headers and calculates missing fees."""
    internal_csv = """Transaction ID,Order,Gross,Status
TXN_CUSTOM_01,ORD_991,100.00,SUCCESS
TXN_CUSTOM_02,ORD_992,200.00,SUCCESS
"""
    bank_csv = """Bank Reference,Settlement Date,Settled Amount,Fee,Net Amount
TXN_CUSTOM_01,2026-10-10,100.00,2.15,97.85
TXN_CUSTOM_02,2026-10-11,200.00,4.30,195.70
"""
    parsed_internal = parse_internal_csv(internal_csv)
    parsed_bank = parse_bank_csv(bank_csv)

    assert len(parsed_internal) == 2
    assert len(parsed_bank) == 2
    assert parsed_internal[0].gross_amount == Decimal("100.00")
    assert parsed_internal[0].expected_fee == Decimal("2.15")  # inferred automatically
    assert parsed_bank[1].bank_fee == Decimal("4.30")

    engine = ReconciliationEngine(cutoff_date=date(2026, 10, 31))
    records, summary = engine.reconcile(parsed_internal, parsed_bank)
    assert summary.matched_count == 2
    assert summary.match_rate_pct == 100.0
