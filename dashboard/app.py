from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Payroll Validation System",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ==========================================
# API HELPER FUNCTIONS
# ==========================================

API_URL = st.sidebar.text_input(
    "Backend API URL",
    value="http://127.0.0.1:8000"
).rstrip("/")


def api_get(endpoint: str, params: Optional[Dict] = None):
    try:
        res = requests.get(f"{API_URL}{endpoint}", params=params, timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as err:
        st.sidebar.error(f"API Error: {err}")
        return None


def api_post(endpoint: str, payload: Optional[Dict] = None):
    try:
        res = requests.post(f"{API_URL}{endpoint}", json=payload, timeout=20)
        res.raise_for_status()
        return res.json()
    except Exception as err:
        st.error(f"API Request Failed: {err}")
        return None


def api_patch(endpoint: str, payload: Optional[Dict] = None):
    try:
        res = requests.patch(f"{API_URL}{endpoint}", json=payload, timeout=20)
        res.raise_for_status()
        return res.json()
    except Exception as err:
        st.error(f"API Request Failed: {err}")
        return None


# ==========================================
# SIDEBAR: ACTOR SELECTION & ACTIONS
# ==========================================

st.sidebar.title("💼 Payroll System")
st.sidebar.caption("Pre-Payroll Validation & Reconciliation")

ACTORS = {
    "HR": {"name": "Priya Sharma", "role": "HR", "title": "HR Partner"},
    "MANAGER": {"name": "David Miller", "role": "MANAGER", "title": "Department Manager"},
    "ADMIN": {"name": "Sarah Jenkins", "role": "ADMIN", "title": "System Administrator"},
    "IT_OPS": {"name": "Alex Chen", "role": "IT_OPS", "title": "IT / Operations"}
}

actor_key = st.sidebar.selectbox(
    "Acting As (Demo Role):",
    options=list(ACTORS.keys()),
    format_func=lambda k: f"{ACTORS[k]['title']} ({ACTORS[k]['name']})"
)
active_actor = ACTORS[actor_key]

st.sidebar.info(f"👤 **{active_actor['name']}**\nRole: `{active_actor['role']}`")

st.sidebar.divider()

# Quick action buttons in sidebar
if st.sidebar.button("🔄 Re-run All 8 Validation Rules", use_container_width=True):
    with st.spinner("Validating payroll rules..."):
        val_res = api_post("/payroll/validate")
        if val_res and val_res.get("success"):
            st.sidebar.success(f"Validation complete! {val_res.get('open_exceptions')} open issues.")
            st.rerun()

if st.sidebar.button("⚡ Bulk-Approve Pending Shifts", use_container_width=True):
    with st.spinner("Approving pending shifts..."):
        app_res = api_post("/time-entries/bulk-approve", {"actor_name": active_actor["name"], "actor_role": active_actor["role"]})
        if app_res and app_res.get("success"):
            st.sidebar.success(f"Approved {app_res.get('approved_count')} time entries!")
            api_post("/payroll/validate")
            st.rerun()

st.sidebar.divider()

# Backend Health Check
try:
    health = requests.get(f"{API_URL}/health", timeout=3)
    health.raise_for_status()
    st.sidebar.success("● Backend API Online")
except Exception:
    st.sidebar.error("○ Backend API Offline")
    st.error("Cannot connect to FastAPI backend on port 8000. Please start the server.")
    st.stop()


# ==========================================
# FETCH DATA
# ==========================================

payroll = api_get("/payroll") or []
exceptions = api_get("/exceptions") or []
periods = api_get("/pay-periods") or []
metrics = api_get("/validation/metrics") or {}
audit_logs = api_get("/audit-logs", params={"limit": 20}) or []

payroll_df = pd.DataFrame(payroll)
exceptions_df = pd.DataFrame(exceptions)


# ==========================================
# HEADER: THE 4-STEP PAYROLL PIPELINE
# ==========================================

st.title("💼 Payroll Validation & Governance System")
st.markdown("""
**How this works (The 4-Step Pipeline):**
`1. Ingest & Aggregate` ➔ `2. Run 8 Automated Validation Rules` ➔ `3. Resolve Exceptions & Approve` ➔ `4. Export Clean CSV`
""")

st.divider()


# ==========================================
# 4 MAIN TABS
# ==========================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 1. Overview & Health",
    "⚠️ 2. Exceptions & Fixes",
    "✍️ 3. Approvals & Safety",
    "📁 4. Secure CSV Export",
    "📜 5. Audit Trail & Ground Truth"
])


