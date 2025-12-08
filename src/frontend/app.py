import streamlit as st
import os
import time
import json
import sys
import requests
from pathlib import Path

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.core.config import settings

API_URL = "http://localhost:8000"

st.set_page_config(page_title="AI Invoice Auditor", page_icon="🛡️", layout="wide")
st.title("🛡️ AI Invoice Auditor & Safety Guard")

def trigger_processing(file_path):
    try:
        requests.get(f"{API_URL}/health", timeout=1)
        payload = {
            "message": {
                "messageId": f"gui-{time.time()}",
                "role": "user",
                "parts": [{"file": {"mediaType": "application/octet-stream", "name": os.path.basename(file_path), "fileWithUri": f"file://{file_path}"}}]
            }
        }
        res = requests.post(f"{API_URL}/v1/message:send", json=payload, timeout=10)
        return (True, res.json()) if res.status_code == 200 else (False, res.text)
    except Exception as e: return False, str(e)

with st.sidebar:
    st.header("System Controls")
    if st.button("🧹 Clear Status"):
        if (settings.DATA_DIR / "status.json").exists(): (settings.DATA_DIR / "status.json").unlink()
        st.toast("Status Cleared")
    st.info("System Ready")

tab1, tab2, tab3 = st.tabs(["🚀 Dashboard", "📊 Audit & Approval", "💬 Chat"])

with tab1:
    c1, c2 = st.columns([1, 2])
    with c1:
        st.subheader("Upload")
        uploaded = st.file_uploader("Files", type=["pdf", "png", "jpg", "json"], accept_multiple_files=True)
        if uploaded and st.button(f"Process {len(uploaded)}"):
            bar = st.progress(0)
            for i, f in enumerate(uploaded):
                p = settings.INVOICE_WATCH_DIR / f.name
                with open(p, "wb") as w: w.write(f.getbuffer())
                ok, res = trigger_processing(str(p))
                if ok: st.toast(f"Started: {f.name}")
                else: st.error(f"Failed {f.name}: {res}")
                bar.progress((i+1)/len(uploaded))
            time.sleep(1)
            st.rerun()
    with c2:
        st.subheader("Live Status")
        status_box = st.empty()
        def show_status():
            p = settings.DATA_DIR / "status.json"
            if p.exists():
                try: 
                    d = json.load(open(p))
                    status_msg = d.get('status')
                    step = d.get('step')
                    file = d.get('current_file')
                    
                    if status_msg == "Completed":
                         status_box.success(f"✅ **DONE**: {file} processed and archived!")
                    else:
                         status_box.info(f"🔄 **Processing**: {file} | **Step**: {step}")
                except: pass
            else: status_box.info("Idle")
        show_status()
        if st.button("Refresh"): st.rerun()

with tab2:
    st.subheader("Approval Center")
    all_reps = sorted(list(settings.OUTPUT_DIR.glob("*_report.json")), key=os.path.getmtime, reverse=True)
    
    pending, processed = [], []
    for r in all_reps:
        try:
            d = json.load(open(r))
            fname = d.get("meta", {}).get("file_name")
            if fname and (settings.PROCESSED_DIR / fname).exists(): processed.append(r)
            else: pending.append(r)
        except: continue

    st.markdown(f"### ⏳ Pending Review ({len(pending)})")
    if pending:
        sel = st.selectbox("Select Pending", [p.name for p in pending], key="sel_p")
        if sel:
            d = json.load(open(settings.OUTPUT_DIR / sel))
            c1, c2 = st.columns([2, 1])
            with c1:
                safe = d.get("safety", {})
                val = d.get("validation", {})
                st.metric("Safety", "Safe" if safe.get("is_safe") else "Flagged", delta_color="normal" if safe.get("is_safe") else "inverse")
                if not safe.get("is_safe"): st.error(safe.get("details"))
                if not val.get("is_valid"): 
                    with st.expander("Discrepancies"):
                        for x in val.get("discrepancies", []): st.write(f"- {x}")
            with c2:
                task_id = d.get("meta", {}).get("file_name", "")
                comment = st.text_area("Approval Comment", key="comment_area")
                if st.button("✅ Approve", type="primary"):
                    res = requests.post(f"{API_URL}/v1/tasks/{task_id}/resume", json={"comment": comment or "Approved via UI"})
                    if res.status_code == 200: 
                        st.success("Approved! Ingesting...")
                        time.sleep(2)
                        st.rerun()
                    else: st.error(res.text)
                
                pdf = settings.OUTPUT_DIR / sel.replace(".json", ".pdf")
                if pdf.exists(): 
                    st.download_button("Download PDF", open(pdf, "rb"), file_name=pdf.name)

    st.divider()
    st.markdown(f"### ✅ Processed ({len(processed)})")
    if processed:
        sel_p = st.selectbox("Select Processed", [p.name for p in processed], key="sel_proc")
        if sel_p:
            pdf_p = settings.OUTPUT_DIR / sel_p.replace(".json", ".pdf")
            if pdf_p.exists():
                st.download_button("Download PDF", open(pdf_p, "rb"), file_name=pdf_p.name, key="dl_p")
            st.json(json.load(open(settings.OUTPUT_DIR / sel_p)))

with tab3:
    st.header("💬 Chat")
    if "messages" not in st.session_state: st.session_state.messages = []
    for m in st.session_state.messages: st.chat_message(m["role"]).write(m["content"])
    if q := st.chat_input():
        st.session_state.messages.append({"role": "user", "content": q})
        st.chat_message("user").write(q)
        try:
            res = requests.post(f"{API_URL}/v1/message:send", json={"message": {"messageId": str(time.time()), "role": "user", "parts": [{"text": q}]}})
            if res.status_code == 200:
                ans = res.json().get("message", {}).get("parts", [{}])[0].get("text", "Error")
            else:
                ans = f"Error: {res.text}"
            st.session_state.messages.append({"role": "assistant", "content": ans})
            st.chat_message("assistant").write(ans)
        except Exception as e: st.error(str(e))