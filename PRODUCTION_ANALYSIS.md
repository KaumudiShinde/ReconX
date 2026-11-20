# ⚠️ What This System Would Get Wrong in Production

> **Mandatory Submission Requirement:** Exactly 3 sentences on what this system would get wrong in production.

---

## The 3 Sentences

1. **Memory & Throughput Scale:** In high-volume production, an in-memory tabular comparison will suffer catastrophic out-of-memory (OOM) crashes and CPU bottlenecks because tier-1 payment gateways process hundreds of millions of daily events, necessitating a distributed stream-processing architecture (e.g. Apache Flink or DuckDB/ClickHouse window queries) with disk-backed state checkpoints rather than loading whole CSVs.
2. **Lump-Sum Batch Netting:** The engine assumes a clean 1-to-1 mapping between internal transaction IDs and bank settlement lines, whereas real-world acquiring banks settle via aggregated lump-sum batch wire payouts (many-to-one) that bundle thousands of sales, refunds, interchange tiers, rolling risk reserves, and chargeback penalties into a single net deposit.
3. **FX Volatility & Timing Slippage:** It does not account for multi-currency foreign exchange (FX) settlement slippage, where the dynamic exchange rate locked at the moment of payment authorization differs from the clearing bank's spot conversion rate applied 48 hours later, causing legitimate FX variances to be erroneously flagged as fee calculation defects.

---

## Deep-Dive: How to Remedy These in Real Production

### 1. Handling Many-to-One Batch Settlements
In production, acquiring banks (e.g., Chase Paymentech, First Data, Worldpay) deposit **one lump-sum wire** per batch (e.g., \$2,450,119.45) rather than 10,000 individual lines.
- **Remedy:** The reconciliation engine must ingest the **Clearing Epilogue / Batch Header** record, calculate the expected net of all captures assigned to Batch ID $K$, deduct the aggregate interchange fee schedule, and perform a subset-sum matrix verification.

### 2. Multi-Currency FX Revaluation
When a customer pays in EUR and the merchant settles in USD:
- Authorization date FX rate: EUR/USD = 1.0850.
- Settlement date (T+2) clearing bank FX rate: EUR/USD = 1.0815.
- The 35-basis-point variance is not a missing fee or leakage—it is **realized foreign exchange gain/loss**.
- **Remedy:** Integrate an automated daily ECB / Federal Reserve FX reference rate feed into the engine to automatically book FX variance into a dedicated general ledger account (*P&L: Realized FX Variance*).

### 3. Distributed Asynchronous Ingestion & DLQ
- Real-world settlement files are delivered via SFTP in ISO 20022 XML (`camt.053`) or BAI2 format at 03:00 AM.
- Parsing gigabyte-scale bank files requires chunked streaming with worker pools.
- Any unresolvable break should automatically create an idempotency-keyed ticket in an Ops queue (Jira / Zendesk) for manual human investigation.

