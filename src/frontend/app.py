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
INVOICE_DIR = "data/invoices"
PROCESSED_DIR = "data/processed"
OUTPUT_DIR = "outputs/reports"

st.set_page_config(
    page_title="AI Invoice Auditor",
    page_icon="🧾", 
    layout="wide"
)

# Auto-refresh logic
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False

def toggle_refresh():
    st.session_state.auto_refresh = not st.session_state.auto_refresh

st.sidebar.title("Controls")
st.sidebar.checkbox("Enable Auto-Refresh (5s)", value=st.session_state.auto_refresh, on_change=toggle_refresh)

if st.session_state.auto_refresh:
    time.sleep(5)
    st.rerun()

st.title("🤖 AI Invoice Auditor Agent")

# Tabs
tab1, tab2, tab3 = st.tabs(["📤 Upload & Process", "📊 Audit Reports", "💬 Chat with Invoices"])

with tab1:
    # 1. Agent Status Cards (Visualizing the Pipeline)
    st.subheader("🕵️‍♀️ Invoice Auditor Agents")
    
    # Mock status for visualization since we don't have a real-time event bus to the Streamlit UI yet
    # In a real app, this would query a status DB
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.info("**👁️ OCR Agent**\n\n*Watching Folder*\n\nStatus: 🟢 Active")
    with c2:
        st.info("**🧠 ADK Translator**\n\n*Standardizing Data*\n\nStatus: 🟢 Active")
    with c3:
        st.info("**✅ Validator**\n\n*Checking Rules*\n\nStatus: 🟢 Active")
    with c4:
        st.info("**📝 Reporter**\n\n*Generating PDF/JSON*\n\nStatus: 🟢 Active")
        
    with c4:
        st.info("**📝 Reporter**\n\n*Generating PDF/JSON*\n\nStatus: 🟢 Active")
        
    st.divider()
    
    # NEW: Visual Progress Tracker
    st.subheader("🚀 Live Processing Status")
    status_file = Path("data/status.json")
    if status_file.exists():
        try:
            with open(status_file, "r") as f:
                current_status = json.load(f)
            
            # Check if status is stale (> 2 minutes old)
            # User requested to keep status until new file is shown
            # import time
            # last_update = current_status.get("timestamp", 0)
            # if time.time() - last_update > 120:
            #      st.info("System is ready. (Last run finished)")
            # else:
            
            # Determine active step index
            steps = ["Extraction", "Translation", "Validation", "Reporting", "Ingestion", "Completed"]
            current_step = current_status.get("step", "Idle").capitalize()
            
            # Simple mapping
            step_map = {
                "Extraction": 0, "Translation": 1, "Validation": 2, 
                "Reporting": 3, "Ingestion": 4, "Completed": 5
            }
            
            active_idx = step_map.get(current_step, 0)
            
            # Progress Bar
            st.progress((active_idx + 1) / len(steps))
            
            st.caption(f"Currently processing: **{current_status.get('current_file', 'Unknown')}**")
            st.info(f"👉 **Step: {current_step}** - {current_status.get('status', '')}")
            
        except Exception as e:
            st.error(f"Error reading status: {e}")
            st.warning("Waiting for updates...")
            
    else:
        st.info("System is ready. Upload a file to see live progress.")
        
    # Debug Info
    with st.expander("🛠️ Debug Status Info"):
        st.write(f"Looking for status at: `{status_file.absolute()}`")
        if status_file.exists():
            with open(status_file, "r") as f:
                st.code(f.read(), language="json")
        else:
            st.write("Status file does not exist.")

    st.divider()

    # Upload Section
    st.header("📤 Upload Invoices")
    uploaded_files = st.file_uploader(
        "Drop invoice PDF/Images or JSON metadata here", 
        type=['pdf', 'png', 'jpg', 'jpeg', 'txt', 'json'],
        accept_multiple_files=True
    )

    if uploaded_files:
        if st.button("Submit All for Processing"):
            progress_bar = st.progress(0)
            for i, uploaded_file in enumerate(uploaded_files):
                save_path = os.path.join(INVOICE_DIR, uploaded_file.name)
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            st.success(f"Successfully uploaded {len(uploaded_files)} files to the processing queue.")
            st.info("The agents will pick them up shortly.")
            time.sleep(1)
            st.rerun()

    # Dashboard stats
    st.divider()
    col1, col2, col3 = st.columns(3)
    try:
        processed_count = len(list(Path(PROCESSED_DIR).glob("*.*"))) // 2 
        report_count = len(list(Path(OUTPUT_DIR).glob("*.pdf")))
        pending_count = len(list(Path(INVOICE_DIR).glob("*.*")))
    except:
        processed_count = 0
        report_count = 0
        pending_count = 0

    col1.metric("✅ Processed Invoices", processed_count)
    col2.metric("📄 Reports Generated", report_count)
    col3.metric("⏳ Pending Queue", pending_count)

