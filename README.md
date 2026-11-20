# 💳 ReconX — Fintech Payment Settlement Reconciliation Engine

[![Tests](https://img.shields.io/badge/pytest-8%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)]()
[![Framework](https://img.shields.io/badge/UI-Streamlit%20Dark-1E293B.svg)]()

> **OneLab Internship Assessment Submission:**  
> *"A payments company's books don't balance at month end. They know every transaction their platform processed. They know what the bank says actually arrived. The two should match. They don't. Find out why. Show them where the gaps are."*

---

## 📑 Table of Contents
1. [Overview & Problem Statement](#overview--problem-statement)
2. [Explicit Assumptions Named](#explicit-assumptions-named)
3. [The 4 Planted Gaps (Forensic Root Cause Analysis)](#the-4-planted-gaps-forensic-root-cause-analysis)
4. [Mathematical Balance Sheet Walk (Reconciliation Proof)](#mathematical-balance-sheet-walk-reconciliation-proof)
5. [Automated Test Suite & Verification Results](#automated-test-suite--verification-results)
6. [What This Would Get Wrong in Production (The 3 Sentences)](#what-this-would-get-wrong-in-production-the-3-sentences)
7. [OneLab Submission Deliverables Mapping](#onelab-submission-deliverables-mapping)
8. [Local Quickstart & Deployment Guide](#local-quickstart--deployment-guide)
9. [Repository Structure](#repository-structure)

---

## 🏛️ Overview & Problem Statement

ReconX is a payment settlement reconciliation platform built in Python. It reconciles an internal platform payment transaction ledger against an external bank settlement file, isolates discrepancies, attributes each dollar of variance to an operational root cause, and generates automated double-entry journal entries to balance the books.

### System Pipeline:
```
ReconX Pipeline
  │
  ├── 1. Data Ingestion & Resilient Normalization
  │     ├── Multi-format timestamp and date parser
  │     ├── Flexible column header resolution (Gross, Amount, TxnID, etc.)
  │     └── Fixed-point Decimal precision (2 decimal places)
  │
  ├── 2. Multi-Pass Reconciliation Matching Engine
  │     ├── Pass 1: Duplicate internal entry & idempotency check (order_id & txn_id)
  │     ├── Pass 2: 1-to-1 exact matching with aggregate rounding drift detection
  │     ├── Pass 3: Month-end timing cutoff float detection (T+1/T+2 subsequent month)
  │     └── Pass 4: Orphaned bank debit adjustments & chargeback detection
  │
  ├── 3. Accounting Sign-Off & Journal Entries
  │     ├── Mathematical balance invariance proof ($0.00 unexplained residual)
  │     └── Automated General Ledger (GL) double-entry journal entries (Debits/Credits)
  │
  └── 4. Fintech Dark Dashboard UI
        ├── Overview, Analytics, Exception Explorer, Forensic Inspector
        └── General Ledger, Data Management, Documentation tabs
```

---

## 📋 Explicit Assumptions Named

1. **Reporting Horizon:** Monthly reconciliation cycle for October 2026 (`2026-10-01` to `2026-10-31 23:59:59 UTC`).
2. **Settlement Window (Float):** Standard acquiring bank clearing SLA is $T+1$ or $T+2$ business days. A transaction on Friday or month-end batches over the weekend and settles on the next banking day.
3. **Fee Deduction Model:** The bank settles transactions individually or in daily clearing batches with an associated processing fee (standard 2.15% per transaction) deducted from gross revenue (`Net = Gross - Fee`).
4. **Monetary Precision:** Implemented using fixed-point Python `Decimal` with standard `ROUND_HALF_UP` (2 decimal places) to completely eliminate IEEE 754 floating-point inaccuracies.
5. **Idempotency Standard:** Transactions sharing the same `order_id` in the internal ledger represent duplicate webhook delivery retries caused by network timeouts.

---

## 🔍 The 4 Planted Gaps (Forensic Root Cause Analysis)

| Gap Type | Operational Root Cause | Detection Strategy | Financial Accounting Resolution |
| :--- | :--- | :--- | :--- |
| **1. Settled Following Month** | Transactions on Oct 31 (`TXN_GAP1_OCT31_*`) settle on Nov 2 due to $T+2$ bank float. Platform recognized revenue in Oct; bank statements omitted it. | Transaction exists in internal ledger within 48h of cutoff; verified in subsequent clearing batch. | Reclassified as **Cash in Transit (Uncleared Deposits)** balance sheet asset. |
| **2. Rounding Difference When Summed** | Internal ledger rounds 2.15% fee per transaction: $\sum \text{round}(\text{gross} \times 2.15\%)$, while bank deducts fee on aggregate daily batch: $\text{round}(\sum \text{gross} \times 2.15\%)$. | Line items match gross, but cumulative portfolio fee diverges by $+\$0.43$ across 43 items ($|\Delta \text{fee}| \le \$0.05$). | Adjusting journal entry posted to **Payment Processing Fee Expense**. |
| **3. Duplicate Internal Entry** | Webhook retry / race condition double-inserted order `ORD_DUP_888` (`$145.00`), while customer card was only charged once at the bank. | Detected by grouping on `order_id` and identifying un-settled clone. | Redundant transaction marked for reversal from platform revenue ledger. |
| **4. Orphaned Bank Refund** | Direct bank chargeback / manual terminal refund (`-$85.00`) executed outside platform API (`TXN_NONEXISTENT_ACQ_999`). | Bank settlement debit (`STL_GAP4_*`) with zero internal transaction ID. | Reconciled as unlogged chargeback; ops ticket dispatched to Merchant Ops. |

---

## 🧮 Mathematical Balance Sheet Walk (Reconciliation Proof)

At month-end close (October 31, 2026), the gross variance between platform records and bank statements is **100% mathematically accounted for**:

$$\begin{aligned}
\text{Internal Platform Gross Volume} & = \$255,142.10 \\
(-) \text{ Webhook Duplicate Record (Gap 3)} & = -\$145.00 \\
(-) \text{ Month-End Timing Float Settled in Nov (Gap 1)} & = -\$530.50 \\
(+) \text{ Direct Bank Debit / Orphaned Refund (Gap 4)} & = -\$85.00 \\
\hline
\mathbf{\text{Reconciled Bank Settlement Gross}} & = \mathbf{\$254,381.60} \\
\mathbf{\text{Unexplained Residual Variance}} & = \mathbf{\$0.00 \quad (100\% \text{ Balanced})}
\end{aligned}$$

---

## 🧪 Automated Test Suite & Verification Results

All 8 tests pass in the automated `pytest` test suite:
```bash
python -m pytest tests -v
```

```text
============================= test session starts =============================
platform win32 -- Python 3.12.0, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\KAUMUDI\ReconX
collected 8 items

tests/test_engine.py::test_reconciliation_detects_all_4_gaps PASSED      [ 12%]
tests/test_engine.py::test_reconciliation_financial_mathematical_proof PASSED [ 25%]
tests/test_engine.py::test_clean_control_group_zero_gaps PASSED          [ 37%]
tests/test_engine.py::test_flexible_csv_parser_and_inference PASSED      [ 50%]
tests/test_generator.py::test_generator_structure_and_counts PASSED      [ 62%]
tests/test_generator.py::test_gap1_has_november_settlements PASSED       [ 75%]
tests/test_generator.py::test_gap3_duplicate_order_exists PASSED         [ 87%]
tests/test_generator.py::test_gap4_orphaned_refund_is_debit PASSED       [100%]

============================== 8 passed in 0.11s ==============================
```

---

## ⚠️ What This Would Get Wrong in Production (The 3 Sentences)

> 1. In high-volume production, an in-memory tabular comparison will suffer catastrophic out-of-memory (OOM) crashes and CPU bottlenecks because tier-1 payment gateways process hundreds of millions of daily events, necessitating a distributed stream-processing architecture (e.g. Apache Flink or DuckDB/ClickHouse window queries) with disk-backed state checkpoints rather than loading whole CSVs.
> 2. The engine assumes a clean 1-to-1 mapping between internal transaction IDs and bank settlement lines, whereas real-world acquiring banks settle via aggregated lump-sum batch wire payouts (many-to-one) that bundle thousands of sales, refunds, interchange tiers, rolling risk reserves, and chargeback penalties into a single net deposit.
> 3. It does not account for multi-currency foreign exchange (FX) settlement slippage, where the dynamic exchange rate locked at the moment of payment authorization differs from the clearing bank's spot conversion rate applied 48 hours later, causing legitimate FX variances to be erroneously flagged as fee calculation defects.

---

## 📦 OneLab Submission Deliverables Mapping

| # | OneLab Submission Requirement | Location / Artifact |
| :-: | :--- | :--- |
| **1** | **Brainstorming thread** (Full LLM conversation, uncleaned) | Documented in [CONVERSATION_HISTORY.md](CONVERSATION_HISTORY.md) and full conversation history export. |
| **2** | **Distilled prompt & Raw Prompt** (Mandatory) | Documented in [PROMPTS.md](PROMPTS.md) and Tab 7 of the web dashboard. |
| **3** | **Execution thread** (Full history including wrong turns) | Documented in [CONVERSATION_HISTORY.md](CONVERSATION_HISTORY.md) (Wrong turn: index slicing bug in generator caught by pytest and resolved). |
| **4** | **Test cases** (What was written to verify solution works) | Automated test suite in [tests/test_engine.py](tests/test_engine.py) and [tests/test_generator.py](tests/test_generator.py). |
| **5** | **Working output** | |
| 5a | *Deployed link* | Push to GitHub and deploy to Streamlit Community Cloud (instructions below). |
| 5b | *Source code* | Organized in existing directory structure (`reconx/`, `tests/`, `data/`, `app.py`). |
| 5c | *Demo video* | 2-minute walkthrough showing Overview, Waterfall Walk, 4 Gaps, Inspector, and GL. |
| 5d | *3 sentences on production limitations* | Authored above, in [PRODUCTION_ANALYSIS.md](PRODUCTION_ANALYSIS.md), and in Tab 7 of the UI. |

---

## 🛠️ Local Quickstart & Deployment Guide

### Local Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run unit tests
python -m pytest tests -v

# 3. Launch dashboard
streamlit run app.py
```
Dashboard opens at: `http://localhost:8501`.

### Streamlit Community Cloud Deployment (Free Public Link)
1. Push this repository to GitHub:
   ```bash
   git remote add origin https://github.com/<your-username>/reconx.git
   git branch -M main
   git push -u origin main
   ```
2. Navigate to [share.streamlit.io](https://share.streamlit.io) and log in with GitHub.
3. Click **"New app"** $\to$ Select `<your-username>/reconx` $\to$ Set Main file path to `app.py` $\to$ Click **"Deploy"**.
4. Copy your live URL (e.g. `https://reconx-onelab.streamlit.app`) into your final submission.

---

## 📁 Repository Structure

```
ReconX/
├── app.py                      # Streamlit Dark Fintech Dashboard (7 core sections)
├── requirements.txt            # Python dependencies (streamlit, pandas, plotly, pytest)
├── README.md                   # Complete documentation & assessment guide
├── PROMPTS.md                  # Raw and Distilled prompts
├── PRODUCTION_ANALYSIS.md      # The 3 sentences + deep production hardening analysis
├── CONVERSATION_HISTORY.md     # Actual AI conversation and brainstorming history
├── reconx/
│   ├── __init__.py
│   ├── models.py               # Financial domain models with Decimal fixed-point precision
│   ├── generator.py            # Synthetic generator (supports clean baseline or planted gaps)
│   ├── engine.py               # 4-Pass reconciliation matching & break detection engine
│   ├── parser.py               # Resilient CSV parser with flexible header mapping
│   └── reporter.py             # Balance sheet walk, audit reporting, and GL journal entries
├── tests/
│   ├── __init__.py
│   ├── test_generator.py       # Generator sanity & schema validation tests
│   └── test_engine.py          # 100% detection verification for all 4 gaps & math proof
└── data/
    ├── internal_transactions.csv
    └── bank_settlement.csv
```
