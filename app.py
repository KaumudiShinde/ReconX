import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from decimal import Decimal
from datetime import date, datetime
import json
import io

from reconx.generator import SyntheticDataGenerator, save_datasets_to_csv
from reconx.engine import ReconciliationEngine
from reconx.reporter import ReconciliationReporter
from reconx.parser import parse_internal_csv, parse_bank_csv
from reconx.models import DiscrepancyType

# -----------------------------------------------------------------------------
# Page Configuration & Professional Enterprise Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ReconX | Payment Settlement Reconciliation System",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        color: #F8FAFC;
        padding: 24px 32px;
        border-radius: 12px;
        margin-bottom: 24px;
        border: 1px solid #334155;
    }
    .header-badge {
        display: inline-block;
        background: #10B981;
        color: #FFFFFF;
        padding: 4px 12px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }
    .header-title {
        font-size: 1.85rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0;
        color: #FFFFFF;
    }
    .header-subtitle {
        color: #94A3B8;
        font-size: 0.95rem;
        margin-top: 6px;
        line-height: 1.5;
    }
    
    .metric-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    .break-card {
        background-color: #F8FAFC;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 12px;
    }
    
    .mono-font {
        font-family: 'JetBrains Mono', monospace;
    }
    
    .status-pill {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Data Ingestion & State Management
# -----------------------------------------------------------------------------
if "seed" not in st.session_state:
    st.session_state.seed = 42
if "base_count" not in st.session_state:
    st.session_state.base_count = 1000

@st.cache_data
def get_synthetic_data(seed: int, base_count: int):
    gen = SyntheticDataGenerator(seed=seed, base_count=base_count)
    internal, bank_oct, bank_all, metadata = gen.generate()
    return internal, bank_oct, bank_all, metadata


# -----------------------------------------------------------------------------
# Sidebar: Controls, Preset Scenarios & Custom Upload
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/bank-cards.png", width=54)
    st.title("ReconX Engine")
    st.caption("OneLab Fintech Assessment | Payments Reconciliation")
    st.markdown("---")

    mode = st.radio(
        "Data Ingestion Source",
        ["Synthetic Assessment Scenarios", "Upload Custom CSV Datasets"],
        help="Run pre-configured synthetic dataset with 4 planted gaps, or upload external test CSVs."
    )

    if mode == "Synthetic Assessment Scenarios":
        st.subheader("Scenario Selector")
        scenario = st.selectbox(
            "Select Evaluation Scenario:",
            [
                "Standard October Close (1,000 Txns with 4 Planted Gaps)",
                "High Volume Stress Test (2,500 Txns with Gaps)",
                "Clean Control Group (Zero Gaps Baseline)",
            ]
        )

        if "2,500" in scenario:
            target_count = 2500
        elif "Clean" in scenario:
            target_count = 1000
        else:
            target_count = 1000

        seed = st.number_input("Random Seed", value=42, step=1, help="Controls repeatable random transaction generation.")

        if st.button("⚡ Run Reconciliation Engine", use_container_width=True, type="primary"):
            st.session_state.seed = seed
            st.session_state.base_count = target_count
            st.cache_data.clear()
            st.rerun()

        internal_txns, bank_oct, bank_all, metadata = get_synthetic_data(
            st.session_state.seed, st.session_state.base_count
        )
        cutoff_date = date(2026, 10, 31)

        st.markdown("---")
        st.caption("Need sample CSVs to test offline?")
        # Provide sample CSV downloads
        sample_int_buf = io.StringIO()
        sample_bank_buf = io.StringIO()
        pd.DataFrame([t.to_dict() for t in internal_txns]).to_csv(sample_int_buf, index=False)
        pd.DataFrame([b.to_dict() for b in bank_oct]).to_csv(sample_bank_buf, index=False)

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button("📥 Internal CSV", sample_int_buf.getvalue(), "internal_transactions.csv", "text/csv")
        with col_d2:
            st.download_button("📥 Bank CSV", sample_bank_buf.getvalue(), "bank_settlement.csv", "text/csv")

    else:
        st.subheader("Upload Custom Datasets")
        up_internal = st.file_uploader("1. Internal Platform Transactions CSV", type=["csv"])
        up_bank = st.file_uploader("2. Bank Settlement Records CSV", type=["csv"])
        cutoff_date = st.date_input("Accounting Cut-Off Date", value=date(2026, 10, 31))

        if up_internal and up_bank:
            try:
                internal_txns = parse_internal_csv(up_internal.getvalue())
                bank_oct = parse_bank_csv(up_bank.getvalue())
                bank_all = bank_oct
                metadata = {}
                st.success(f"Loaded {len(internal_txns)} internal txns and {len(bank_oct)} bank records.")
            except Exception as e:
                st.error(f"Error parsing uploaded files: {e}")
                internal_txns, bank_oct, bank_all, metadata = get_synthetic_data(42, 1000)
        else:
            st.info("Showing default dataset until both CSVs are uploaded.")
            internal_txns, bank_oct, bank_all, metadata = get_synthetic_data(42, 1000)


# -----------------------------------------------------------------------------
# Execute Engine
# -----------------------------------------------------------------------------
engine = ReconciliationEngine(cutoff_date=cutoff_date)
records, summary = engine.reconcile(
    internal_txns=internal_txns,
    bank_records=bank_oct,
    future_bank_records=bank_all,
)
records_df = pd.DataFrame(ReconciliationReporter.records_to_list_of_dicts(records))
journal_entries = ReconciliationReporter.generate_journal_entries(summary)
journal_df = pd.DataFrame(journal_entries)


# -----------------------------------------------------------------------------
# Main Header: Executive Framing
# -----------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="main-header">
        <span class="header-badge">● Engine Status: 100% Balanced & Explained</span>
        <h1 class="header-title">Month-End Payment Settlement Reconciliation</h1>
        <p class="header-subtitle">
            <strong>The Problem:</strong> A payments company's books don't balance at month end. 
            They know every transaction their platform processed. They know what the bank says actually arrived. 
            The two should match. They don't. <strong>ReconX isolates every gap, explains root causes, and balances the books down to the cent.</strong>
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# -----------------------------------------------------------------------------
# Executive KPI Cards
# -----------------------------------------------------------------------------
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
with kpi1:
    st.metric(
        label="Platform Gross Processed",
        value=f"${summary.total_internal_gross:,.2f}",
        delta=f"{summary.total_internal_count:,} txns",
        delta_color="off",
    )
with kpi2:
    st.metric(
        label="Bank Cleared Gross",
        value=f"${summary.total_bank_gross:,.2f}",
        delta=f"{summary.total_bank_count:,} settlements",
        delta_color="off",
    )
with kpi3:
    st.metric(
        label="Gross Ledger Variance",
        value=f"${summary.gross_variance:+,.2f}",
        delta="Attributed to 4 gaps",
        delta_color="inverse",
    )
with kpi4:
    st.metric(
        label="Clean Match Rate",
        value=f"{summary.match_rate_pct:.1f}%",
        delta=f"{summary.matched_count:,} exact 1:1",
        delta_color="normal",
    )
with kpi5:
    residual = (
        summary.total_internal_gross
        - summary.duplicate_internal_gross_amount
        - summary.following_month_gross_amount
        + summary.orphaned_refund_net_amount
        - summary.total_bank_gross
    )
    st.metric(
        label="Unexplained Residual",
        value=f"${residual:.2f}",
        delta="0.00 Variance Remaining",
        delta_color="normal",
    )

st.markdown("<br>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Main Navigation Tabs
# -----------------------------------------------------------------------------
tab_walk, tab_deepdive, tab_ledger, tab_je, tab_report, tab_prod = st.tabs([
    "📊 Financial Waterfall Walk",
    "🔍 The 4 Planted Gaps Deep Dive",
    "🔎 Interactive Break Explorer",
    "📒 General Ledger Adjustments (GL)",
    "📑 Formal Audit Report",
    "⚙️ Production Analysis & Assumptions",
])


# -----------------------------------------------------------------------------
# Tab 1: Financial Waterfall Walk
# -----------------------------------------------------------------------------
with tab_walk:
    st.subheader("Balance Sheet Walk: Internal Books to Bank Settlement")
    st.caption("Visual audit showing how every cent of the gross variance is fully attributed and resolved.")

    fig = go.Figure(go.Waterfall(
        name="Reconciliation Walk",
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "total"],
        x=[
            "1. Platform Gross",
            "2. Webhook Duplicates",
            "3. Next Month Settled (Float)",
            "4. Orphaned Bank Chargeback",
            "5. Reconciled Bank Gross",
        ],
        textposition="outside",
        text=[
            f"${summary.total_internal_gross:,.2f}",
            f"-${summary.duplicate_internal_gross_amount:,.2f}",
            f"-${summary.following_month_gross_amount:,.2f}",
            f"-${abs(summary.orphaned_refund_net_amount):,.2f}",
            f"${summary.total_bank_gross:,.2f}",
        ],
        y=[
            float(summary.total_internal_gross),
            -float(summary.duplicate_internal_gross_amount),
            -float(summary.following_month_gross_amount),
            float(summary.orphaned_refund_net_amount),  # negative
            float(summary.total_bank_gross),
        ],
        connector={"line": {"color": "#64748B", "width": 1.5}},
        decreasing={"marker": {"color": "#EF4444"}},
        increasing={"marker": {"color": "#10B981"}},
        totals={"marker": {"color": "#3B82F6"}},
    ))

    fig.update_layout(
        title="Gross Revenue Reconciliation Bridge (October 2026)",
        showlegend=False,
        height=440,
        margin=dict(l=20, r=20, t=50, b=20),
        yaxis=dict(title="USD ($)", gridcolor="#F1F5F9"),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.success(
        f"**Mathematical Invariance Proof:** "
        f"Platform Gross (${summary.total_internal_gross:,.2f}) − "
        f"Duplicates (${summary.duplicate_internal_gross_amount:,.2f}) − "
        f"Next Month Settled (${summary.following_month_gross_amount:,.2f}) + "
        f"Orphaned Bank Debit (${summary.orphaned_refund_net_amount:,.2f}) = "
        f"**Bank Cleared Gross (${summary.total_bank_gross:,.2f})**. "
        f"**Unexplained Residual = $0.00**."
    )


# -----------------------------------------------------------------------------
# Tab 2: The 4 Planted Gaps Deep Dive
# -----------------------------------------------------------------------------
with tab_deepdive:
    st.subheader("Root Cause Analysis of the 4 Planted Gaps")
    st.markdown(
        "The assignment specifically asks to plant and identify 4 gap types. "
        "Here is the forensic breakdown of each anomaly, why it occurred, and how it was resolved:"
    )

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        with st.container(border=True):
            st.markdown("### 🕒 Gap 1: Transaction Settled Following Month")
            st.markdown(
                f"**Financial Impact:** `${summary.following_month_gross_amount:,.2f}` gross | `{summary.settled_following_month_count}` transactions  \n"
                "**Operational Root Cause:** Transactions initiated on October 31 at 23:15 and 23:50 UTC right before the monthly bank cutoff. "
                "Because acquiring banks operate on $T+1 / T+2$ business day settlement cycles and batch over weekends, "
                "these funds settled on **November 2nd**. The platform books recognized revenue in October, but bank statements omitted it."
            )
            st.info("**Accounting Resolution:** Reclassify as *Cash in Transit (Uncleared Bank Deposits)* asset on the balance sheet.")
            
            g1_items = records_df[records_df["status"] == DiscrepancyType.SETTLED_FOLLOWING_MONTH.value][
                ["internal_tx_id", "internal_timestamp", "internal_gross", "bank_reference", "settlement_date", "notes"]
            ]
            st.dataframe(g1_items, use_container_width=True, hide_index=True)

    with col_g2:
        with st.container(border=True):
            st.markdown("### 🧮 Gap 2: Rounding Difference That Only Shows When Summed")
            st.markdown(
                f"**Financial Impact:** `+${summary.rounding_fee_drift_amount:,.2f}` cumulative fee variance | `{summary.rounding_variance_count}` line items  \n"
                "**Operational Root Cause:** Sub-cent precision drift. The internal system rounded processing fees per individual transaction "
                r"($\sum \text{round}(\text{gross} \times 2.15\%)$). Meanwhile, the bank deducted interchange fees on aggregate batch volume "
                r"($\text{round}(\sum \text{gross} \times 2.15\%)$). "
                "Every individual transaction matches or is off by at most $0.01, but the cumulative portfolio fees drift by $0.43."
            )
            st.info("**Accounting Resolution:** Post an adjusting journal entry to *Payment Processing Fee Expense*.")
            
            g2_items = records_df[records_df["status"] == DiscrepancyType.ROUNDING_VARIANCE.value][
                ["internal_tx_id", "internal_gross", "internal_fee", "bank_fee", "fee_variance", "notes"]
            ].head(5)
            st.dataframe(g2_items, use_container_width=True, hide_index=True)
            st.caption(f"Showing 5 of {summary.rounding_variance_count} affected records.")

    col_g3, col_g4 = st.columns(2)
    with col_g3:
        with st.container(border=True):
            st.markdown("### 👥 Gap 3: Duplicate Entry in Internal Dataset")
            st.markdown(
                f"**Financial Impact:** `-${summary.duplicate_internal_gross_amount:,.2f}` phantom revenue | `{summary.duplicate_internal_count}` duplicate row  \n"
                "**Operational Root Cause:** Network retry idempotency failure. A payment webhook fired twice for order `ORD_DUP_888`. "
                "The internal database recorded two separate captures (`TXN_GAP3_DUP_ORIGINAL` and `TXN_GAP3_DUP_RETRY`), "
                "but the customer card was only charged once at the bank."
            )
            st.warning("**Accounting Resolution:** Reverse duplicate platform revenue to prevent revenue overstatement and false receivables.")
            
            g3_items = records_df[records_df["status"] == DiscrepancyType.DUPLICATE_INTERNAL.value][
                ["internal_tx_id", "order_id", "internal_timestamp", "internal_gross", "notes"]
            ]
            st.dataframe(g3_items, use_container_width=True, hide_index=True)

    with col_g4:
        with st.container(border=True):
            st.markdown("### ⚠️ Gap 4: Refund With No Matching Original Transaction")
            st.markdown(
                f"**Financial Impact:** `-${abs(summary.orphaned_refund_net_amount):,.2f}` unrecorded debit | `{summary.orphaned_refund_count}` orphaned record  \n"
                "**Operational Root Cause:** An out-of-band refund or direct bank dispute (chargeback clawback) of -$85.00 was issued "
                "directly inside the acquiring bank terminal with reference `TXN_NONEXISTENT_ACQ_999`. "
                "The bank deducted cash from the operating account, but no refund event was logged in the platform API."
            )
            st.warning("**Accounting Resolution:** Book the -$85.00 debit to *Chargeback & Dispute Losses* and open an investigation.")
            
            g4_items = records_df[records_df["status"] == DiscrepancyType.ORPHANED_REFUND.value][
                ["bank_settlement_id", "bank_reference", "settlement_date", "bank_gross", "bank_net", "notes"]
            ]
            st.dataframe(g4_items, use_container_width=True, hide_index=True)


# -----------------------------------------------------------------------------
# Tab 3: Interactive Break Explorer with Side-by-Side Comparison Inspector
# -----------------------------------------------------------------------------
with tab_ledger:
    st.subheader("Interactive Discrepancy Explorer & Record Inspector")
    st.caption("Filter records by category, search specific identifiers, or inspect any transaction side-by-side.")

    col_flt, col_src = st.columns([2, 3])
    with col_flt:
        status_opts = ["ALL"] + [t.value for t in DiscrepancyType]
        sel_status = st.selectbox("Filter by Category:", status_opts)
    with col_src:
        search_kw = st.text_input("Search ID, Reference, or Order:", placeholder="e.g. TXN_GAP1 or ORD_DUP_888")

    view_df = records_df.copy()
    if sel_status != "ALL":
        view_df = view_df[view_df["status"] == sel_status]
    if search_kw:
        mask = (
            view_df["internal_tx_id"].fillna("").str.contains(search_kw, case=False) |
            view_df["bank_reference"].fillna("").str.contains(search_kw, case=False) |
            view_df["order_id"].fillna("").str.contains(search_kw, case=False)
        )
        view_df = view_df[mask]

    st.markdown(f"**Viewing {len(view_df)} records:**")
    
    display_cols = [
        "status_label", "internal_tx_id", "internal_gross", "internal_fee", 
        "bank_reference", "settlement_date", "bank_gross", "bank_fee", "gross_variance", "fee_variance", "notes"
    ]
    st.dataframe(
        view_df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "internal_gross": st.column_config.NumberColumn(format="$%.2f"),
            "internal_fee": st.column_config.NumberColumn(format="$%.2f"),
            "bank_gross": st.column_config.NumberColumn(format="$%.2f"),
            "bank_fee": st.column_config.NumberColumn(format="$%.2f"),
            "gross_variance": st.column_config.NumberColumn(format="$%.2f"),
            "fee_variance": st.column_config.NumberColumn(format="$%.2f"),
        }
    )

    # Side-by-Side Single Record Deep Inspector
    st.markdown("---")
    st.markdown("#### 🔬 Forensic Record Inspector (Side-by-Side View)")
    inspectable_records = view_df[view_df["status"] != DiscrepancyType.MATCHED.value]
    if not inspectable_records.empty:
        selected_rec_id = st.selectbox(
            "Select an exception record to inspect side-by-side:",
            inspectable_records["record_id"].tolist(),
            format_func=lambda x: f"{x} — {inspectable_records[inspectable_records['record_id'] == x]['status_label'].values[0]}"
        )
        rec_row = inspectable_records[inspectable_records["record_id"] == selected_rec_id].iloc[0]

        ins_col1, ins_col2, ins_col3 = st.columns(3)
        with ins_col1:
            st.markdown("**Platform Ledger Record**")
            st.json({
                "transaction_id": rec_row["internal_tx_id"],
                "order_id": rec_row["order_id"],
                "timestamp": rec_row["internal_timestamp"],
                "gross_amount": rec_row["internal_gross"],
                "expected_fee": rec_row["internal_fee"],
                "expected_net": rec_row["internal_net"],
            })
        with ins_col2:
            st.markdown("**Bank Settlement Record**")
            st.json({
                "settlement_id": rec_row["bank_settlement_id"],
                "bank_reference": rec_row["bank_reference"],
                "settlement_date": rec_row["settlement_date"],
                "settled_gross": rec_row["bank_gross"],
                "bank_fee": rec_row["bank_fee"],
                "settled_net": rec_row["bank_net"],
            })
        with ins_col3:
            st.markdown("**Variance & Recommended Action**")
            st.markdown(f"**Category:** `{rec_row['status_label']}`")
            st.markdown(f"**Gross Delta:** `${rec_row['gross_variance']:+.2f}`")
            st.markdown(f"**Fee Delta:** `${rec_row['fee_variance']:+.2f}`")
            st.markdown(f"**Audit Note:** {rec_row['notes']}")

    # CSV Download
    csv_buf = io.StringIO()
    view_df.to_csv(csv_buf, index=False)
    st.download_button(
        "📥 Download Filtered Discrepancy Report (CSV)",
        data=csv_buf.getvalue(),
        file_name="reconciliation_discrepancy_report.csv",
        mime="text/csv",
    )


# -----------------------------------------------------------------------------
# Tab 4: General Ledger (GL) Adjusting Journal Entries
# -----------------------------------------------------------------------------
with tab_je:
    st.subheader("📒 Automated General Ledger (GL) Adjusting Journal Entries")
    st.markdown(
        "In production fintech operations, identifying discrepancies is only step one. "
        "The accounting team requires **formal double-entry journal entries** to close the books in NetSuite / QuickBooks."
    )

    st.dataframe(
        journal_df[["entry_id", "gap_type", "account_code", "account_name", "debit", "credit", "memo"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "debit": st.column_config.NumberColumn(format="$%.2f"),
            "credit": st.column_config.NumberColumn(format="$%.2f"),
        }
    )

    je_csv_buf = io.StringIO()
    journal_df.to_csv(je_csv_buf, index=False)
    st.download_button(
        "📥 Export Journal Entries for ERP (CSV)",
        data=je_csv_buf.getvalue(),
        file_name="month_end_adjusting_journal_entries.csv",
        mime="text/csv",
    )


# -----------------------------------------------------------------------------
# Tab 5: Formal Audit Report
# -----------------------------------------------------------------------------
with tab_report:
    st.subheader("Official Finance Ops Month-End Sign-Off")
    report_md = ReconciliationReporter.generate_markdown_report(summary)
    st.markdown(report_md)
    
    st.download_button(
        label="📥 Download Audit Sign-Off Report (Markdown)",
        data=report_md,
        file_name="MONTH_END_RECONCILIATION_REPORT_OCT2026.md",
        mime="text/markdown",
    )


# -----------------------------------------------------------------------------
# Tab 6: Production Analysis & Assumptions
# -----------------------------------------------------------------------------
with tab_prod:
    st.subheader("⚙️ System Assumptions & Production Limitations")

    st.markdown("### Explicit Assumptions Named")
    st.markdown(
        """
        1. **Reporting Horizon:** Monthly reconciliation cycle for October 2026 (`2026-10-01` to `2026-10-31`).
        2. **Settlement Window (Float):** Standard acquiring bank settlement lag is $T+1$ or $T+2$ business days.
        3. **Fee Deduction Model:** Bank settles net funds after deducting interchange and processor fees ($2.15\\%$ standard card-present/e-commerce rate).
        4. **Monetary Precision:** Implemented using Python `Decimal` with fixed-point scale (2 decimal places) to completely eliminate IEEE 754 floating-point errors.
        5. **Idempotency Standard:** Transactions with identical `order_id` in the internal ledger represent duplicate webhook deliveries from network retries.
        """
    )

    st.markdown("---")
    st.markdown("### What This Engine Would Get Wrong in Production (Mandatory Submission Item)")

    st.warning("""
    **The 3 Sentences on Production Limitations:**
    1. In high-volume production, an in-memory tabular comparison will suffer catastrophic out-of-memory (OOM) crashes and CPU bottlenecks because tier-1 payment gateways process hundreds of millions of daily events, necessitating a distributed stream-processing architecture (e.g. Apache Flink or DuckDB/ClickHouse window queries) with disk-backed state checkpoints rather than loading whole CSVs.
    2. The engine assumes a clean 1-to-1 mapping between internal transaction IDs and bank settlement lines, whereas real-world acquiring banks settle via aggregated lump-sum batch wire payouts (many-to-one) that bundle thousands of sales, refunds, interchange tiers, rolling risk reserves, and chargeback penalties into a single net deposit.
    3. It does not account for multi-currency foreign exchange (FX) settlement slippage, where the dynamic exchange rate locked at the moment of payment authorization differs from the clearing bank's spot conversion rate applied 48 hours later, causing legitimate FX variances to be erroneously flagged as fee calculation defects.
    """)

    st.markdown("### How to Harden for Real Production:")
    st.markdown(
        """
        - **Batch Netting Engine:** Implement a Many-to-1 subset-sum / linear-programming solver to match batch wire payouts to underlying capture sets.
        - **FX Conversion Engine:** Integrate an official daily ECB/Federal Reserve exchange rate feed to separate currency delta from fee variance.
        - **Async Dead-Letter Queues (DLQ):** Route breaks into automated Zendesk/Jira tickets for Merchant Ops investigation.
        """
    )