# ==========================================
# TAB 1: OVERVIEW & HEALTH
# ==========================================

with tab1:
    st.subheader("1. Payroll Health & Governance KPIs")

    total_records = len(payroll_df)
    total_net = payroll_df["net_pay"].sum() if not payroll_df.empty else 0.0
    approved_count = len(payroll_df[payroll_df["status"] == "APPROVED"]) if not payroll_df.empty else 0
    open_excs = len([e for e in exceptions if e.get("status") == "OPEN"])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Payroll Inputs", total_records)
    k2.metric("Total Net Payroll", f"₹{total_net:,.2f}")
    k3.metric("Approved Records", approved_count)
    k4.metric("Open Exceptions", open_excs, delta="Requires Attention" if open_excs > 0 else "All Clean", delta_color="inverse")

    st.markdown("---")

    # Metrics against ground truth
    st.markdown("##### 🎯 Anomaly Detection Accuracy (Ground Truth Benchmark)")
    if metrics.get("ground_truth_available"):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Planted Anomalies", metrics.get("ground_truth_count", 0))
        m2.metric("True Positives Detected", metrics.get("true_positives", 0))
        m3.metric("Recall (Sensitivity)", f"{metrics.get('recall', 0):.1%}")
        m4.metric("F1-Score", f"{metrics.get('f1_score', 0):.3f}")
    else:
        st.info("Ground truth benchmark loaded from `datasets/ground_truth.json`.")

    st.markdown("---")

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown("##### Payroll Lifecycle Distribution")
        if not payroll_df.empty:
            status_df = payroll_df["status"].value_counts().reset_index()
            status_df.columns = ["Status", "Count"]
            fig_stat = px.bar(
                status_df, x="Status", y="Count", color="Status", text="Count",
                color_discrete_map={"DRAFT": "#6c757d", "PENDING": "#ffc107", "APPROVED": "#28a745", "EXPORTED": "#17a2b8"}
            )
            st.plotly_chart(fig_stat, use_container_width=True)

    with col_chart2:
        st.markdown("##### Exceptions by Issue Category")
        if not exceptions_df.empty:
            open_df = exceptions_df[exceptions_df["status"] == "OPEN"]
            if not open_df.empty:
                issue_df = open_df["issue_type"].value_counts().reset_index()
                issue_df.columns = ["Issue Type", "Count"]
                fig_issue = px.pie(issue_df, names="Issue Type", values="Count", hole=0.4)
                st.plotly_chart(fig_issue, use_container_width=True)
            else:
                st.success("All exceptions have been resolved!")


# ==========================================
# TAB 2: EXCEPTIONS & IN-LINE FIXES
# ==========================================

