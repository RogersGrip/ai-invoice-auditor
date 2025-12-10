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
        try: 
            requests.get(f"{API_URL}/health", timeout=1)
        except: 
            return False, "Backend unreachable"
        
        payload = {
            "message": {
                "messageId": f"gui-{time.time()}",
                "role": "user",
                "parts": [{
                    "file": {
                        "mediaType": "application/octet-stream", 
                        "name": os.path.basename(file_path), 
                        "fileWithUri": f"file://{file_path}"
                    }
                }]
            }
        }
        res = requests.post(f"{API_URL}/v1/message:send", json=payload, timeout=120)
        if res.status_code == 200:
            return True, res.json()
        return False, res.text
    except Exception as e:
        return False, str(e)

with st.sidebar:
    st.header("System Controls")
    if st.button("Refresh State 🔄"):
        st.rerun()
        
    if st.button("🧹 Clear Status"):
        if (settings.DATA_DIR / "status.json").exists(): 
            (settings.DATA_DIR / "status.json").unlink()
        st.toast("Status Cleared")
        time.sleep(0.5)
        st.rerun()
    
    st.divider()
    status_placeholder = st.empty()
    
    p = settings.DATA_DIR / "status.json"
    if p.exists():
        try:
            d = json.load(open(p))
            status_placeholder.info(f"📄 **{d.get('current_file')}**\n\n🔄 {d.get('step')}\n\nℹ️ {d.get('status')}")
        except: 
            status_placeholder.warning("Status file corrupt")
    else:
        status_placeholder.success("System Idle")

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
                with open(p, "wb") as w: 
                    w.write(f.getbuffer())
                
                # Try to process everything; backend handles meta files gracefully now
                ok, res = trigger_processing(str(p))
                
                if ok: 
                    st.toast(f"Uploaded: {f.name}")
                else: 
                    st.error(f"Failed {f.name}: {res}")
                bar.progress((i+1)/len(uploaded))
            time.sleep(1)
            st.rerun()
            
    with c2:
        st.subheader("Monitoring")
        st.markdown(f"""
        - **Watch Folder:** `{settings.INVOICE_WATCH_DIR}`
        - **Processed:** `{settings.PROCESSED_DIR}`
        - **Reports:** `{settings.OUTPUT_DIR}`
        """)
        
        watch_files = list(settings.INVOICE_WATCH_DIR.glob("*.*"))
        if watch_files:
            st.write("📁 **Files in Queue:**")
            for wf in watch_files:
                st.code(wf.name)
        else:
            st.write("✅ Queue is empty.")

with tab2:
    st.subheader("Approval Center")
    
    all_reps = sorted(list(settings.OUTPUT_DIR.glob("*_report.json")), key=os.path.getmtime, reverse=True)
    
    unique_reports = {}
    for r in all_reps:
        try:
            with open(r) as f:
                d = json.load(f)
                fname = d.get("meta", {}).get("file_name")
                
                if fname and fname.endswith(".meta.json"):
                    continue
                    
                if fname and fname not in unique_reports:
                    unique_reports[fname] = (r, d)
        except: continue

    pending_list = []
    processed_list = []
    
    for fname, (r_path, d) in unique_reports.items():
        is_archived = (settings.PROCESSED_DIR / fname).exists()
        status = d.get("meta", {}).get("status")
        
        if is_archived or status == "COMPLETED":
            processed_list.append((fname, r_path, d))
        else:
            pending_list.append((fname, r_path, d))

    st.markdown(f"### ⏳ Pending Review ({len(pending_list)})")
    
    if pending_list:
        opts = {f"{fname} | {d.get('meta',{}).get('status', 'UNKNOWN')}": (fname, r_path) for fname, r_path, d in pending_list}
        sel_label = st.selectbox("Select Invoice to Review", list(opts.keys()))
        
        if sel_label:
            fname, r_path = opts[sel_label]
            d = json.load(open(r_path))
            
            c1, c2 = st.columns([2, 1])
            with c1:
                safe = d.get("safety", {})
                val = d.get("validation", {})
                
                col_a, col_b = st.columns(2)
                col_a.metric("Safety Check", "Safe" if safe.get("is_safe") else "Flagged", delta_color="normal" if safe.get("is_safe") else "inverse")
                col_b.metric("Business Logic", "Valid" if val.get("is_valid") else "Invalid", delta_color="normal" if val.get("is_valid") else "inverse")
                
                if not safe.get("is_safe"): 
                    st.error(f"Safety Issue: {safe.get('details')}")
                
                if not val.get("is_valid"):
                    st.warning("Validation Discrepancies:")
                    for x in val.get("discrepancies", []): 
                        st.write(f"- 🔴 {x}")
                    for x in val.get("missing_fields", []): 
                        st.write(f"- ⚠️ Missing: {x}")

            with c2:
                st.markdown("#### Actions")
                comment = st.text_area("Approval Comment", key="comment_area")
                if st.button("✅ Approve & Process", type="primary", use_container_width=True):
                    with st.spinner("Resuming Workflow..."):
                        res = requests.post(f"{API_URL}/v1/tasks/{fname}/resume", json={"comment": comment or "Approved via UI"})
                        if res.status_code == 200:
                            st.success("Approved! Moving to ingestion...")
                            time.sleep(1)
                            st.rerun()
                        else: 
                            st.error(f"Error: {res.text}")
                
                pdf = str(r_path).replace(".json", ".pdf")
                if os.path.exists(pdf):
                    with open(pdf, "rb") as f:
                        st.download_button("Download Report PDF", f, file_name=os.path.basename(pdf), use_container_width=True)

    st.divider()
    st.markdown(f"### ✅ Processed Archive ({len(processed_list)})")
    if processed_list:
        proc_opts = {f"{fname}": (fname, r_path) for fname, r_path, d in processed_list}
        sel_proc = st.selectbox("View Archived Report", list(proc_opts.keys()))
        if sel_proc:
            _, r_path = proc_opts[sel_proc]
            st.json(json.load(open(r_path)))

with tab3:
    st.header("💬 Invoice Assistant (RAG)")
    
    if "messages" not in st.session_state: 
        st.session_state.messages = []
        
    for m in st.session_state.messages: 
        st.chat_message(m["role"]).write(m["content"])
        
    if q := st.chat_input("Ask about invoices..."):
        st.session_state.messages.append({"role": "user", "content": q})
        st.chat_message("user").write(q)
        
        with st.chat_message("assistant"):
            with st.spinner("Searching Knowledge Base..."):
                try:
                    payload = {"message": {"messageId": str(time.time()), "role": "user", "parts": [{"text": q}]}}
                    res = requests.post(f"{API_URL}/v1/message:send", json=payload, timeout=120)
                    
                    if res.status_code == 200:
                        ans = res.json().get("message", {}).get("parts", [{}])[0].get("text", "No response.")
                    else:
                        ans = f"Error: {res.status_code} - {res.text}"
                        
                    st.session_state.messages.append({"role": "assistant", "content": ans})
                    st.write(ans)
                except Exception as e:
                    st.error(f"Connection Error: {e}")