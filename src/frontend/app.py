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

# --- Setup Path & Config ---
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.core.config import settings

# --- Constants & Configuration ---
API_URL = "http://localhost:8000"
PAGE_TITLE = "AI Invoice Auditor"

st.set_page_config(
    page_title=PAGE_TITLE,
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Enterprise CSS & Styling ---
st.markdown("""
<style>
    /* Global Styles */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Card-like containers */
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }

    /* --- METRICS TEXT COLOR RED --- */
    div[data-testid="stMetric"] label {
        color: #d32f2f !important; /* Red Label */
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #d32f2f !important; /* Red Value */
    }
    
    /* Status Badges */
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
    
    /* Chat Input Styling - WIDER INPUT AREA */
    .stChatInput {
        position: fixed;
        bottom: 20px;
        padding-bottom: 20px;
        width: 100% !important; /* Force full width */
        max-width: 1000px; /* Optional cap */
        left: 55%;
        transform: translateX(-50%);
        z-index: 100;
    }

    /* Chat Bubbles - WIDER USER MESSAGES */
    div[data-testid="stChatMessageContent"] {
        min-width: 200px;
    }
    
    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- Helper Functions (Visualizers) ---

def format_currency(value, currency="USD"):
    try:
        return f"{float(value):,.2f} {currency}"
    except:
        return f"{value} {currency}"

def render_status_badge(status):
    status = status.upper()
    if status in ["COMPLETED", "APPROVED", "SAFE", "VALIDATED"]:
        return f'<span class="status-badge status-success">{status}</span>'
    elif status in ["PENDING", "EXTRACTED", "TRANSLATED"]:
        return f'<span class="status-badge status-warning">{status}</span>'
    else:
        return f'<span class="status-badge status-danger">{status}</span>'

def display_pdf(file_path):
    """Embeds PDF file into the Streamlit app using an iframe."""
    if not os.path.exists(file_path):
        st.error("PDF file not found.")
        return
    try:
        with open(file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error displaying PDF: {e}")

def display_structured_invoice(data: dict):
    """Intelligently renders invoice JSON data into a clean UI."""
    # 1. Header Metrics
    cols = st.columns(4)
    with cols[0]:
        st.metric("Vendor", data.get("vendor_id", "Unknown"))
    with cols[1]:
        st.metric("Invoice No", data.get("invoice_no", "N/A"))
    with cols[2]:
        st.metric("Date", data.get("invoice_date", "N/A"))
    with cols[3]:
        total = data.get("total_amount", 0)
        curr = data.get("currency", "USD")
        st.metric("Total Amount", format_currency(total, curr))

    # 2. Line Items Table
    items = data.get("line_items", [])
    if items:
        st.markdown("#### Line Items")
        df_items = pd.DataFrame(items)
        # Reorder cols for readability if they exist
        preferred_cols = ["description", "item_code", "qty", "unit_price", "total", "currency"]
        final_cols = [c for c in preferred_cols if c in df_items.columns]
        st.dataframe(
            df_items[final_cols] if final_cols else df_items,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No line item details extracted.")

def render_validation_checks(validation_report: dict):
    """Visualizes validation logic."""
    if not validation_report:
        return
    
    st.markdown("#### Validation Audit")
    
    col1, col2 = st.columns(2)
    with col1:
        is_valid = validation_report.get("is_valid", False)
        status_text = "PASS" if is_valid else "FAIL"
        st.write(f"**Data Integrity:** {status_text}")
        
        missing = validation_report.get("missing_fields", [])
        if missing:
            with st.expander("Missing Fields", expanded=True):
                for m in missing:
                    st.error(f"Missing: {m}")
    
    with col2:
        biz_status = validation_report.get("business_status", "N/A").upper()
        st.write(f"**ERP Reconciliation:** {biz_status}")
        
        discrepancies = validation_report.get("discrepancies", [])
        if discrepancies:
            with st.expander("Discrepancies", expanded=True):
                for d in discrepancies:
                    st.warning(d)

def trigger_upload(fp):
    """Triggers the backend API for a file."""
    try:
        try:
            requests.get(f"{API_URL}/health", timeout=1)
        except:
            return False, "Backend unreachable. Is ./run.sh running?"
        
        # Payload Structure: FIXED (Nested 'message' inside 'params')
        payload = {
            "id": str(uuid.uuid4()),
            "params": {
                "message": {
                    "contextId": str(uuid.uuid4()),
                    "role": "user",
                    "parts": [{
                        "file": {
                            "name": os.path.basename(fp),
                            "uri": f"file://{fp}",
                            "mediaType": "application/pdf"
                        }
                    }]
                }
            }
        }
        res = requests.post(f"{API_URL}/v1/message:send", json=payload, timeout=5)
        if res.status_code == 200:
            return True, res.json()
        return False, f"Error {res.status_code}: {res.text}"
    except Exception as e:
        return False, str(e)

# --- Sidebar Logic ---
with st.sidebar:
    st.markdown(f"## {PAGE_TITLE}")
    st.caption("Additional Capstone Project")
    st.divider()
    
    st.subheader("System Heartbeat")
    
    # Check Backend Health
    try:
        health = requests.get(f"{API_URL}/health", timeout=0.5).json()
        st.success(f"Online ({health.get('threads', 0)} Active Threads)")
    except:
        st.error("Offline")

    st.divider()
    
    # File Processor Status
    status_p = settings.DATA_DIR / "status.json"
    if status_p.exists():
        try:
            d = json.load(open(status_p))
            st.markdown(f"**Processing:** `{d.get('current_file', 'None')}`")
            st.progress(100, text=d.get('step', 'Idle'))
            st.caption(f"Status: {d.get('status', 'Active')}")
        except:
            pass
    else:
        st.info("System Idle")

    st.divider()
    auto_refresh = st.toggle("Auto-Refresh Dashboard", value=False)
    if st.button("Force Refresh", use_container_width=True):
        st.rerun()

    if auto_refresh:
        time.sleep(5)
        st.rerun()

# --- Main Layout ---

tab_dashboard, tab_audit, tab_chat = st.tabs(["Dashboard", "Audit & Approval", "Assistant"])

# ==========================
# TAB 1: DASHBOARD
# ==========================
with tab_dashboard:
    st.header("Operations Center")
    
    col_metrics, col_upload = st.columns([2, 1])
    
    with col_metrics:
        # Live Queue & History using Dataframes
        st.subheader("Live Queue")
        watch_files = []
        for f in settings.INVOICE_WATCH_DIR.glob("*.*"):
            if not f.name.startswith(".") and not f.name.endswith(".meta.json"):
                watch_files.append({
                    "Filename": f.name,
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
        for f in sorted(settings.PROCESSED_DIR.glob("*.*"), key=os.path.getmtime, reverse=True)[:10]:
             if not f.name.startswith(".") and not f.name.endswith(".meta.json"):
                processed_files.append({
                    "Filename": f.name,
                    "Processed At": datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
                    "Status": "Archived"
                })
        
        if processed_files:
            st.dataframe(pd.DataFrame(processed_files), use_container_width=True, hide_index=True)

    with col_upload:
        st.subheader("Manual Ingest")
        uploaded = st.file_uploader("Upload Invoices (PDF/IMG)", type=["pdf", "png", "jpg"], accept_multiple_files=True)
        
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

# ==========================
# TAB 2: AUDIT & APPROVAL
# ==========================
with tab_audit:
    # --- Load & Parse Reports ---
    reports = []
    if settings.OUTPUT_DIR.exists():
        for r_file in settings.OUTPUT_DIR.glob("*_report.json"):
            try:
                with open(r_file) as f:
                    content = json.load(f)
                    
                    # Normalize based on JSON structure
                    invoice_data = content.get("data") or content.get("extracted_data", {})
                    meta = content.get("meta", {})
                    
                    flat_record = {
                        "_path": str(r_file),
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
    
    # Sort by Newest
    reports.sort(key=lambda x: x["_timestamp"], reverse=True)
    
    # Filter Queues
    pending = [r for r in reports if r["_status"] not in ["COMPLETED", "APPROVED"]]
    completed = [r for r in reports if r["_status"] in ["COMPLETED", "APPROVED"]]

    # -------------------------------------------
    # SECTION 1: PENDING / NEEDS ATTENTION
    # -------------------------------------------
    if pending:
        st.error(f"[ACTION REQUIRED] {len(pending)} Invoices Require Manual Review")
        for r in pending:
            fname = r["_display_name"]
            status = r["_status"]
            
            with st.expander(f"[PENDING] {fname} | Status: {status}", expanded=True):
                c1, c2 = st.columns([2, 1])
                
                with c1:
                    display_structured_invoice(r["data"])
                    st.divider()
                    render_validation_checks(r["validation"])
                    
                    if not r["safety"].get("is_safe", True):
                        st.error(f"[SAFETY ALERT]: {r['safety'].get('details')}")
                
                with c2:
                    st.container(border=True)
                    st.subheader("Manager Action")
                    comment = st.text_area("Reason", key=f"comm_{fname}", placeholder="Approval notes...")
                    
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("Approve", key=f"btn_app_{fname}", type="primary", use_container_width=True):
                            try:
                                resp = requests.post(f"{API_URL}/v1/approve", json={"file_name": fname, "reason": comment, "approved_by": "Manager"})
                                if resp.status_code == 200:
                                    st.toast("Approved!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Error: {resp.text}")
                            except Exception as e:
                                st.error(str(e))
                    with b2:
                         st.button("Reject", key=f"btn_rej_{fname}", use_container_width=True)

    else:
        if not completed:
            st.info("No audit history found.")
        else:
            st.success("No Pending Reviews. All caught up.")

    st.divider()

    # -------------------------------------------
    # SECTION 2: COMPLETED HISTORY (Deep Dive)
    # -------------------------------------------
    st.subheader(f"Audit History ({len(completed)})")
    
    if completed:
        selected_report_name = st.selectbox("Select Invoice to Audit", [r["_display_name"] for r in completed])
        target_report = next((r for r in completed if r["_display_name"] == selected_report_name), None)
        
        if target_report:
            with st.container(border=True):
                # --- Header Section ---
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
                
                # --- Top Level Metrics ---
                inv_data = target_report["data"]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Vendor", inv_data.get("vendor_id", "N/A"))
                m2.metric("Invoice #", inv_data.get("invoice_no", "N/A"))
                m3.metric("Date", inv_data.get("invoice_date", "N/A"))
                m4.metric("Total Amount", format_currency(inv_data.get("total_amount", 0), inv_data.get("currency", "USD")))
                
                st.divider()

                # --- NESTED TABS FOR DETAILS ---
                sub_tab_data, sub_tab_compliance, sub_tab_pdf, sub_tab_raw = st.tabs(["Line Items", "Compliance & Safety", "View PDF", "Raw Data"])

                # Sub-Tab 1: Line Items Table
                with sub_tab_data:
                    items = inv_data.get("line_items", [])
                    if items:
                        df = pd.DataFrame(items)
                        cols = ["description", "item_code", "qty", "unit_price", "total", "currency"]
                        existing_cols = [c for c in cols if c in df.columns]
                        st.dataframe(
                            df[existing_cols] if existing_cols else df, 
                            use_container_width=True, 
                            hide_index=True
                        )
                        conf = inv_data.get("translation_confidence", 1.0)
                        if conf < 1.0:
                            st.caption(f"[WARN] Translation Confidence: {conf*100:.1f}%")
                    else:
                        st.info("No line items extracted.")

                # Sub-Tab 2: Compliance (Validation + Safety + PII)
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
                            for m in missing:
                                st.code(m, language=None)
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
                            for d in discrepancies:
                                st.caption(f"- {d}")
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
                            
                        with st.expander("Safety Analysis Details"):
                            st.write(safe.get("details", "No detailed analysis."))

                # Sub-Tab 3: View PDF
                with sub_tab_pdf:
                    base = Path(target_report["_path"]).stem.replace("_report", "")
                    # Look for associated PDF in output dir
                    pdf_candidates = list(settings.OUTPUT_DIR.glob(f"*{base}*.pdf"))
                    
                    if pdf_candidates:
                        pdf_path = pdf_candidates[0]
                        c_pdf_view, c_pdf_down = st.columns([4, 1])
                        
                        with c_pdf_view:
                            # Display PDF embedded
                            display_pdf(str(pdf_path))
                            
                        with c_pdf_down:
                             with open(pdf_path, "rb") as f:
                                st.download_button(
                                    "[DOWNLOAD PDF]", 
                                    f, 
                                    file_name=pdf_path.name,
                                    mime="application/pdf",
                                    use_container_width=True
                                )
                    else:
                        st.warning("No generated PDF report found for this invoice.")

                # Sub-Tab 4: Raw JSON
                with sub_tab_raw:
                    st.markdown("**System Record (JSON):**")
                    st.json(target_report)

# ==========================
# TAB 3: ASSISTANT
# ==========================
with tab_chat:
    st.header("Invoice Knowledge Assistant")
    st.caption("Ask questions about processed invoices, totals, vendors, or specific line items.")

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I can analyze your processed invoices. Ask me anything."}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if isinstance(msg["content"], dict) and "structured_data" in msg["content"]:
                # Show summary then data
                st.markdown(msg["content"].get("text_summary", ""))
                display_structured_invoice(msg["content"]["structured_data"])
            elif isinstance(msg["content"], dict):
                st.json(msg["content"])
            else:
                st.markdown(msg["content"])

    if prompt := st.chat_input("E.g., 'List all high-value items from Invoice 004'"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").markdown(prompt)

        with st.chat_message("assistant"):
            # UI PROGRESS INDICATOR
            status_container = st.status("Thinking...", expanded=True)
            try:
                status_container.write("Searching invoice database...")
                
                # Payload with nested message inside params to fix 422
                payload = {
                    "id": str(uuid.uuid4()),
                    "params": {
                        "message": {
                            "messageId": str(uuid.uuid4()), 
                            "role": "user", 
                            "parts": [{"text": prompt}]
                        }
                    }
                }
                
                # Call Backend with Extended Timeout
                response = requests.post(f"{API_URL}/v1/message:send", json=payload, timeout=120)
                
                if response.status_code == 200:
                    status_container.write("Generating answer...")
                    data = response.json()
                    
                    # Robust parsing of response
                    raw_text = data.get("message", {}).get("parts", [{}])[0].get("text", "No response content.")
                    
                    # Try to detect JSON for structured display
                    parsed_content = raw_text
                    try:
                        if "{" in raw_text and "}" in raw_text:
                            import re
                            match = re.search(r"\{.*\}", raw_text.replace("\n", ""), re.DOTALL)
                            if match:
                                json_data = json.loads(match.group(0))
                                st.write("Found structured invoice data:")
                                display_structured_invoice(json_data)
                                parsed_content = {
                                    "text_summary": raw_text.split("{")[0].strip() or "Found data:",
                                    "structured_data": json_data
                                }
                            else:
                                st.markdown(raw_text)
                        else:
                            st.markdown(raw_text)
                    except:
                        st.markdown(raw_text)
                    
                    status_container.update(label="Complete", state="complete", expanded=False)
                    st.session_state.messages.append({"role": "assistant", "content": parsed_content})
                else:
                    status_container.update(label="Error", state="error")
                    err_msg = f"Server Error {response.status_code}: {response.text}"
                    st.error(err_msg)
                    
            except Exception as e:
                status_container.update(label="Connection Failed", state="error")
                st.error(f"Connection Error: {str(e)}")