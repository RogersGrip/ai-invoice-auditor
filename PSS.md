# Capstone Project: AI Invoice Auditor

## 1. Project Overview

**Name:** AI Invoice Auditor

**Description:**  
An end-to-end agentic AI system for automated multilingual invoice processing and validation. Agents extract, translate, validate, and audit invoices received via email (or read from a file system). The solution integrates Retrieval‑Augmented Generation (RAG), human‑in‑the‑loop feedback, and observability for accuracy and traceability.

**Business Context:**  
A logistics client receives invoices from global vendors in multiple languages and formats (PDF, Word, scanned images). Manual processing is time-consuming, error-prone, and requires language expertise.

## 2. Project Requirements

Design and implement an agentic AI solution that:

1. Monitor inbox for incoming invoices (design/approach only; demo may read files from the file system).
2. Extract invoice data (text, tables, key fields) from attachments in any language and format.
3. Translate extracted data to English.
4. Validate invoice data against enterprise records (ERP or mocked API returning line‑item ERP data).
5. Generate detailed validation reports highlighting discrepancies, missing fields, and translation confidence.
6. Provide question‑answering over invoices using vector‑based RAG for support agents.
7. Implement RAG with agentic roles:
    - Indexing Agent — parse and index documents into a vector DB.
    - Retrieval Agent — generate query embeddings and perform similarity search.
    - Augmentation Agent — re-rank chunks by relevance.
    - Generation Agent — use LLM to produce contextual responses.
    - Reflection Agent — evaluate responses for relevance and groundedness.
8. RAG tools to include:
    - Vector‑Indexer Tool
    - Semantic‑Retriever Tool
    - Chunk‑Ranker Tool
    - Response‑Synthesizer Tool
    - RAG‑Evaluator Tool
9. Implement an agentic workflow using LangGraph (RAG, prompt engineering, human‑in‑the‑loop).
10. Core agents for the Invoice Auditor:
     - Invoice‑Monitor Agent (can read from file system for demos)
     - Extractor Agent
     - Translation Agent
     - Invoice Data Validation Agent
     - Business Validation Agent
     - Reporting Agent
11. Tools used by agents:
     - Invoice‑Watcher Tool
     - Data Harvester Tool
     - Lang‑Bridge Tool (translation/normalization)
     - DataCompletenessChecker Tool
     - Business Validation Tool
     - Insight Reporter Tool
12. Implement some agents with LangGraph and others with Google ADK as appropriate.
13. Ensure interoperability via the Agent‑to‑Agent Protocol.
14. Embed Responsible AI (RAI) guardrails across agents and tools.
15. Integrate observability (e.g., LangFuse) for tracing, monitoring, and debugging.

## 3. Solution Architecture

- Modular, agentic architecture with a central LLM gateway orchestrating specialized agents.
- RAG pipeline separated into indexing, retrieval, augmentation, generation, and reflection.
- Human‑in‑the‑loop feedback and audit trails for validation and continuous improvement.
- Design principles:
  - Reusable prompt templates.
  - Model Context Protocol (MCP) for dynamic tool discovery and invocation.
  - End‑to‑end observability and traceability.

## 4. Technology Stack

- Backend: Python
- Agent frameworks: LangGraph and Google ADK
- Vector DB: FAISS / Qdrant / Weaviate
- OCR: Tesseract or equivalent
- Models: Open‑source LLMs and embedding models
- Frontend: Streamlit or React
- Observability: LangFuse

## 5. Non‑Functional Requirements

- Performance: Efficient batch processing
- Scalability: Horizontally scalable agent modules
- Security: Secure document handling and access controls
- Reliability: Robust error handling and fallbacks
- Usability: Intuitive UI for support agents
- Maintainability: Modular codebase and documentation

## 6. Input Data

- Sample masked invoices (e.g., Masked Invoice.pdf)
- Mock ERP records for validation

## 7. Deliverables

- Solution design diagram
- Modular Python source code
- Demo application (UI + backend agents)
- Sample multilingual invoices and mock ERP data
- Validation reports (PDF / HTML / CSV)
- Documentation (setup, usage, prompts, agent designs)
- Observability traces and example RAG evaluation reports


---