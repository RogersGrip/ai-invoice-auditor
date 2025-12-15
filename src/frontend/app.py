# ===== FILE: src/frontend/app.py =====
import streamlit as st
import os
import time
import json
import sys
import requests
import uuid
from pathlib import Path

# Setup Path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.core.config import settings

API_URL = "http://localhost:8000"

st.set_page_config(page_title="AI Invoice Auditor", page_icon="shield", layout="wide")
st.title("AI Invoice Auditor & Safety Guard")

# --- Sidebar ---
with st.sidebar:
    st.header("System Controls")
    
    # Auto-Refresh Toggle
    auto_refresh = st.toggle("Auto-Refresh (5s)", value=False)
    
    if st.button("Refresh Now 🔄"):
        st.rerun()
    
    st.divider()
    
    # Status File Display
    status_p = settings.DATA_DIR / "status.json"
    if status_p.exists():
        try:
            d = json.load(open(status_p))
            st.info(f"📄 **{d.get('current_file', 'Unknown')}**\n\n🔄 {d.get('step', 'Processing')}\n\nℹ️ {d.get('status', 'Active')}")
        except: pass
    else:
        st.success("System Idle")

    if auto_refresh:
        time.sleep(5)
        st.rerun()

# --- Helpers ---
def trigger_upload(fp):
    try:
        # Check backend health first
        try:
            requests.get(f"{API_URL}/health", timeout=1)
        except:
            return False, "Backend unreachable. Is ./run.sh running?"

        # Payload with messageId
        payload = {
            "message": {
                "messageId": str(uuid.uuid4()), 
                "role": "user",
                "parts": [{
                    "file": {
                        "name": os.path.basename(fp),
                        "fileWithUri": f"file://{fp}",
                        "mediaType": "application/pdf"
                    }
                }]
            }
        }
        res = requests.post(f"{API_URL}/v1/message:send", json=payload, timeout=5)
        if res.status_code == 200:
            return True, res.json()
        return False, f"Error {res.status_code}: {res.text}"
    except Exception as e:
        return False, str(e)

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["Dashboard", "Audit & Approval", "Chat"])

