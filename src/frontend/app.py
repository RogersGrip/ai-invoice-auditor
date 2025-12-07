import streamlit as st
import os
import shutil
import time
import json
import sys
from pathlib import Path

# Add project root to sys.path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Config
INVOICE_DIR = project_root / "data" / "invoices"
PROCESSED_DIR = project_root / "data" / "processed"
OUTPUT_DIR = project_root / "outputs" / "reports"
STATUS_FILE = project_root / "data" / "status.json"

# Ensure directories exist
INVOICE_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="AI Invoice Auditor",
    page_icon="🧾", 
    layout="wide"
)

# --- Sidebar Controls ---
st.sidebar.title("Controls")
auto_refresh = st.sidebar.toggle("Enable Live Auto-Refresh (2s)", value=False)
if st.sidebar.button("🧹 Clear Status"):
    if STATUS_FILE.exists():
        STATUS_FILE.unlink()
    st.toast("Status cleared!")

st.title("🤖 AI Invoice Auditor Agent")

# Tabs
tab1, tab2, tab3 = st.tabs(["📤 Upload & Process", "📊 Audit Reports", "💬 Chat with Invoices"])

with tab1:
    # 1. Agent Status Cards (Visualizing the Pipeline)
    st.subheader("🕵️‍♀️ Invoice Auditor Agents")
    
    # Responsive Columns
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        st.info("**👁️ OCR Agent**\n\n*Watching Folder*\n\nStatus: 🟢 Active")
    with c2:
        st.info("**🧠 Translator**\n\n*Standardizing Data*\n\nStatus: 🟢 Active")
    with c3:
        st.info("**✅ Validator**\n\n*Checking Rules*\n\nStatus: 🟢 Active")
    with c4:
        st.info("**📝 Reporter**\n\n*Generating PDF/JSON*\n\nStatus: 🟢 Active")
        
    st.divider()
    
    # NEW: Visual Progress Tracker (Properly containerized)
    st.subheader("🚀 Live Processing Status")
    
    status_container = st.empty()
    
    def render_status():
        if STATUS_FILE.exists():
            try:
                # Read with retry in case of lock
                content = "{}"
                for _ in range(3):
                    try:
                        with open(STATUS_FILE, "r") as f:
                            content = f.read()
                        if content: break
                    except:
                        time.sleep(0.1)
                
                if not content: return
                
                current_status = json.loads(content)
                steps = ["Extraction", "Translation", "Validation", "Reporting", "Ingestion", "Completed"]
                current_step = current_status.get("step", "Idle").capitalize()
                
                # Check for Failure
                status_text = current_status.get('status', '').lower()
                is_failed = "fail" in status_text or "error" in status_text
                
                step_map = {s: i for i, s in enumerate(steps)}
                active_idx = step_map.get(current_step, 0 if not is_failed else len(steps))

                with status_container.container():
                    # Progress Bar
                    # If failed, show red or full bar with error
                    st.progress((active_idx + 1) / len(steps))
                    
                    st.caption(f"File: **{current_status.get('current_file', 'Unknown')}**")
                    if is_failed:
                        st.error(f"❌ **Failed at {current_step}**: {status_text}")
                    else:
                        st.success(f"👉 **Step: {current_step}** - {current_status.get('status', 'Processing...')}")
                    

                    if current_step == "Completed":
                        last_file = st.session_state.get("last_balloon_file")
                        current_file = current_status.get("current_file")

                        if last_file != current_file:
                            st.session_state["last_balloon_file"] = current_file
                            st.toast("Processing Completed! 🚀")
            except Exception as e:
                status_container.error(f"Error reading status: {e}")
        else:
            status_container.info("⏳ Waiting for tasks... System is idle.")

    # Render once
    render_status()
    
    # Auto-refresh loop
    if auto_refresh:
        time.sleep(2)
        st.rerun()

    st.divider()

    # Upload Section
    st.header("📤 Upload Invoices")
    uploaded_files = st.file_uploader(
        "Drop invoice PDF/Images or JSON metadata here", 
        type=['pdf', 'png', 'jpg', 'jpeg', 'txt', 'json'],
        accept_multiple_files=True
    )

    if uploaded_files:
        if st.button("Submit All for Processing", type="primary"):
            progress_bar = st.progress(0)
            for i, uploaded_file in enumerate(uploaded_files):
                save_path = INVOICE_DIR / uploaded_file.name
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            st.success(f"Successfully uploaded {len(uploaded_files)} files.")
            time.sleep(1)
            st.rerun()

    # Dashboard stats
    st.divider()
    c1, c2, c3 = st.columns(3)
    
    # Stats Calculation
    processed_count = len(list(PROCESSED_DIR.glob("*.*"))) // 2 if PROCESSED_DIR.exists() else 0
    report_count = len(list(OUTPUT_DIR.glob("*.pdf"))) if OUTPUT_DIR.exists() else 0
    pending_count = len(list(INVOICE_DIR.glob("*.*"))) if INVOICE_DIR.exists() else 0

    c1.metric("✅ Processed Invoices", processed_count)
    c2.metric("📄 Reports Generated", report_count)
    c3.metric("⏳ Pending Queue", pending_count)

