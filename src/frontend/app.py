import streamlit as st
import os
import time
import json
import sys
import requests
import uuid
import base64
import pandas as pd
from pathlib import Path
from datetime import datetime

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.core.config import settings

API_URL = "http://localhost:8000"
PAGE_TITLE = "AI Invoice Auditor"

st.set_page_config(
    page_title=PAGE_TITLE,
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    .status-badge {
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
        text-transform: uppercase;
        border: 1px solid transparent;
    }
    .status-success { background-color: #d1e7dd; color: #0f5132; border-color: #badbcc; }
    .status-warning { background-color: #fff3cd; color: #664d03; border-color: #ffecb5; }
    .status-danger { background-color: #f8d7da; color: #842029; border-color: #f5c2c7; }
    .stChatInput {
        position: fixed; bottom: 20px; padding-bottom: 20px;
        width: 100% !important; max-width: 1000px;
        left: 55%; transform: translateX(-50%); z-index: 100;
    }
    div[data-testid="stChatMessageContent"] { min-width: 200px; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

def format_currency(value, currency="USD"):
    try:
        return f"{float(value):,.2f} {currency}"
    except:
        return f"{value} {currency}"

def render_status_badge(status):
    status = status.upper()
    if status in ["COMPLETED", "APPROVED", "SAFE", "VALIDATED"]:
        return f'<span class="status-badge status-success">{status}</span>'
    elif status in ["PENDING", "EXTRACTED", "TRANSLATED", "AWAITING_APPROVAL"]:
        return f'<span class="status-badge status-warning">{status}</span>'
    else:
        return f'<span class="status-badge status-danger">{status}</span>'

def display_pdf(file_path):
    if not os.path.exists(file_path):
        st.error("File not found.")
        return
    try:
        if file_path.lower().endswith(".pdf"):
            with open(file_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
        else:
            st.image(file_path, width=700)
    except Exception as e:
        st.error(f"Error displaying file: {e}")

def trigger_upload(fp):
    """Call the clean /v1/upload endpoint."""
    try:
        try:
            requests.get(f"{API_URL}/health", timeout=1)
        except:
            return False, "Backend unreachable. Is ./run.sh running?"
            
        payload = {"file_path": str(fp), "file_type": "application/json" if fp.endswith(".json") else "application/pdf"}
        
        res = requests.post(f"{API_URL}/v1/upload", json=payload, timeout=5)
        if res.status_code == 200:
            return True, res.json()
        return False, f"Error {res.status_code}: {res.text}"
    except Exception as e:
        return False, str(e)

# --- Sidebar ---
with st.sidebar:
    st.markdown(f"## {PAGE_TITLE}")
    st.caption("Additional Capstone Project")
    st.divider()
    
    st.subheader("System Heartbeat")
    try:
        health = requests.get(f"{API_URL}/health", timeout=0.5).json()
        st.success(f"Online ({health.get('threads', 0)} Active Threads)")
    except:
        st.error("Offline")
        
    st.divider()
    
    status_p = settings.DATA_DIR / "status.json"
    if status_p.exists():
        try:
            d = json.load(open(status_p))
            st.markdown(f"**Processing:** `{d.get('current_file', 'None')}`")
            st.progress(100, text=d.get('step', 'Idle'))
            st.caption(f"Status: {d.get('status', 'Active')}")
        except: pass
    else:
        st.info("System Idle")
        
    st.divider()
    auto_refresh = st.toggle("Auto-Refresh Dashboard", value=False)
    if st.button("Force Refresh", use_container_width=True): st.rerun()
    if auto_refresh:
        time.sleep(5)
        st.rerun()

# --- Tabs ---
tab_dashboard, tab_audit, tab_chat = st.tabs(["Dashboard", "Audit & Approval", "Assistant"])

with tab_dashboard:
    st.header("Operations Center")
    col_metrics, col_upload = st.columns([2, 1])
    
    with col_metrics:
        st.subheader("Live Queue")
        watch_files = []
        if settings.INVOICE_WATCH_DIR.exists():
            for f in settings.INVOICE_WATCH_DIR.glob("*.*"):
                if not f.name.startswith(".") and not f.name.endswith(".meta.json"):
                    watch_files.append({
                        "File": f.name,
                        "Detected": datetime.fromtimestamp(f.stat().st_mtime).strftime('%H:%M:%S'),
                        "Size (KB)": round(f.stat().st_size / 1024, 2)
                    })
        if watch_files:
            st.dataframe(pd.DataFrame(watch_files), use_container_width=True, hide_index=True)
        else:
            st.info("Queue is empty. Waiting for invoices...")
            
        st.divider()
        st.subheader("Recently Processed")
        processed_files = []
        if settings.PROCESSED_DIR.exists():
            for f in sorted(settings.PROCESSED_DIR.glob("*.*"), key=os.path.getmtime, reverse=True)[:10]:
                if not f.name.startswith(".") and not f.name.endswith(".meta.json"):
                    processed_files.append({
                        "File": f.name,
                        "Archived": datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
                        "Status": "Archived"
                    })
        if processed_files:
            st.dataframe(pd.DataFrame(processed_files), use_container_width=True, hide_index=True)
            
    with col_upload:
        st.subheader("Manual Ingest")
        uploaded = st.file_uploader("Upload Invoices", type=["pdf", "png", "jpg", "json"], accept_multiple_files=True)
        
        if uploaded and st.button(f"Process {len(uploaded)} Files", type="primary", use_container_width=True):
            status_bar = st.status("Initiating Upload...", expanded=True)
            for f in uploaded:
                status_bar.write(f"Uploading {f.name}...")
                p = settings.INVOICE_WATCH_DIR / f.name
                with open(p, "wb") as w:
                    w.write(f.getbuffer())
                
                ok, res = trigger_upload(str(p))
                if ok:
                    status_bar.write(f"Triggered Workflow: {f.name}")
                else:
                    status_bar.error(f"Failed {f.name}: {res}")
            status_bar.update(label="Upload Batch Complete", state="complete", expanded=False)
            time.sleep(1)
            st.rerun()

with tab_audit:
    reports = []
    if settings.OUTPUT_DIR.exists():
        for r_file in settings.OUTPUT_DIR.glob("*_report.json"):
            try:
                with open(r_file) as f:
                    content = json.load(f)
                    invoice_data = content.get("data") or content.get("extracted_data", {})
                    meta = content.get("meta", {})
                    flat_record = {
                        "path": str(r_file),
                        "_display_name": meta.get("file_name", r_file.name),
                        "_timestamp": meta.get("timestamp", ""),
                        "_status": meta.get("status", "UNKNOWN"),
                        "data": invoice_data,
                        "meta": meta,
                        "validation": content.get("validation", {}),
                        "safety": content.get("safety", {}),
                        "approval": content.get("approval")
                    }
                    reports.append(flat_record)
            except Exception as e:
                pass
    reports.sort(key=lambda x: x["_timestamp"], reverse=True)
    
    pending = [r for r in reports if r["_status"] not in ["COMPLETED", "APPROVED", "APPROVED_BY_HITL", "REJECTED"]]
    completed = [r for r in reports if r["_status"] in ["COMPLETED", "APPROVED", "APPROVED_BY_HITL", "REJECTED"]]
    
    if pending:
        st.error(f"[ACTION REQUIRED] {len(pending)} Invoices Require Manual Review")
        
        st.markdown("### Pending Reviews")
        h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns([2, 1, 1, 1, 2])
        h_col1.markdown("**File Name**")
        h_col2.markdown("**Issue**")
        h_col3.markdown("**Vendor**")
        h_col4.markdown("**Total**")
        h_col5.markdown("**Actions**")
        st.divider()

        for r in pending:
            fname = r["_display_name"]
            status = r["_status"]
            data = r["data"]
            vendor = data.get("vendor_id", "Unknown")
            total = format_currency(data.get("total_amount", 0), data.get("currency", "USD"))
            
            r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([2, 1, 1, 1, 2])
            r_col1.write(fname)
            r_col2.markdown(f"**{status}**")
            r_col3.write(vendor)
            r_col4.write(total)
            
            with r_col5:
                btn_col1, btn_col2 = st.columns(2)
                if btn_col1.button("Approve", key=f"app_{fname}", type="primary", use_container_width=True):
                     try:
                        resp = requests.post(f"{API_URL}/v1/approve", json={
                            "file_name": fname,
                            "reason": "Approved via Table UI",
                            "approved_by": "Manager"
                        })
                        if resp.status_code == 200:
                            st.toast(f"Approved {fname}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Error: {resp.text}")
                     except Exception as e:
                        st.error(str(e))

                if btn_col2.button("Reject", key=f"rej_{fname}", type="secondary", use_container_width=True):
                    try:
                        resp = requests.post(f"{API_URL}/v1/reject", json={
                            "file_name": fname,
                            "reason": "Rejected via Table UI",
                            "rejected_by": "Manager"
                        })
                        if resp.status_code == 200:
                            st.toast(f"Rejected {fname}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Error: {resp.text}")
                    except Exception as e:
                        st.error(str(e))
            
            with st.expander(f"View Issues for {fname}"):
                val = r["validation"]
                safe = r["safety"]
                if not val.get("is_valid", True):
                    st.write("**Data Validation Failed:**")
                    for m in val.get("missing_fields", []): st.code(f"Missing: {m}")
                if val.get("business_status") == "mismatch":
                    st.write("**Business Logic Mismatch:**")
                    for d in val.get("discrepancies", []): st.warning(d)
                if not safe.get("is_safe", True):
                    st.write("**Safety / PII Alert:**")
                    if safe.get("pii_detected"):
                        st.error(f"PII Found: {', '.join(safe.get('pii_detected'))}")
                    if safe.get("details"):
                        st.write(f"Details: {safe.get('details')}")
            st.divider()
    else:
        if completed:
            st.success("No Pending Reviews. All caught up.")
        else:
            st.info("No invoices processed yet.")
            
    if completed:
        st.subheader(f"Audit History ({len(completed)})")
        selected_report_name = st.selectbox("Select Invoice to Audit", [r["_display_name"] for r in completed])
        target_report = next((r for r in completed if r["_display_name"] == selected_report_name), None)
        
        if target_report:
            with st.container(border=True):
                h_col1, h_col2 = st.columns([3, 1])
                with h_col1:
                    st.markdown(f"### {target_report['_display_name']}")
                    metadata = target_report['meta'].get('metadata', {})
                    src = metadata.get('source', 'Unknown Source')
                    ts = metadata.get('ingest_timestamp', 'N/A')
                    st.caption(f"**Source:** {src} | **Ingested:** {ts}")
                with h_col2:
                    st.markdown(render_status_badge(target_report["_status"]), unsafe_allow_html=True)
                st.divider()
                inv_data = target_report["data"]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Vendor", inv_data.get("vendor_id", "N/A"))
                m2.metric("Invoice #", inv_data.get("invoice_no", "N/A"))
                m3.metric("Date", inv_data.get("invoice_date", "N/A"))
                m4.metric("Total Amount", format_currency(inv_data.get("total_amount", 0), inv_data.get("currency", "USD")))
                st.divider()
                sub_tab_data, sub_tab_compliance, sub_tab_pdf, sub_tab_raw = st.tabs(["Line Items", "Compliance & Safety", "View PDF", "Raw Data"])
                
                with sub_tab_data:
                    items = inv_data.get("line_items", [])
                    if items:
                        df = pd.DataFrame(items)
                        cols = ["description", "item_code", "qty", "unit_price", "total", "currency"]
                        existing_cols = [c for c in cols if c in df.columns]
                        st.dataframe(df[existing_cols] if existing_cols else df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No line items extracted.")
                        
                with sub_tab_compliance:
                    col_data_val, col_biz_val, col_safety = st.columns(3)
                    with col_data_val:
                        st.markdown("#### Data Integrity")
                        val = target_report["validation"]
                        is_valid = val.get("is_valid", False)
                        st.write(f"**Format Valid:** {'[PASS]' if is_valid else '[FAIL]'}")
                        missing = val.get("missing_fields", [])
                        if missing:
                            st.warning(f"**Missing Fields:** {len(missing)}")
                            for m in missing: st.code(m, language=None)
                        else:
                            st.success("All required fields present")
                    with col_biz_val:
                        st.markdown("#### Business Logic")
                        biz_status = val.get("business_status", "N/A").upper()
                        erp_status = "[MATCH]" if biz_status == "MATCH" else "[WARNING]"
                        st.write(f"**ERP Status:** {erp_status} {biz_status}")
                        discrepancies = val.get("discrepancies", [])
                        if discrepancies:
                            st.error(f"**Discrepancies:** {len(discrepancies)}")
                            for d in discrepancies: st.caption(f"- {d}")
                        else:
                            st.success("Matches ERP Records")
                    with col_safety:
                        st.markdown("#### Safety & PII")
                        safe = target_report["safety"]
                        is_safe = safe.get("is_safe", True)
                        st.write(f"**Content Safety:** {'[SAFE]' if is_safe else '[FLAGGED]'}")
                        pii = safe.get("pii_detected", [])
                        if pii:
                            st.warning(f"**PII Detected:** {len(pii)}")
                            st.write(", ".join([f"`{p}`" for p in pii]))
                        else:
                            st.success("No PII Detected")
                        if safe.get("details"):
                            with st.expander("Safety Analysis Details"):
                                st.write(safe.get("details"))
                
                with sub_tab_pdf:
                    base_report_name = Path(target_report["path"]).stem
                    generated_pdf = settings.OUTPUT_DIR / f"{base_report_name}.pdf"
                    if generated_pdf.exists():
                        c_pdf_view, c_pdf_down = st.columns([4, 1])
                        with c_pdf_view:
                            display_pdf(str(generated_pdf))
                        with c_pdf_down:
                            with open(generated_pdf, "rb") as f:
                                st.download_button("Download Report", f, file_name=generated_pdf.name, mime="application/pdf", use_container_width=True)
                    else:
                        st.warning("No generated PDF report found.")
                
                with sub_tab_raw:
                    st.markdown("**System Record (JSON):**")
                    st.json(target_report)

with tab_chat:
    st.header("Invoice Assistant")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I can analyze your processed invoices. Ask me anything."}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("E.g., 'List all high-value items from Invoice 004'"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").markdown(prompt)
        
        with st.chat_message("assistant"):
            status_container = st.status("Thinking...", expanded=True)
            try:
                status_container.write("Searching invoice database...")
                
                payload = {"query": prompt}
                
                response = requests.post(f"{API_URL}/v1/chat", json=payload, timeout=120)
                
                if response.status_code == 200:
                    status_container.write("Generating answer...")
                    data = response.json()
                    answer_text = data.get("answer", "No answer found.")
                    
                    status_container.update(label="Complete", state="complete", expanded=False)
                    st.markdown(answer_text)
                    st.session_state.messages.append({"role": "assistant", "content": answer_text})
                else:
                    status_container.update(label="Error", state="error")
                    err_msg = f"Server Error {response.status_code}: {response.text}"
                    st.error(err_msg)
            except Exception as e:
                status_container.update(label="Connection Failed", state="error")
                st.error(f"Connection Error: {str(e)}")