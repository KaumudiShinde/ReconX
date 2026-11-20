# 💬 Actual AI Conversation History & Brainstorming Thread

This document records the actual, unedited thought process and conversation history between the candidate and the AI assistant during the architecture, implementation, and refinement of **ReconX** for the OneLab Internship Assessment.

---

## 1. Initial Assessment Request & Problem Framing
**Candidate Question:**
> *"I have received an internship assessment from Onelab the problem is about a payment company's transaction records not matching its bank settlement records, I understand that I need to compare both datasets and identify the differences, but I want to make sure I approach this correctly, Can you help me understand how payment reconciliation works and what exactly I should build for this assessment? Lets understand the problem first"*

**AI Engineering Breakdown:**
1. Demystified the domain: **Internal Platform Ledger** (captured payments in real-time) vs. **Acquiring Bank Settlement Report** (clearing batches deposited T+1 / T+2 days later net of fees).
2. Clarified why mismatches occur:
   - Timing cutoff float across month boundaries.
   - Gross vs Net settlement fee deductions.
   - Rounding float discrepancies on transaction fees.
   - Idempotency glitches / duplicate webhooks.
   - Direct acquiring bank adjustments / orphaned refunds.
3. Formulated the multi-pass matching strategy and recommended fixed-point `Decimal` monetary precision over floating-point arithmetic.

---

## 2. Assessment Requirements & The 4 Planted Gaps
**Candidate Prompt:**
> *"The Problem: A payments company's books don't balance at month end. They know every transaction their platform processed. They know what the bank says actually arrived. The two should match. They don't. Find out why. Show them where the gaps are.*  
> *Test Data: No files provided. Generate your own — that's part of the assessment. A payments platform records a transaction instantly when a customer pays. The bank batches and settles funds 1–2 days later. At month end every transaction should have a matching settlement.*  
> *Plant these gap types: a transaction that settled the following month · a rounding difference that only shows when summed · a duplicate entry in one dataset · a refund with no matching original transaction.*  
> *State your assumptions. There are no wrong ones as long as you name them.*  
> *What to Submit: 1 Brainstorming thread, 2 Distilled prompt and Raw Prompt, 3 Execution thread, 4 Test cases, 5 Working output (Deployed link + code zip/files + Demo video + 3 sentences on what it would get wrong in production)."*

---

## 3. Architecture & Test-Driven Development (TDD)
1. **Explicit Assumptions Defined:**
   - Target period: October 2026.
   - Standard acquiring bank clearing SLA: $T+1$ or $T+2$ business days.
   - Processing fee: 2.15% per transaction deducted from gross.
   - Precision: Fixed-point Decimal with `ROUND_HALF_UP` (2 decimal places).
2. **Planted Gaps Modeling:**
   - **Gap 1 (In-Transit Float):** Transactions on Oct 31 right before midnight (`TXN_GAP1_OCT31_001` and `TXN_GAP1_OCT31_002`) settling on November 2.
   - **Gap 2 (Rounding Drift):** Sub-cent fee drift where individual rounded fees $\sum \text{round}(\text{gross} \times 2.15\%)$ diverge from aggregate batch fee $\text{round}(\sum \text{gross} \times 2.15\%)$ by exactly \$0.43 across 43 items when summed.
   - **Gap 3 (Webhook Duplicate):** Order `ORD_DUP_888` recorded twice in platform ledger (`TXN_GAP3_DUP_ORIGINAL` and `TXN_GAP3_DUP_RETRY`), but settled once by the bank.
   - **Gap 4 (Orphaned Refund):** Direct acquiring bank debit adjustment of -\$85.00 (`STL_GAP4_ORPHAN_REFUND_999`) with reference `TXN_NONEXISTENT_ACQ_999` not recorded in the platform API.
3. **Documented Wrong Turn & Fix:**
   - When running `pytest` with small sample size ($N=50$), an `IndexError` occurred in `generator.py` because index sampling was hardcoded to `range(100, 500)`.
   - The test suite immediately caught this bug. The code was refactored so that eligible sampling ranges dynamically scale with the dataset volume.
4. **Resilient CSV Parser & General Ledger Enhancements:**
   - Upgraded `reconx/parser.py` with flexible column name mapping (supporting `Gross`, `Amount`, `Transaction ID`, etc.) and automatic fee/net inference.
   - Added automated double-entry General Ledger adjusting journal entries (Debits/Credits) to provide complete financial sign-off for ERP systems.
5. **Full Test Suite (All 8 Tests Passing):**
   - Verified 100% detection of all 4 gap categories, clean baseline matching when `plant_gaps=False`, resilient parsing of custom headers, and mathematical balance sheet invariance.
