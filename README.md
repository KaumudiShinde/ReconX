# 💳 ReconX — Fintech Payment Settlement Reconciliation Engine

[![Tests](https://img.shields.io/badge/pytest-passing-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)]()
[![Framework](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg)]()

> **Internship Assessment for OneLab:**  
> A payments company's books don't balance at month end. They know every transaction their platform processed. They know what the bank says actually arrived. The two should match. They don't. Find out why. Show them where the gaps are.

---

## 🚀 Live Demo & Deployment
- **Deployed Web App:** Deployable in 1 click on [Streamlit Community Cloud](https://share.streamlit.io) by connecting this repository (select `app.py` as main file).
- **Interactive UI:** Includes financial KPI metrics, a Plotly waterfall balance walk, deep-dive root-cause panels for all 4 gap types, interactive break explorer, and audit report export.

---

## 📌 Architecture & How It Works

```
ReconX Pipeline
  │
  ├── 1. Ingest & Normalize (UTC timestamps, Fixed-point Decimal precision)
  │
  ├── 2. Multi-Pass Matching Engine
  │     ├── Pass 1: Duplicate Internal Record Detection (Webhook retry idempotency)
  │     ├── Pass 2: 1-to-1 Match & Sub-Cent Rounding Drift Identification
  │     ├── Pass 3: Month-End Timing Cutoff & Float Detection (Settled in Month T+1)
  │     └── Pass 4: Orphaned Bank Adjustments (Direct chargeback/clawback)
  │
  ├── 3. Mathematical Reconciliation Proof
  │     └── Internal Gross - Gaps = Bank Gross (Residual: $0.00)
  │
  └── 4. Interactive Dashboard & Audit Export (Streamlit, Plotly, CSV/Markdown export)
```

---

## 🔍 The 4 Planted Gaps (Root Causes & Mathematical Resolution)

| Gap Type | Operational Root Cause | Detection Strategy | Financial Resolution |
| :--- | :--- | :--- | :--- |
| **1. Settled Following Month** | Oct 31 transactions (`TXN_GAP1_*`) settle on Nov 2 due to $T+2$ bank clearing and weekend cut-off. | Transaction exists in internal ledger within 48h of cutoff; settlement date verified in subsequent clearing batch. | Reclassified as *Funds in Transit (Uncleared Deposits)* balance sheet asset. |
| **2. Rounding Difference When Summed** | Internal rounds fee per transaction: $\sum \text{round}(\text{gross} \times 2.15\%)$, while bank deducts fee on aggregate batch: $\text{round}(\sum \text{gross} \times 2.15\%)$. | Identified by exact gross match accompanied by $|\Delta \text{fee}| \le \$0.05$ across 43 transactions ($+\$0.43$ drift). | Adjusting journal entry posted to *Payment Processing Expense*. |
| **3. Duplicate Internal Entry** | Webhook retry / race condition double-inserted order `ORD_DUP_888` (`$145.00`), while bank charged card once. | Detected by grouping on `order_id` and identifying un-settled clone. | Redundant transaction marked for reversal from platform revenue ledger. |
| **4. Orphaned Bank Refund** | Direct bank chargeback / manual terminal refund (`-$85.00`) executed outside platform API. | Bank settlement debit (`STL_GAP4_*`) with zero internal transaction ID. | Reconciled as unlogged chargeback; ops ticket dispatched to Merchant Ops. |

---

## 🧮 Mathematical Reconciliation Proof

At month-end (October 31, 2026), the platform and bank books balance down to the exact penny:

$$\begin{aligned}
\text{Internal Platform Gross Volume} & = \$255,142.10 \\
(-) \text{ Webhook Duplicate Record (Gap 3)} & = -\$145.00 \\
(-) \text{ Month-End Timing Float Settled in Nov (Gap 1)} & = -\$530.50 \\
(+) \text{ Direct Bank Debit / Orphaned Refund (Gap 4)} & = -\$85.00 \\
\hline
\mathbf{\text{Reconciled Bank Settlement Gross}} & = \mathbf{\$254,381.60} \\
\mathbf{\text{Unexplained Residual Variance}} & = \mathbf{\$0.00 \quad (100\% \text{ Accounted For})}
\end{aligned}$$

---

## ⚠️ What This Would Get Wrong in Production (The 3 Sentences)

1. **Memory & Throughput Scale:** In high-volume production, an in-memory tabular comparison will suffer catastrophic out-of-memory (OOM) crashes and CPU bottlenecks because tier-1 payment gateways process hundreds of millions of daily events, necessitating a distributed stream-processing architecture (e.g. Apache Flink or DuckDB/ClickHouse window queries) with disk-backed state checkpoints rather than loading whole CSVs.
2. **Lump-Sum Batch Netting:** The engine assumes a clean 1-to-1 mapping between internal transaction IDs and bank settlement lines, whereas real-world acquiring banks settle via aggregated lump-sum batch wire payouts (many-to-one) that bundle thousands of sales, refunds, interchange tiers, rolling risk reserves, and chargeback penalties into a single net deposit.
3. **FX Volatility & Timing Slippage:** It does not account for multi-currency foreign exchange (FX) settlement slippage, where the dynamic exchange rate locked at the moment of payment authorization differs from the clearing bank's spot conversion rate applied 48 hours later, causing legitimate FX variances to be erroneously flagged as fee calculation defects.

---

## 🛠️ Local Setup & Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Automated Test Suite
```bash
python -m pytest tests -v
```

### 3. Launch the Interactive Dashboard
```bash
streamlit run app.py
```
The dashboard will open automatically in your browser at `http://localhost:8501`.

---

## 📁 Repository Structure

```
ReconX/
├── app.py                      # Main Streamlit Web Application
├── requirements.txt            # Python dependencies (streamlit, pandas, plotly, pytest)
├── README.md                   # Full documentation & project guide
├── PROMPTS.md                  # Distilled and Raw prompts (Submission Item 2)
├── PRODUCTION_ANALYSIS.md      # The 3 sentences + deep production hardening analysis
├── reconx/
│   ├── __init__.py
│   ├── models.py               # Domain dataclasses with Decimal precision
│   ├── generator.py            # Synthetic dataset generator with the 4 planted gaps
│   ├── engine.py               # 3-Pass reconciliation matching engine
│   └── reporter.py             # Markdown, JSON & tabular audit reporting
├── tests/
│   ├── __init__.py
│   ├── test_generator.py       # Generator sanity & schema validation tests
│   └── test_engine.py          # 100% detection verification for all 4 gaps & math proof
└── data/
    ├── internal_transactions.csv
    └── bank_settlement.csv
```