with tab2:
    st.subheader("2. Exception Workbench: Investigate & Fix in One Click")
    st.caption("Interview Tip: Demonstrate how an exception is investigated, corrected in source data, and formally resolved.")

    # Deterministically sort open exceptions by employee_id ascending, then by exception_id
    open_items = sorted(
        [e for e in exceptions if e.get("status") == "OPEN"],
        key=lambda x: (
            x.get("employee_id") if x.get("employee_id") is not None else 999999,
            x.get("exception_id") or ""
        )
    )

    if not open_items:
        st.success("🎉 No open exceptions! All payroll records are clean and ready for approval.")
    else:
        st.write(f"Found **{len(open_items)} open exception(s)** blocking payroll approval.")

        # Display simple table sorted by employee_id (1, 2, 3...)
        tbl_rows = []
        for e in open_items:
            eid = e.get("employee_id")
            emp_code = f"EMP-{eid:06d}" if eid is not None else "GLOBAL"
            tbl_rows.append({
                "employee_id": eid,
                "employee_code": emp_code,
                "exception_id": e.get("exception_id"),
                "issue_type": e.get("issue_type"),
                "severity": e.get("severity"),
                "description": e.get("description")
            })
        tbl_df = pd.DataFrame(tbl_rows)
        st.dataframe(
            tbl_df,
            use_container_width=True,
            height=260,
            column_config={
                "employee_id": st.column_config.NumberColumn("Employee ID", format="%d"),
                "employee_code": "Employee Code",
                "exception_id": "Exception ID",
                "issue_type": "Issue Type",
                "severity": "Severity",
                "description": "Description"
            }
        )

        st.markdown("---")
        st.markdown("#### 🛠️ In-Line Correction Tool")

        selected_id = st.selectbox(
            "Select Exception to Investigate:",
            options=[e["exception_id"] for e in open_items],
            format_func=lambda eid: next(
                (
                    f"Employee {e['employee_id']} (EMP-{e['employee_id']:06d}) | {e['issue_type']} | {e['exception_id']}"
                    if e.get("employee_id") is not None
                    else f"GLOBAL | {e['issue_type']} | {e['exception_id']}"
                )
                for e in open_items if e["exception_id"] == eid
            )
        )
        selected_exc = next((e for e in open_items if e["exception_id"] == selected_id), None)

        if selected_exc:
            issue = selected_exc["issue_type"]
            emp_id = selected_exc["employee_id"]
            src_id = selected_exc.get("source_record_id")

            st.info(f"**Issue Description:** {selected_exc.get('description')}")

            # Specific interactive fix per issue type
            if issue in ["MISSING_BANK_ACCOUNT", "MISSING_TAX_ID"]:
                st.write("**Fix Action:** Enter missing banking and tax details for this employee:")
                c1, c2 = st.columns(2)
                default_acc = f"ACC-{emp_id:06d}-9876" if emp_id else "ACC-000001-9876"
                default_tax = f"TAX-{emp_id:06d}-45" if emp_id else "TAX-000001-45"
                f_bank = c1.text_input("Bank Account", value=default_acc)
                f_tax = c2.text_input("Tax ID", value=default_tax)
                if st.button("💾 Save Employee Details & Fix"):
                    res = api_patch(f"/employees/{emp_id}/payroll-details", {"bank_account": f_bank, "tax_id": f_tax})
                    if res and res.get("success"):
                        st.success("Saved! Now click 'Resolve Exception' below.")

            elif issue == "DUPLICATE_TIME_ENTRY":
                st.write(f"**Fix Action:** Void duplicate submission reference for time entry `{src_id}`:")
                if st.button("🗑️ Void Duplicate Shift"):
                    res = api_post(f"/time-entries/{src_id}/mark-duplicate")
                    if res and res.get("success"):
                        st.success("Duplicate voided and hours reset! Now click 'Resolve Exception' below.")

            elif issue == "EXCESSIVE_WORKING_HOURS":
                st.write("**Fix Action:** Adjust excessive shift hours to period limit:")
                adj_hours = st.number_input("Set Shift Hours", min_value=0.0, max_value=24.0, value=8.0, step=0.5)
                time_target = src_id if src_id else (f"TIME-EMP-{emp_id:06d}-2026-01-28-EXCESS" if emp_id else "")
                if st.button("⏱️ Adjust Hours to 8.0h"):
                    res = api_patch(f"/time-entries/{time_target}", {"hours_worked": adj_hours})
                    if res and res.get("success"):
                        st.success("Hours adjusted! Now click 'Resolve Exception' below.")

            elif issue == "DUPLICATE_ALLOWANCE":
                st.write(f"**Fix Action:** Void duplicate allowance `{src_id}`:")
                if st.button("🗑️ Void Duplicate Allowance"):
                    res = api_post(f"/allowances/{src_id}/mark-duplicate")
                    if res and res.get("success"):
                        st.success("Duplicate allowance zeroed! Now click 'Resolve Exception' below.")

            elif issue == "DUPLICATE_LEAVE_DEDUCTION":
                st.write(f"**Fix Action:** Void duplicate unpaid leave deduction `{src_id}`:")
                if st.button("🗑️ Void Duplicate Deduction"):
                    res = api_post(f"/deductions/{src_id}/mark-duplicate")
                    if res and res.get("success"):
                        st.success("Duplicate leave deduction voided! Now click 'Resolve Exception' below.")

            elif issue == "UNAPPROVED_TIME_ENTRY":
                st.write("**Fix Action:** Approve pending shifts for this period:")
                if st.button("✅ Approve Employee Shifts"):
                    res = api_post("/time-entries/bulk-approve", {"employee_id": emp_id, "actor_name": active_actor["name"]})
                    if res and res.get("success"):
                        st.success("Approved shifts! Now click 'Resolve Exception' below.")

            elif issue == "PAYROLL_RECONCILIATION_MISMATCH":
                st.write(f"**Fix Action:** Recalculate net pay arithmetic for `{src_id}`:")
                if st.button("🧮 Reconcile Net Pay Arithmetic"):
                    res = api_post(f"/payroll/{src_id}/reconcile")
                    if res and res.get("success"):
                        st.success("Net pay recalculated and reconciled! Now click 'Resolve Exception' below.")

            st.markdown("---")

            # Final Step: Resolve
            st.markdown("##### 📝 Mark Exception Resolved")
            notes = st.text_input("Resolution Audit Notes:", value="Investigated source record and corrected discrepancies.")
            if st.button("✔️ Confirm & Resolve Exception", type="primary"):
                resolve_res = api_post(
                    f"/exceptions/{selected_id}/resolve",
                    {"resolution_comments": notes, "actor_name": active_actor["name"], "actor_role": active_actor["role"]}
                )
                if resolve_res and resolve_res.get("success"):
                    st.success(resolve_res.get("message"))
                    st.rerun()
                elif resolve_res:
                    st.error(resolve_res.get("message"))


