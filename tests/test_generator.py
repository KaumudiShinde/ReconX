from decimal import Decimal
from datetime import date
from reconx.generator import SyntheticDataGenerator


def test_generator_structure_and_counts():
    gen = SyntheticDataGenerator(seed=42, base_count=100)
    internal, bank_oct, bank_all, metadata = gen.generate()

    assert len(internal) >= 100
    assert len(bank_oct) > 0
    assert len(bank_all) >= len(bank_oct)
    
    # Verify metadata tracks all 4 planted gaps
    assert len(metadata["gap_1_following_month"]) > 0
    assert metadata["gap_2_rounding_drift"]["drift_amount"] > Decimal("0.00")
    assert len(metadata["gap_3_duplicate_internal"]) > 0
    assert len(metadata["gap_4_orphaned_refund"]) > 0


def test_gap1_has_november_settlements():
    gen = SyntheticDataGenerator(seed=42, base_count=50)
    _, _, bank_all, metadata = gen.generate()

    nov_records = [r for r in bank_all if r.settlement_date >= date(2026, 11, 1)]
    assert len(nov_records) >= len(metadata["gap_1_following_month"])


def test_gap3_duplicate_order_exists():
    gen = SyntheticDataGenerator(seed=42, base_count=50)
    internal, _, _, metadata = gen.generate()

    dup_meta = metadata["gap_3_duplicate_internal"][0]
    matching_txns = [tx for tx in internal if tx.order_id == dup_meta["order_id"]]
    assert len(matching_txns) == 2


def test_gap4_orphaned_refund_is_debit():
    gen = SyntheticDataGenerator(seed=42, base_count=50)
    _, bank_oct, _, metadata = gen.generate()

    orphan_meta = metadata["gap_4_orphaned_refund"][0]
    orphan_recs = [r for r in bank_oct if r.settlement_id == orphan_meta["settlement_id"]]
    assert len(orphan_recs) == 1
    assert orphan_recs[0].type == "DEBIT"
    assert orphan_recs[0].settled_net < Decimal("0.00")

