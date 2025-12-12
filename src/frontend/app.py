# ===== FILE: src/frontend/app.py =====
import streamlit as st
import os
import time
import json
import sys
import requests
import uuid
from pathlib import Path

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.core.config import settings

API_URL = "http://localhost:8000"

st.set_page_config(page_title="AI Invoice Auditor", page_icon="🛡️", layout="wide")
st.title("🛡️ AI Invoice Auditor & Safety Guard")

# Sidebar
with st.sidebar:
    st.header("System Controls")
    if st.button("Refresh State 🔄"): st.rerun()
    st.divider()
    
    status_p = settings.DATA_DIR / "status.json"
    if status_p.exists():
        try:
            d = json.load(open(status_p))
            st.info(f"📄 **{d.get('current_file', 'Unknown')}**\n\n🔄 {d.get('step', 'Processing')}\n\nℹ️ {d.get('status', 'Active')}")
        except: pass
    else: st.success("System Idle")

# Trigger
def trigger(fp):
    try:
        requests.get(f"{API_URL}/health", timeout=1)
        payload = {
            "message": {
                "messageId": str(uuid.uuid4()),  # FIXED: Required field
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
        return res.status_code == 200, res.text
    except Exception as e: return False, str(e)

# Tabs
tab1, tab2, tab3 = st.tabs(["🚀 Dashboard", "📊 Audit & Approval", "💬 Chat"])

with tab1:
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Upload")
        uploaded = st.file_uploader("Files", type=["pdf", "png", "jpg"], accept_multiple_files=True)
        if uploaded and st.button(f"Process {len(uploaded)}"):
            bar = st.progress(0)
            for i, f in enumerate(uploaded):
                p = settings.INVOICE_WATCH_DIR / f.name
                with open(p, "wb") as w: w.write(f.getbuffer())
                ok, res = trigger(str(p))
                if ok: st.toast(f"Uploaded: {f.name}")
                else: st.error(f"Failed {f.name}: {res}")
                bar.progress((i+1)/len(uploaded))
            time.sleep(1); st.rerun()

    with c2:
        st.subheader("Monitoring")
        st.markdown(f"**Watch:** `{settings.INVOICE_WATCH_DIR}`")
        st.markdown(f"**Processed:** `{settings.PROCESSED_DIR}`")
        files = [f.name for f in settings.INVOICE_WATCH_DIR.glob("*.*") if not f.name.startswith(".")]
        if files: st.warning(f"📁 **Queue:**\n\n" + "\n".join(files))
        else: st.success("✅ Queue Empty")

with tab2:
    st.subheader("Audit Center")
    reports = []
    if settings.OUTPUT_DIR.exists():
        for r in settings.OUTPUT_DIR.glob("*_report.json"):
            try: reports.append(json.load(open(r)))
            except: pass
    
    # Sort by time
    reports.sort(key=lambda x: x.get("meta", {}).get("timestamp", ""), reverse=True)

    # Separation
    processed, pending = [], []
    for r in reports:
        meta = r.get("meta", {})
        status = meta.get("status", "UNKNOWN")
        fname = meta.get("file_name") or meta.get("file") or "unknown"
        r["display_name"] = fname
        
        if status in ["COMPLETED", "APPROVED"]: processed.append(r)
        else: pending.append(r)
    
    st.markdown(f"### ✅ Processed ({len(processed)})")
    if processed:
        sel = st.selectbox("Select Report", [r["display_name"] for r in processed])
        if sel:
            target = next((r for r in processed if r["display_name"] == sel), None)
            st.json(target)

    st.divider()
    st.markdown(f"### ⏳ Pending Action ({len(pending)})")
    
    for r in pending:
        fname = r["display_name"]
        status = r["meta"].get("status", "UNKNOWN")
        
        with st.expander(f"⚠️ {fname} [{status}]"):
            c1, c2 = st.columns([2, 1])
            with c1: st.json(r)
            with c2:
                st.write("#### Actions")
                comment = st.text_input("Comment", key=f"c_{fname}")
                if st.button("✅ Approve & Finalize", key=f"b_{fname}", type="primary"):
                    try:
                        resp = requests.post(f"{API_URL}/v1/approve", json={"file_name": fname, "comment": comment})
                        if resp.status_code == 200:
                            st.success("Approved!")
                            time.sleep(1)
                            st.rerun()
                        else: st.error(f"Error: {resp.text}")
                    except Exception as e: st.error(str(e))

with tab3:
    st.header("Chat (RAG)")
    if "messages" not in st.session_state: st.session_state.messages = []
    for m in st.session_state.messages: st.chat_message(m["role"]).markdown(m["content"])
    
    if q := st.chat_input("Ask about invoices..."):
        st.session_state.messages.append({"role": "user", "content": q})
        st.chat_message("user").markdown(q)
        try:
            # FIXED: Added messageId to payload
            payload = {
                "message": {
                    "messageId": str(uuid.uuid4()), 
                    "role": "user", 
                    "parts": [{"text": q}]
                }
            }
            res = requests.post(f"{API_URL}/v1/message:send", json=payload, timeout=60)
            
            if res.status_code == 200:
                ans = res.json().get("message", {}).get("parts", [{}])[0].get("text", "No response")
                st.session_state.messages.append({"role": "assistant", "content": ans})
                st.chat_message("assistant").markdown(ans)
            else:
                st.error(f"Server Error ({res.status_code}): {res.text}")
                
        except Exception as e: 
            st.error(f"Connection Error: {e}")