with tab2:
    # Reports Viewer
    st.header("📊 Audit Reports")
    
    col_ctrl1, col_ctrl2 = st.columns([0.8, 0.2])
    with col_ctrl2:
        if st.button("🔄 Refresh List"):
            st.rerun()

    # Get both HTML and JSON reports
    json_reports = []
    if OUTPUT_DIR.exists():
        json_reports = sorted(list(OUTPUT_DIR.glob("*_report.json")), key=os.path.getmtime, reverse=True)
    
    # --- HITL: Filter State ---
    filter_status = st.radio("Filter by Status", ["All", "Failed / Action Required", "Approved (Auto + Manual)"], horizontal=True)

    filtered_files = []
    file_map = {}
    
    for j_path in json_reports:
        try:
            with open(j_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            is_valid_auto = data.get("validation", {}).get("is_valid", False)
            is_approved_human = data.get("validation", {}).get("approved_by_human", False)
            
            status_label = "Approved" if (is_valid_auto or is_approved_human) else "Failed"
            
            include = True
            if filter_status == "Failed / Action Required" and status_label == "Approved": include = False
            if filter_status == "Approved (Auto + Manual)" and status_label == "Failed": include = False
            
            if include:
                base_name = j_path.name.replace("_report.json", "")
                label = f"{'✅' if status_label == 'Approved' else '❌'} {base_name}"
                filtered_files.append(label)
                file_map[label] = j_path
        except:
            continue

    if filtered_files:
        selected_label = st.selectbox("Select Report to View", filtered_files)
        
        if selected_label:
            json_path = file_map[selected_label]
            base_name = json_path.name.replace("_report.json", "")
            
            # Load Data
            with open(json_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
                
            val_data = report_data.get("validation", {})
            is_valid = val_data.get("is_valid", False)
            is_manual = val_data.get("approved_by_human", False)
            
            # Paths
            html_path = OUTPUT_DIR / f"{base_name}_report.html"
            pdf_path = OUTPUT_DIR / f"{base_name}_report.pdf"

            # --- Status Header & Actions ---
            st.divider()
            s_col1, s_col2 = st.columns([3, 1])
            with s_col1:
                if is_valid:
                    st.success(f"### ✅ Automatically Approved")
                elif is_manual:
                    st.success(f"### ✅ Manually Approved by Human")
                else:
                    st.error(f"### ❌ Validation Failed - Action Required")
            
            with s_col2:
                # HITL Action Button
                if not is_valid:
                    if not is_manual:
                        if st.button("👍 Verify & Approve", type="primary"):
                            report_data["validation"]["approved_by_human"] = True
                            report_data["meta"]["status"] = "APPROVED_MANUAL"
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(report_data, f, indent=2)
                            st.toast("Report Manually Approved!")
                            time.sleep(1)
                            st.rerun()
                    else:
                        if st.button("↩️ Revoke Approval"):
                            report_data["validation"]["approved_by_human"] = False
                            report_data["meta"]["status"] = "FAILED (Revoked)"
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(report_data, f, indent=2)
                            st.toast("Approval Revoked.")
                            time.sleep(1)
                            st.rerun()
            st.divider()

            # Tabs for view modes
            view_tab1, view_tab2, view_tab3 = st.tabs(["📄 Web Report", "⬇️ Data & Downloads", "🔍 Raw JSON"])
            
            with view_tab1:
                if html_path.exists():
                    with open(html_path, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    
                    # Monkey-patch visual status in HTML for preview? 
                    # Simpler just to show the frame. The HTML on disk isn't updated unless we regenerate it.
                    # We could regenerate HTML here if we wanted consistency, but UI header is enough.
                    st.components.v1.html(html_content, height=800, scrolling=True)
                else:
                    st.warning("HTML report missing. View JSON tab.")

            with view_tab2:
                st.subheader("Downloads")
                c1, c2 = st.columns(2)
                
                if pdf_path.exists():
                    with open(pdf_path, "rb") as f:
                        pdf_data = f.read()
                    c1.download_button("📄 Download PDF", pdf_data, f"{base_name}.pdf", "application/pdf")
                
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        json_data = f.read().encode('utf-8')
                    c2.download_button("📊 Download JSON", json_data, f"{base_name}.json", "application/json")

            with view_tab3:
                st.json(report_data)
    else:
        st.info("No matching reports found.")

with tab3:
    st.header("💬 Chat with Invoices")
    st.caption("Ask questions about processed invoices.")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask a question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing invoices..."):
                try:
                    from src.workflows.rag_graph import create_rag_graph
                    rag_app = create_rag_graph()
                    response = rag_app.invoke({"query": prompt})
                    answer = response.get("answer", "I couldn't find an answer.")
                    
                    st.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                    
                    with st.expander("Sources & Reflection"):
                        eval_data = response.get("evaluation", {})
                        if isinstance(eval_data, str):
                            try:
                                s = eval_data.find('{')
                                e = eval_data.rfind('}')
                                if s != -1 and e != -1: eval_data = json.loads(eval_data[s:e+1])
                            except: pass
                        
                        if isinstance(eval_data, dict) and "context_precision" in eval_data:
                            metrics = {
                                "Metric": ["Context Precision", "Context Recall", "Faithfulness", "Answer Relevance", "Entity Recall"],
                                "Score": [
                                    eval_data.get("context_precision", 0.0),
                                    eval_data.get("context_recall", 0.0),
                                    eval_data.get("faithfulness", 0.0),
                                    eval_data.get("answer_relevance", 0.0),
                                    eval_data.get("context_entity_recall", 0.0)
                                ]
                            }
                            st.table(metrics)
                            st.write(f"**Reasoning:** {eval_data.get('reasoning', 'N/A')}")
                        else:
                            st.json(eval_data)
                        
                        ctx = response.get("context", "")
                        if isinstance(ctx, list): ctx = "\n\n".join([str(c) for c in ctx])
                        st.text(str(ctx)[:1000] + "...")
                        
                except Exception as e:
                    st.error(f"Error: {e}")
