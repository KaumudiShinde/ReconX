# 📝 Submission Item 2: Distilled Prompt & Raw Prompt

This document contains the exact prompts used for the AI-assisted generation and execution of the **ReconX** payment reconciliation system.

---

## 1. Raw Prompt (Initial Unfiltered Request)

```text
The Problem:
A payments company's books don't balance at month end. They know every transaction their platform processed. They know what the bank says actually arrived. The two should match. They don't. Find out why. Show them where the gaps are.

Test Data:
No files provided. Generate your own — that's part of the assessment. A payments platform records a transaction instantly when a customer pays. The bank batches and settles funds 1–2 days later. At month end every transaction should have a matching settlement.
Plant these gap types: 
1. a transaction that settled the following month
2. a rounding difference that only shows when summed
3. a duplicate entry in one dataset
4. a refund with no matching original transaction.
State your assumptions. There are no wrong ones as long as you name them.

What to Build:
Build a complete reconciliation engine with a visual web dashboard, unit test suite, and balance sheet proofs that isolates every cent of variance and explains the root cause.
```

---

## 2. Distilled Prompt (Production-Grade Execution Prompt)

```text
Act as a Principal Fintech Systems Architect. Build a payment reconciliation engine named ReconX in Python with an interactive Streamlit web dashboard, a synthetic data generator planting 4 specific edge cases, a multi-pass matching engine, and a complete pytest suite.

### Requirements & Assumptions:
1. Scope: October 2026 month-end reconciliation. Platform transactions use UTC timestamps; bank settles on T+1 or T+2 business days with a 2.15% fee deducted from gross.
2. Financial Precision: Use Python Decimal with ROUND_HALF_UP (2 decimal places) for monetary amounts to prevent floating-point inaccuracies.
3. Synthetic Data Generator (SyntheticDataGenerator):
   - Baseline: 1,000 clean transactions with T+1/T+2 settlement dates and matching gross/fees.
   - Gap 1 (Timing Cutoff): Oct 31 transactions (TXN_GAP1_*) that settle on Nov 2 (unsettled in October statement).
   - Gap 2 (Rounding Drift): Sub-cent fee variance where individual per-transaction fee rounding diverges from aggregate batch fee calculation by $0.43 across 43 items when summed.
   - Gap 3 (Duplicate Entry): Internal webhook retry causing duplicate booking of ORD_DUP_888 ($145.00), while the bank settled only once.
   - Gap 4 (Orphaned Refund): Bank debit adjustment of -$85.00 with reference TXN_NONEXISTENT_ACQ_999 with zero internal counterpart.
4. Reconciliation Engine (ReconciliationEngine):
   - Multi-pass algorithm:
     * Pass 1: Duplicate internal entry detection by order_id grouping.
     * Pass 2: 1-to-1 match on transaction_id == bank_reference with fee-drift detection.
     * Pass 3: Month-end cutoff float detection against future settlement batches.
     * Pass 4: Orphaned bank debit/adjustment classification.
   - Mathematical Balance Invariance: Assert that Internal Gross - Duplicates - Next Month Settled + Orphaned Debits == Bank Gross down to $0.00 unexplained variance.
5. Interactive Web Dashboard (app.py):
   - Executive KPI cards (Gross volume, Cleared volume, Gross variance, Match rate %, Residual unexplained).
   - Plotly Waterfall balance walk chart illustrating the mathematical proof.
   - Deep-dive cards for each of the 4 planted gaps with root cause and recommended accounting fix.
   - Interactive data table with status filtering, reference search, and CSV export.
   - Formal audit sign-off report viewer with downloadable Markdown.
6. Test Suite (pytest):
   - Unit tests verifying generator constraints, detection of all 4 gap categories, and 100% mathematical balance sheet equality.
```