# --- Tab 1: Dashboard ---
with tab1:
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Upload Invoice")
        uploaded = st.file_uploader("Drop PDF/Image", type=["pdf", "png", "jpg", ".json", ".meta.json"], accept_multiple_files=True)
        if uploaded and st.button(f"Process {len(uploaded)} Files"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, f in enumerate(uploaded):
                status_text.text(f"Uploading {f.name}...")
                # Save to Watch Folder
                p = settings.INVOICE_WATCH_DIR / f.name
                with open(p, "wb") as w:
                    w.write(f.getbuffer())
                
                # Trigger Backend
                ok, res = trigger_upload(str(p))
                if ok:
                    st.toast(f"✅ Queued: {f.name}")
                else:
                    st.error(f"❌ Failed {f.name}: {res}")
                
                progress_bar.progress((i + 1) / len(uploaded))
            
            status_text.text("Upload Complete!")
            time.sleep(1)
            st.rerun()

    with c2:
        st.subheader("Live Queue Monitoring")
        
        # Scan Watch Folder
        watch_files = [f.name for f in settings.INVOICE_WATCH_DIR.glob("*.*") 
                       if not f.name.startswith(".") and not f.name.endswith(".meta.json")]
        
        # Scan Processed Folder (Recent)
        processed_files = sorted(
            [f for f in settings.PROCESSED_DIR.glob("*.*") if not f.name.startswith(".")],
            key=os.path.getmtime, reverse=True
        )[:5]

        col_q, col_p = st.columns(2)
        
        with col_q:
            st.info(f"**📁 In Queue ({len(watch_files)})**")
            if watch_files:
                for f in watch_files:
                    st.code(f"🕒 {f}")
            else:
                st.write("*Queue is empty.*")

        with col_p:
            st.success(f"**✅ Recently Processed**")
            if processed_files:
                for f in processed_files:
                    st.caption(f"✔ {f.name}")
            else:
                st.write("*No recent history.*")

# --- Tab 2: Audit ---
with tab2:
    st.subheader("Audit Center")
    
    # Load Reports
    reports = []
    if settings.OUTPUT_DIR.exists():
        for r_file in settings.OUTPUT_DIR.glob("*_report.json"):
            try:
                with open(r_file) as f:
                    data = json.load(f)
                    # Helper for display
                    meta = data.get("meta", {})
                    data["_display_name"] = meta.get("file_name") or meta.get("file") or r_file.name
                    data["_timestamp"] = meta.get("timestamp", "")
                    reports.append(data)
            except: pass
    
    # Sort by Newest
    reports.sort(key=lambda x: x["_timestamp"], reverse=True)
    
    # Filter
    processed = [r for r in reports if r.get("meta", {}).get("status") in ["COMPLETED", "APPROVED"]]
    pending = [r for r in reports if r.get("meta", {}).get("status") not in ["COMPLETED", "APPROVED"]]

    # 1. Processed Section
    st.markdown(f"### ✅ Completed ({len(processed)})")
    if processed:
        selected_report = st.selectbox("Select Report", [r["_display_name"] for r in processed])
        if selected_report:
            target = next((r for r in processed if r["_display_name"] == selected_report), None)
            if target:
                st.json(target)
                # Try to find PDF
                base = Path(selected_report).stem
                # Handle timestamped filenames if needed
                pdf_candidates = list(settings.OUTPUT_DIR.glob(f"*{base}*.pdf"))
                if pdf_candidates:
                    with open(pdf_candidates[0], "rb") as f:
                        st.download_button("Download PDF", f, file_name=pdf_candidates[0].name)

    st.divider()

    # 2. Pending/Failed/HITL Section
    st.markdown(f"### ⚠️ Needs Attention ({len(pending)})")
    for r in pending:
        fname = r["_display_name"]
        status = r.get("meta", {}).get("status", "UNKNOWN")
        
        with st.expander(f"🔴 {fname} [{status}]", expanded=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.write("**Issues Found:**")
                # Show discrepancies nicely
                val = r.get("validation", {})
                if val.get("discrepancies"):
                    for d in val["discrepancies"]:
                        st.error(f"❌ {d}")
                elif val.get("missing_fields"):
                    for m in val["missing_fields"]:
                        st.warning(f"⚠️ Missing: {m}")
                else:
                    st.json(r)
            
            with c2:
                st.write("#### Manager Action")
                comment = st.text_input("Approval Comment", key=f"comm_{fname}")
                if st.button("✅ Force Approve", key=f"btn_{fname}", type="primary"):
                    try:
                        resp = requests.post(f"{API_URL}/v1/approve", json={"file_name": fname, "comment": comment})
                        if resp.status_code == 200:
                            st.balloons()
                            st.success("Approved! Refreshing...")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Failed: {resp.text}")
                    except Exception as e:
                        st.error(str(e))

# --- Tab 3: Chat ---
with tab3:
    st.header("💬 Invoice Assistant")
    
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I can analyze your processed invoices. Ask me anything."}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("E.g., 'List all high-value items from Invoice 004'"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").markdown(prompt)

        with st.chat_message("assistant"):
            # UI PROGRESS INDICATOR
            status_container = st.status("Thinking...", expanded=True)
            try:
                status_container.write("🔍 Searching invoice database...")
                
                # Payload with messageId
                payload = {
                    "message": {
                        "messageId": str(uuid.uuid4()), 
                        "role": "user", 
                        "parts": [{"text": prompt}]
                    }
                }
                
                # Call Backend with Extended Timeout
                response = requests.post(f"{API_URL}/v1/message:send", json=payload, timeout=120)
                
                if response.status_code == 200:
                    status_container.write("🧠 Generating answer...")
                    data = response.json()
                    answer_text = data.get("message", {}).get("parts", [{}])[0].get("text", "No response content.")
                    
                    status_container.update(label="Complete", state="complete", expanded=False)
                    st.markdown(answer_text)
                    st.session_state.messages.append({"role": "assistant", "content": answer_text})
                else:
                    status_container.update(label="Error", state="error")
                    err_msg = f"Server Error {response.status_code}: {response.text}"
                    st.error(err_msg)
                    # st.session_state.messages.append({"role": "assistant", "content": err_msg})
                    
            except Exception as e:
                status_container.update(label="Connection Failed", state="error")
                st.error(f"Connection Error: {str(e)}")