import streamlit as st
import os
import time
import json
import sys
import requests
from pathlib import Path
from typing import Tuple, Dict, Any

# -------------------------------------------------------------
# Environment Setup
# -------------------------------------------------------------
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.core.config import settings

API_URL = "http://localhost:8000"

st.set_page_config(page_title="AI Invoice Auditor", layout="wide")


# -------------------------------------------------------------
# Utility Functions
# -------------------------------------------------------------
def backend_health() -> bool:
    try:
        requests.get(f"{API_URL}/health", timeout=1)
        return True
    except Exception:
        return False


def trigger_processing(file_path: str) -> Tuple[bool, Any]:
    if not backend_health():
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

    try:
        response = requests.post(
            f"{API_URL}/v1/message:send",
            json=payload,
            timeout=120
        )
        if response.status_code == 200:
            return True, response.json()
        return False, response.text
    except Exception as exc:
        return False, str(exc)


def read_json(path: Path) -> Dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}


# -------------------------------------------------------------
# Sidebar Controls
# -------------------------------------------------------------
with st.sidebar:
    st.title("System Controls")

    if st.button("Refresh Application"):
        st.rerun()

    if st.button("Clear Status File"):
        status_file = settings.DATA_DIR / "status.json"
        if status_file.exists():
            status_file.unlink()
        st.success("Status cleared")
        st.rerun()

    st.divider()
    status_placeholder = st.empty()
    status_path = settings.DATA_DIR / "status.json"

    if status_path.exists():
        status = read_json(status_path)
        status_placeholder.info(
            f"File: {status.get('current_file', '')}\n\n"
            f"Step: {status.get('step', '')}\n\n"
            f"Status: {status.get('status', '')}"
        )
    else:
        status_placeholder.success("System idle")


# -------------------------------------------------------------
# Tabs
# -------------------------------------------------------------
tab_dashboard, tab_approval, tab_chat = st.tabs(
    ["Dashboard", "Audit & Approval", "Chat Assistant"]
)


# =============================================================
# 1. DASHBOARD TAB
# =============================================================
with tab_dashboard:
    st.header("Invoice Processing Dashboard")

    col_left, col_right = st.columns([1, 2])

    # ----------------- Upload Section -----------------
    with col_left:
        st.subheader("Upload Invoices")

        uploaded_files = st.file_uploader(
            "Upload Files",
            type=["pdf", "png", "jpg", "json"],
            accept_multiple_files=True
        )

        if uploaded_files and st.button(f"Process {len(uploaded_files)} Files"):
            progress_bar = st.progress(0)

            for index, file in enumerate(uploaded_files):
                dest_path = settings.INVOICE_WATCH_DIR / file.name
                with open(dest_path, "wb") as f:
                    f.write(file.getbuffer())

                success, response = trigger_processing(str(dest_path))

                if success:
                    st.info(f"Uploaded: {file.name}")
                else:
                    st.error(f"Failed: {file.name} | {response}")

                progress_bar.progress((index + 1) / len(uploaded_files))

            time.sleep(1)
            st.rerun()

    # ----------------- Monitoring Section -----------------
    with col_right:
        st.subheader("Monitoring Information")

        st.markdown(
            f"""
            Watch Directory: `{settings.INVOICE_WATCH_DIR}`  
            Processed Directory: `{settings.PROCESSED_DIR}`  
            Reports Directory: `{settings.OUTPUT_DIR}`
            """
        )

        queued_files = list(settings.INVOICE_WATCH_DIR.glob("*.*"))
        if queued_files:
            st.write("Files in Queue:")
            for file in queued_files:
                st.code(file.name)
        else:
            st.write("No files in queue.")