# ==========================================
# TAB 3: APPROVALS & RECONCILIATION
# ==========================================

with tab3:
    st.subheader("3. Governance Approvals & Safety Check")
    st.caption("Interview Tip: Demonstrate that records with open exceptions are BLOCKED from approval, while clean records succeed.")

    # Select pay period
    period_dict = {p["period_code"]: p["id"] for p in periods} if periods else {}
    sel_period = st.selectbox("Select Pay Period:", options=list(period_dict.keys()))
    pid = period_dict[sel_period] if sel_period else 1

    period_payroll = [p for p in payroll if p.get("pay_period_id") == pid]

    if period_payroll:
        st.markdown("##### Select Record to Review & Approve:")
        sel_rec = st.selectbox(
            "Select Employee Payroll:",
            options=period_payroll,
            format_func=lambda x: f"{x['payroll_input_id']} | Net: ₹{x['net_pay']:,.2f} | Status: {x['status']}"
        )

        if sel_rec:
            # Component Gross-to-Net breakdown
            col_b, col_o, col_a, col_d, col_n = st.columns(5)
            col_b.metric("Basic Salary", f"₹{sel_rec['basic_salary']:,.2f}")
            col_o.metric("+ Overtime", f"₹{sel_rec['overtime_amount']:,.2f}")
            col_a.metric("+ Allowances", f"₹{sel_rec['allowance_total']:,.2f}")
            col_d.metric("- Deductions", f"₹{sel_rec['deduction_total'] + sel_rec['unpaid_leave_deduction']:,.2f}")
            col_n.metric("= Net Pay", f"₹{sel_rec['net_pay']:,.2f}")

            # Arithmetic verification banner
            expected = round(sel_rec['basic_salary'] + sel_rec['overtime_amount'] + sel_rec['allowance_total'] - sel_rec['deduction_total'] - sel_rec['unpaid_leave_deduction'], 2)
            if abs(round(sel_rec['net_pay'], 2) - expected) <= 0.01:
                st.success(f"✓ Reconciled: Net Pay ₹{sel_rec['net_pay']:,.2f} matches calculation formula.")
            else:
                st.error(f"✕ Mismatch! Net Pay ₹{sel_rec['net_pay']:,.2f} != Expected ₹{expected:,.2f}")

            st.markdown("---")

            # Approval Form
            st.markdown(f"**Sign-off Decision (as {active_actor['title']}):**")
            col_dec, col_btn = st.columns([2, 1])
            dec = col_dec.selectbox("Governance Decision:", ["APPROVED", "REJECTED"])

            if col_btn.button("✍️ Submit Approval Decision", type="primary"):
                app_res = api_post(
                    f"/approvals/{sel_rec['id']}",
                    {
                        "approver_name": active_actor["name"],
                        "approver_role": active_actor["role"],
                        "decision": dec,
                        "comments": "Approved via interview demo"
                    }
                )

                if app_res and app_res.get("success"):
                    st.success(f"🎉 {app_res.get('message')}")
                    st.rerun()
                elif app_res:
                    if app_res.get("status") == "BLOCKED":
                        st.error(f"🛑 **APPROVAL BLOCKED BY GOVERNANCE CHECK!**\n\n{app_res.get('message')}")
                        for iss in app_res.get("issues", []):
                            st.warning(f"• {iss}")
                    else:
                        st.error(app_res.get("message"))


# ==========================================
# TAB 4: SECURE EXPORT
# ==========================================

