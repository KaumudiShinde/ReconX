import random
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
from typing import Tuple, List, Dict, Any
import os
import csv

from reconx.models import InternalTransaction, BankSettlementRecord


def round_curr(val: Decimal) -> Decimal:
    """Standard 2-decimal monetary rounding."""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class SyntheticDataGenerator:
    """
    Generates synthetic payment platform transactions and bank settlement records
    for a month-end reconciliation period (October 2026), planting the 4 required gaps:
      1. A transaction that settled the following month (Cutoff / Float lag)
      2. A rounding difference that only shows when summed (Sub-cent precision drift)
      3. A duplicate entry in one dataset (Webhook retry idempotency failure)
      4. A refund with no matching original transaction (Orphaned bank debit / clawback)
    """

    def __init__(self, seed: int = 42, base_count: int = 1000):
        self.seed = seed
        self.base_count = base_count
        self.fee_rate = Decimal("0.0215")  # 2.15% fee
        random.seed(seed)

    def generate(self) -> Tuple[List[InternalTransaction], List[BankSettlementRecord], List[BankSettlementRecord], Dict[str, Any]]:
        """
        Returns:
            internal_txns: List of internal transactions for October.
            bank_october: List of bank settlements dated in October.
            bank_all (including November roll-over): Complete bank records.
            metadata: Details of planted gaps for audit and assertions.
        """
        random.seed(self.seed)
        
        internal_txns: List[InternalTransaction] = []
        bank_records: List[BankSettlementRecord] = []
        
        # Metadata dictionary tracking exactly what we planted
        planted_metadata: Dict[str, Any] = {
            "gap_1_following_month": [],
            "gap_2_rounding_drift": {
                "individual_rounded_sum": Decimal("0.00"),
                "bank_actual_fee_sum": Decimal("0.00"),
                "drift_amount": Decimal("0.00"),
                "affected_tx_ids": [],
            },
            "gap_3_duplicate_internal": [],
            "gap_4_orphaned_refund": [],
        }

        # ---------------------------------------------------------
        # 1. Generate Clean Baseline Transactions (Oct 1 to Oct 28)
        # ---------------------------------------------------------
        # These will settle within October without any issue.
        base_date = date(2026, 10, 1)
        
        for i in range(1, self.base_count + 1):
            tx_id = f"TXN_202610_{i:04d}"
            order_id = f"ORD_{i:05d}"
            customer_id = f"CUST_{random.randint(100, 999)}"
            
            # Day between 1 and 28 so T+2 settles before Oct 31
            day_offset = random.randint(0, 27)
            tx_date = base_date + timedelta(days=day_offset)
            hour = random.randint(8, 22)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            tx_timestamp = datetime(tx_date.year, tx_date.month, tx_date.day, hour, minute, second)
            
            # Amount between $10.00 and $500.00
            gross_float = round(random.uniform(10.0, 500.0), 2)
            gross = Decimal(str(gross_float))
            
            # Fee calculation: 2.15%
            # Internal platform rounds fee per transaction using standard half-up
            expected_fee = round_curr(gross * self.fee_rate)
            expected_net = gross - expected_fee
            
            # Bank settlement happens T+1 or T+2 days later
            settlement_lag = random.choice([1, 2])
            stl_date = tx_date + timedelta(days=settlement_lag)
            stl_id = f"STL_202610_{i:04d}"
            
            # Bank fee calculation: For standard clean, bank matches expected fee
            bank_fee = expected_fee
            settled_net = gross - bank_fee
            
            internal_txns.append(
                InternalTransaction(
                    transaction_id=tx_id,
                    order_id=order_id,
                    customer_id=customer_id,
                    timestamp=tx_timestamp,
                    type="PAYMENT",
                    gross_amount=gross,
                    expected_fee=expected_fee,
                    expected_net=expected_net,
                    status="SUCCESS",
                )
            )
            
            bank_records.append(
                BankSettlementRecord(
                    settlement_id=stl_id,
                    bank_reference=tx_id,
                    settlement_date=stl_date,
                    type="CREDIT",
                    settled_gross=gross,
                    bank_fee=bank_fee,
                    settled_net=settled_net,
                    bank_status="SETTLED",
                )
            )

        # ---------------------------------------------------------
        # 2. Plant Gap 1: A transaction that settled the following month
        # ---------------------------------------------------------
        # These 2 transactions happen on Oct 31 right before midnight.
        # Bank settles on Nov 2 (T+2 after weekend).
        gap1_txns = [
            ("TXN_GAP1_OCT31_001", "ORD_99001", Decimal("350.00"), datetime(2026, 10, 31, 23, 15, 0), date(2026, 11, 2)),
            ("TXN_GAP1_OCT31_002", "ORD_99002", Decimal("180.50"), datetime(2026, 10, 31, 23, 50, 0), date(2026, 11, 2)),
        ]
        
        for tx_id, ord_id, gross, tx_time, stl_date in gap1_txns:
            fee = round_curr(gross * self.fee_rate)
            net = gross - fee
            
            internal_tx = InternalTransaction(
                transaction_id=tx_id,
                order_id=ord_id,
                customer_id="CUST_FLOAT",
                timestamp=tx_time,
                type="PAYMENT",
                gross_amount=gross,
                expected_fee=fee,
                expected_net=net,
                status="SUCCESS",
            )
            bank_rec = BankSettlementRecord(
                settlement_id=f"STL_{tx_id}",
                bank_reference=tx_id,
                settlement_date=stl_date,  # November 2nd!
                type="CREDIT",
                settled_gross=gross,
                bank_fee=fee,
                settled_net=net,
                bank_status="SETTLED",
            )
            
            internal_txns.append(internal_tx)
            bank_records.append(bank_rec)
            planted_metadata["gap_1_following_month"].append({
                "transaction_id": tx_id,
                "gross_amount": float(gross),
                "timestamp": tx_time.isoformat(),
                "settlement_date": stl_date.isoformat(),
            })

        # ---------------------------------------------------------
        # 3. Plant Gap 2: Rounding difference that ONLY shows when summed
        # ---------------------------------------------------------
        # Mathematical root cause:
        # Sum of per-item rounded fees != Fee calculated on aggregate batch total.
        # E.g., for 50 transactions, the exact unrounded fee is $X.XX5.
        # Internal platform rounds each one UP by 1 cent.
        # The bank's clearing batch aggregates gross first, then rounds,
        # or uses banker's rounding (round half to even).
        # To simulate this cleanly: on specific transactions, the sub-cent
        # fraction produces a $0.01 difference between internal half-up and
        # bank clearing house rounding.
        # When viewing any single transaction, a $0.01 fee difference is within
        # penny rounding, but when summed across all transactions, internal fees
        # diverge from bank fees by exactly the sum of drifted cents!
        rounding_drift_count = min(43, max(5, self.base_count // 10))
        eligible_indices = list(range(min(5, len(bank_records)), len(bank_records)))
        affected_indices = random.sample(eligible_indices, min(rounding_drift_count, len(eligible_indices)))

        for idx in affected_indices:
            # Shift bank fee by 1 cent on these items to reflect the aggregate rounding drift
            old_bank_fee = bank_records[idx].bank_fee
            new_bank_fee = old_bank_fee - Decimal("0.01")  # Bank charged 1 cent less due to aggregate truncation
            bank_records[idx].bank_fee = new_bank_fee
            bank_records[idx].settled_net = bank_records[idx].settled_gross - new_bank_fee

            planted_metadata["gap_2_rounding_drift"]["affected_tx_ids"].append(
                bank_records[idx].bank_reference
            )

        planted_metadata["gap_2_rounding_drift"]["drift_amount"] = Decimal(str(len(affected_indices) * 0.01))

        # ---------------------------------------------------------
        # 4. Plant Gap 3: Duplicate entry in one dataset
        # ---------------------------------------------------------
        # An internal transaction where a webhook retry caused the platform
        # to record the same customer payment twice.
        # The bank only processed and credited the payment ONCE.
        dup_gross = Decimal("145.00")
        dup_fee = round_curr(dup_gross * self.fee_rate)
        dup_net = dup_gross - dup_fee
        
        dup_original = InternalTransaction(
            transaction_id="TXN_GAP3_DUP_ORIGINAL",
            order_id="ORD_DUP_888",
            customer_id="CUST_DUP",
            timestamp=datetime(2026, 10, 15, 14, 20, 0),
            type="PAYMENT",
            gross_amount=dup_gross,
            expected_fee=dup_fee,
            expected_net=dup_net,
            status="SUCCESS",
        )
        # Duplicate record inserted with different or identical tx_id (webhook retry)
        dup_clone = InternalTransaction(
            transaction_id="TXN_GAP3_DUP_RETRY",
            order_id="ORD_DUP_888",  # Same order_id!
            customer_id="CUST_DUP",
            timestamp=datetime(2026, 10, 15, 14, 20, 0),
            type="PAYMENT",
            gross_amount=dup_gross,
            expected_fee=dup_fee,
            expected_net=dup_net,
            status="SUCCESS",
        )
        
        # Bank only has one settlement for this order
        dup_bank_rec = BankSettlementRecord(
            settlement_id="STL_GAP3_DUP_ORIGINAL",
            bank_reference="TXN_GAP3_DUP_ORIGINAL",
            settlement_date=date(2026, 10, 16),
            type="CREDIT",
            settled_gross=dup_gross,
            bank_fee=dup_fee,
            settled_net=dup_net,
            bank_status="SETTLED",
        )
        
        internal_txns.append(dup_original)
        internal_txns.append(dup_clone)
        bank_records.append(dup_bank_rec)
        
        planted_metadata["gap_3_duplicate_internal"].append({
            "original_tx_id": dup_original.transaction_id,
            "duplicate_tx_id": dup_clone.transaction_id,
            "order_id": "ORD_DUP_888",
            "duplicate_gross_amount": float(dup_gross),
        })

        # ---------------------------------------------------------
        # 5. Plant Gap 4: Refund with no matching original transaction
        # ---------------------------------------------------------
        # An orphaned bank debit: A customer dispute / chargeback or manual
        # bank clawback executed directly through the acquiring bank.
        # The platform database has NO corresponding transaction or refund.
        orphan_refund_amount = Decimal("85.00")
        orphan_bank_record = BankSettlementRecord(
            settlement_id="STL_GAP4_ORPHAN_REFUND_999",
            bank_reference="TXN_NONEXISTENT_ACQ_999",
            settlement_date=date(2026, 10, 20),
            type="DEBIT",
            settled_gross=Decimal("-85.00"),
            bank_fee=Decimal("0.00"),
            settled_net=Decimal("-85.00"),
            bank_status="ADJUSTMENT",
        )
        
        bank_records.append(orphan_bank_record)
        planted_metadata["gap_4_orphaned_refund"].append({
            "settlement_id": orphan_bank_record.settlement_id,
            "bank_reference": orphan_bank_record.bank_reference,
            "debit_amount": -85.00,
            "settlement_date": orphan_bank_record.settlement_date.isoformat(),
        })

        # Shuffle internal transactions to simulate natural chronological arrival
        internal_txns.sort(key=lambda x: x.timestamp)
        bank_records.sort(key=lambda x: x.settlement_date)

        # Separate bank records into October statement vs All (including November settlements)
        bank_october = [r for r in bank_records if r.settlement_date <= date(2026, 10, 31)]

        return internal_txns, bank_october, bank_records, planted_metadata


def save_datasets_to_csv(
    internal_txns: List[InternalTransaction],
    bank_records: List[BankSettlementRecord],
    output_dir: str = "data",
) -> Tuple[str, str]:
    """Saves generated records to CSV files."""
    os.makedirs(output_dir, exist_ok=True)
    
    internal_path = os.path.join(output_dir, "internal_transactions.csv")
    bank_path = os.path.join(output_dir, "bank_settlement.csv")
    
    # Save Internal Transactions
    with open(internal_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "transaction_id", "order_id", "customer_id", "timestamp",
            "type", "gross_amount", "expected_fee", "expected_net", "status"
        ])
        for tx in internal_txns:
            writer.writerow([
                tx.transaction_id, tx.order_id, tx.customer_id, tx.timestamp.isoformat(),
                tx.type, f"{tx.gross_amount:.2f}", f"{tx.expected_fee:.2f}",
                f"{tx.expected_net:.2f}", tx.status
            ])
            
    # Save Bank Settlement Records
    with open(bank_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "settlement_id", "bank_reference", "settlement_date", "type",
            "settled_gross", "bank_fee", "settled_net", "bank_status"
        ])
        for stl in bank_records:
            writer.writerow([
                stl.settlement_id, stl.bank_reference, stl.settlement_date.isoformat(),
                stl.type, f"{stl.settled_gross:.2f}", f"{stl.bank_fee:.2f}",
                f"{stl.settled_net:.2f}", stl.bank_status
            ])
            
    return internal_path, bank_path