# =============================================================
# 2. AUDIT & APPROVAL TAB
# =============================================================
with tab_approval:
    st.header("Audit Review and Approval Workflow")

    all_reports = sorted(
        list(settings.OUTPUT_DIR.glob("*_report.json")),
        key=os.path.getmtime,
        reverse=True,
    )

    unique_reports = {}

    # Deduplicate meta files
    for report in all_reports:
        data = read_json(report)
        fname = data.get("meta", {}).get("file_name")

        if not fname or fname.endswith(".meta.json"):
            continue

        if fname not in unique_reports:
            unique_reports[fname] = (report, data)

    pending = []
    archived = []

    for fname, (report_path, data) in unique_reports.items():
        status = data.get("meta", {}).get("status")
        is_archived = (settings.PROCESSED_DIR / fname).exists()

        if status == "COMPLETED" or is_archived:
            archived.append((fname, report_path, data))
        else:
            pending.append((fname, report_path, data))

    # -------------------- Pending Section --------------------
    st.subheader(f"Pending Review ({len(pending)})")

    if pending:
        selector = {
            f"{fname} | {data.get('meta', {}).get('status', 'UNKNOWN')}":
            (fname, report_path)
            for fname, report_path, data in pending
        }

        selected_label = st.selectbox("Select Invoice", list(selector.keys()))

        if selected_label:
            fname, r_path = selector[selected_label]
            report = read_json(r_path)

            safe = report.get("safety", {})
            validation = report.get("validation", {})

            c1, c2 = st.columns([2, 1])

            # Core Audit Results
            with c1:
                st.write("Safety Check")
                st.table({
                    "Metric": ["Is Safe", "Details"],
                    "Value": [safe.get("is_safe"), safe.get("details", "")]
                })

                st.write("Business Logic Validation")
                st.table({
                    "Metric": ["Is Valid"],
                    "Value": [validation.get("is_valid")]
                })

                if validation.get("discrepancies"):
                    with st.expander("Validation Discrepancies"):
                        st.write(validation["discrepancies"])

                if validation.get("missing_fields"):
                    with st.expander("Missing Fields"):
                        st.write(validation["missing_fields"])

            # Actions
            with c2:
                st.subheader("Actions")

                reviewer_comment = st.text_area("Reviewer Comment")

                if st.button("Approve and Resume Workflow", use_container_width=True):
                    response = requests.post(
                        f"{API_URL}/v1/tasks/{fname}/resume",
                        json={"comment": reviewer_comment or "Approved"}
                    )
                    if response.status_code == 200:
                        st.success("Workflow resumed")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(response.text)

                # Report PDF
                pdf_path = str(r_path).replace(".json", ".pdf")
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="Download PDF Report",
                            data=f,
                            file_name=os.path.basename(pdf_path)
                        )

    st.divider()

    # -------------------- Archive Section --------------------
    st.subheader(f"Processed Archive ({len(archived)})")

    if archived:
        picker = {fname: (fname, r_path) for fname, r_path, _ in archived}
        selected_archived = st.selectbox("Select Archived Report", list(picker.keys()))

        if selected_archived:
            _, r_path = picker[selected_archived]
            data = read_json(r_path)

            with st.expander("Report Contents"):
                st.json(data)


# =============================================================
# 3. CHAT ASSISTANT TAB
# =============================================================
with tab_chat:
    st.header("Invoice Knowledge Assistant")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display existing messages on every rerun
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle user input (persistent input at bottom)
    if prompt := st.chat_input("Enter your message"):
        # Store and display user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Call backend for response
        try:
            payload = {
                "message": {
                    "messageId": str(time.time()),
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            }
            api_response = requests.post(
                f"{API_URL}/v1/message:send",
                json=payload,
                timeout=120
            )

            if api_response.status_code == 200:
                parts = api_response.json().get("message", {}).get("parts", [])
                response_text = parts[0].get("text", "") if parts else ""
            else:
                response_text = f"Error: {api_response.status_code}"

        except Exception as exc:
            response_text = f"Connection error: {exc}"

        # Display assistant reply
        with st.chat_message("assistant"):
            st.markdown(response_text)

        # Store assistant reply in history
        st.session_state.messages.append(
            {"role": "assistant", "content": response_text}
        )