with tab4:
    st.subheader("4. Secure Payroll Export")
    st.caption("Interview Tip: Show that ONLY approved records export to CSV, producing deterministic PEX-YYYY-XXXXXX identifiers.")

    export_period = st.selectbox("Select Pay Period to Export:", options=list(period_dict.keys()), key="exp_p")
    exp_id = period_dict[export_period] if export_period else 1

    p_records = [p for p in payroll if p.get("pay_period_id") == exp_id]
    p_approved = [p for p in p_records if p.get("status") == "APPROVED"]
    p_draft = [p for p in p_records if p.get("status") in ["DRAFT", "PENDING"]]
    p_exported = [p for p in p_records if p.get("status") == "EXPORTED"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Eligible Approved Records", len(p_approved))
    c2.metric("Draft/Pending (Ineligible)", len(p_draft))
    c3.metric("Already Exported", len(p_exported))

    if st.button("🚀 Generate Official Payroll Export CSV", type="primary", use_container_width=True):
        with st.spinner("Generating export with immutable PEX identifier..."):
            exp_res = api_post(f"/payroll/export/{exp_id}", {"actor_name": active_actor["name"], "actor_role": active_actor["role"]})
            if exp_res and exp_res.get("success"):
                st.success(f"Export Completed! {exp_res.get('message')}")
                st.balloons()
                st.rerun()
            elif exp_res:
                st.warning(exp_res.get("message"))

    st.markdown("---")
    st.markdown("##### 📜 Historical Payroll Export Runs")
    exp_history = api_get("/payroll/exports") or []
    if exp_history:
        exp_df = pd.DataFrame(exp_history)[["export_id", "file_name", "record_count", "total_amount", "export_status", "exported_at"]]
        st.dataframe(exp_df, use_container_width=True)

        st.markdown("---")
        st.markdown("##### ⬇️ Download Any Exported Payroll CSV")
        st.caption("Select any historical export run from the list below to download its official CSV file.")

        # Let user select ANY export from history
        export_options = [
            f"{e['export_id']} | {e['file_name']} | {e['record_count']} records | ₹{e.get('total_amount', 0):,.2f} | {str(e.get('exported_at', ''))[:19]}"
            for e in exp_history
        ]

        selected_export_label = st.selectbox(
            "Choose Payroll Export to Download:",
            options=export_options,
            index=0,
            help="Select any export run from history to download its official CSV file."
        )

        selected_idx = export_options.index(selected_export_label)
        selected_exp = exp_history[selected_idx]
        target_file = selected_exp["file_name"]

        dl_path = Path("export") / target_file
        if not dl_path.exists():
            dl_path = Path("exports") / target_file

        if dl_path.exists():
            with open(dl_path, "rb") as f:
                file_bytes = f.read()

            c_down, c_info = st.columns([1, 2])
            with c_down:
                st.download_button(
                    label=f"⬇️ Download CSV ({selected_exp['export_id']})",
                    data=file_bytes,
                    file_name=target_file,
                    mime="text/csv",
                    type="primary",
                    use_container_width=True
                )
            with c_info:
                st.success(f"✓ Ready: `{target_file}` ({selected_exp['record_count']} records, total ₹{selected_exp.get('total_amount', 0):,.2f}).")

            # Inline Preview of selected CSV file
            try:
                import io
                preview_df = pd.read_csv(io.BytesIO(file_bytes))
                with st.expander(f"👁️ Preview CSV Content for {target_file} ({len(preview_df)} rows)", expanded=False):
                    st.dataframe(preview_df, use_container_width=True)
            except Exception:
                pass
        else:
            st.warning(f"File `{target_file}` not found on server disk. You can also download it from `{API_URL}/payroll/exports/download/{target_file}`.")
    else:
        st.info("No export runs recorded yet. Approve records and click 'Generate Official Payroll Export CSV'.")


# ==========================================
# TAB 5: AUDIT TRAIL & GROUND TRUTH
# ==========================================

with tab5:
    st.subheader("5. Audit Traceability & Ground Truth Verification")
    st.caption("Interview Tip: Highlight that no state change is overwritten—all actions write immutable audit records.")

    st.markdown("##### 📜 Chronological Audit Log (Recent Events)")
    if audit_logs:
        a_df = pd.DataFrame(audit_logs)[["log_id", "entity_name", "record_id", "action", "actor_role", "actor_name", "reason", "timestamp"]]
        st.dataframe(a_df, use_container_width=True)
    else:
        st.info("No audit logs recorded yet.")

    st.markdown("---")
    st.markdown("##### 🎯 Ground Truth Anomalies vs Detected Status")
    gt_file = Path("datasets/ground_truth.json")
    if gt_file.exists():
        import json
        with open(gt_file, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
        st.dataframe(pd.DataFrame(gt_data)[["rule_code", "issue_type", "record_id", "expected_decision", "description"]], use_container_width=True)
    else:
        st.info("ground_truth.json not found.")


# ==========================================
# FOOTER
# ==========================================

st.divider()
st.caption("Payroll Validation System | Stack: FastAPI + SQLModel (SQLite) + Streamlit | Fixed Seed: 20261022")