with tab2:
    # Reports Viewer
    st.header("📊 Audit Reports")
    
    col_ctrl1, col_ctrl2 = st.columns([0.8, 0.2])
    with col_ctrl2:
        if st.button("🔄 Refresh List"):
            st.rerun()

    # Get both HTML and JSON reports
    try:
        html_reports = sorted(list(Path(OUTPUT_DIR).glob("*.html")), key=os.path.getmtime, reverse=True)
    except:
        html_reports = []
    
    if html_reports:
        # 1. SELECT instead of iterating all
        selected_file = st.selectbox("Select Report to View", [r.name for r in html_reports])
        
        if selected_file:
            base_name = selected_file.replace(".html", "")
            
            # Paths
            html_path = Path(OUTPUT_DIR) / selected_file
            pdf_path = Path(OUTPUT_DIR) / f"{base_name}.pdf"
            json_path = Path(OUTPUT_DIR) / f"{base_name}.json"

            # Tabs for view modes
            view_tab1, view_tab2, view_tab3 = st.tabs(["📄 Web Report", "⬇️ Data & Downloads", "🔍 Raw JSON"])
            
            with view_tab1:
                if html_path.exists():
                    with open(html_path, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    st.components.v1.html(html_content, height=800, scrolling=True)

            with view_tab2:
                st.subheader("Downloads")
                st.caption("Select a file above to enable downloads.")
                
                # Single set of buttons for the SELECTED file only
                c1, c2 = st.columns(2)
                
                if pdf_path.exists():
                    with open(pdf_path, "rb") as f:
                        pdf_data = f.read()
                    c1.download_button(
                        label="📄 Download PDF", 
                        data=pdf_data, 
                        file_name=f"{base_name}.pdf", 
                        mime="application/pdf",
                        key=f"btn_pdf_selected"
                    )
                
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        json_data = f.read().encode('utf-8')
                    c2.download_button(
                        label="📊 Download JSON", 
                        data=json_data, 
                        file_name=f"{base_name}.json", 
                        mime="application/json",
                        key=f"btn_json_selected"
                    )

            with view_tab3:
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        st.json(json.load(f))
                else:
                    st.warning("JSON report not found.")

    else:
        st.info("No reports found yet. Process an invoice to verify.")

with tab3:
    st.header("💬 Chat with Invoices")
    st.caption("Ask questions about processed invoices (e.g., 'What is the total amount for INV-004?')")
    
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
                        # Parse and Format Metrics
                        eval_data = response.get("evaluation", {})
                        if isinstance(eval_data, str):
                            try:
                                # Start searching for the first '{' for JSON start
                                start_index = eval_data.find('{')
                                # Start searching for the last '}' for JSON end
                                end_index = eval_data.rfind('}')
                                
                                if start_index != -1 and end_index != -1:
                                    json_str = eval_data[start_index : end_index + 1]
                                    eval_data = json.loads(json_str)
                                else:
                                    eval_data = {} # Or handle valid non-JSON string
                            except json.JSONDecodeError:
                                pass
                        
                        if isinstance(eval_data, dict) and "context_precision" in eval_data:
                            # Create a nice metrics table
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

                        st.markdown("**Context Used:**")
                        
                        # Handle context being a list or string
                        ctx = response.get("context", "")
                        if isinstance(ctx, list):
                            ctx = "\n\n".join([str(c) for c in ctx])
                        
                        st.text(str(ctx)[:1000] + "...")
                        
                except Exception as e:
                    st.error(f"Error: {e}")
