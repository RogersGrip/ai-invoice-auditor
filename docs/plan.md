This is a comprehensive, state-of-the-art architectural plan for the **AI Invoice Auditor**. I have designed this to be modular, production-grade, and strictly aligned with your constraints (Python 3.12, `uv`, Bedrock/Cohere, No Docker, SOLID principles).

As your Sprint Master, I will layout the architecture first. Once you approve this high-level direction, we will move to **Sprint 0**.

-----

## 1\. High-Level Design (HLD)

We will use a **Hub-and-Spoke Agentic Architecture**.

  * **Orchestrator (LangGraph):** Manages the state and flow between agents.
  * **Specialized Agents:** Focused on single responsibilities (Extraction, Translation, Validation).
  * **Interoperability (A2A & MCP):** The Core System (LangGraph) communicates with the External System (e.g., a standalone Reporting Agent built with Google ADK patterns) via a standardized HTTP/JSON schema (A2A). Tools are exposed via MCP.

### Architecture Diagram

```mermaid
graph TD
    subgraph "Input Layer"
        Email[Email/Folder Monitor] -->|Triggers| Orch[Orchestrator (LangGraph)]
    end

    subgraph "Orchestration Layer (LangGraph)"
        Orch --> MonitorAg[Invoice Monitor Agent]
        Orch --> ExtractAg[Extractor Agent]
        Orch --> TransAg[Translation Agent]
        Orch --> ValidAg[Data Validation Agent]
        Orch --> RAGAg[RAG Specialist Agent]
    end

    subgraph "External/Specialized Agents (Simulating Google ADK/Interop)"
        Orch <-->|A2A Protocol (HTTP)| BizAg[Business Validation Agent]
    end

    subgraph "Tooling Layer (MCP)"
        ExtractAg <-->|MCP| OCR[OCR Tool (Tesseract)]
        ExtractAg <-->|MCP| PDF[PDF Parser]
        BizAg <-->|MCP| ERP[Mock ERP API]
        RAGAg <-->|MCP| VecDB[Qdrant (Local)]
    end

    subgraph "Observability & Gateway"
        LiteLLM[LiteLLM Gateway]
        LangFuse[LangFuse Observability]
        Orch -.-> LiteLLM
        Orch -.-> LangFuse
    end

    subgraph "User Interface"
        Streamlit[Streamlit UI] <--> Orch
    end
```

-----

## 2\. Low-Level Design (LLD)

### Tech Stack & Decisions

  * **Language:** Python 3.12 (Strict typing).
  * **Dependency Manager:** `uv` (Fast, efficient).
  * **LLM Gateway:** `LiteLLM` pointing to AWS Bedrock (`cohere.command-r-plus-v1:0`).
  * **Orchestration:** `LangGraph` (Stateful workflows).
  * **Interop:** `FastAPI` to expose agents that require A2A protocol.
  * **Vector DB:** `Qdrant` (Local mode, no Docker required).
  * **Observability:** `LangFuse` (Self-hosted or Cloud, we will configure SDK).
  * **Config:** `Pydantic Settings` + `.env`.

### Directory Structure

We will adhere to a clean "src-layout".

```text
ai-invoice-auditor/
├── .venv/                   # Managed by uv
├── config/                  # Configuration & YAML personas
├── data/                    # Mock data (ERP), raw invoices, processed
├── logs/                    # Structured logs
├── src/
│   ├── agents/              # Agent logic (Classes)
│   │   ├── monitor.py
│   │   ├── extractor.py
│   │   ├── translator.py
│   │   └── validator.py
│   ├── core/                # Core infrastructure
│   │   ├── llm.py           # LiteLLM wrapper
│   │   ├── state.py         # LangGraph state definitions
│   │   └── logger.py        # Loguru setup
│   ├── database/            # Qdrant & Vector logic
│   ├── models/              # Pydantic data models (Schemas)
│   ├── tools/               # MCP Tool implementations
│   │   ├── erp_mock.py
│   │   └── ocr_engine.py
│   ├── workflows/           # LangGraph workflows
│   └── main.py              # Entry point
├── tests/
├── .env.example
├── pyproject.toml
└── README.md
```

-----

## 3\. The Master Sprint Plan

We will execute this in **6 Logical Sprints**.

### **Sprint 0: Foundations & Configuration**

  * Initialize project with `uv`.
  * Set up Environment Variables & Logging.
  * Implement `Mock ERP` data loader.
  * Define `Agent Personas` (YAML).
  * **Goal:** A running environment where we can load config and access the Mock ERP.

### **Sprint 1: Ingestion & Extraction (The Eyes)**

  * Implement `Invoice Monitor Agent` (Watchdog).
  * Implement `Extractor Agent` with OCR (Tesseract/PDF tools).
  * Create Pydantic models for `Invoice` structure.
  * **Goal:** Drop a PDF in a folder -\> Get raw JSON text out.

### **Sprint 2: Translation & Standardization (The Brain - Part 1)**

  * Implement `Translation Agent` using Cohere.
  * Implement `Lang-Bridge Tool`.
  * Standardize all outputs to English and specific JSON Schema.
  * **Goal:** Raw Multilingual JSON -\> Clean English JSON.

### **Sprint 3: Validation & A2A Protocol (The Brain - Part 2)**

  * Implement `Data Validation Agent` (Rules engine).
  * **Complex Step:** Implement `Business Validation Agent` as a separate micro-service (FastAPI) to demonstrate **A2A Protocol** (simulating Google ADK separation).
  * Integrate Mock ERP checks.
  * **Goal:** Clean JSON -\> Validated Report with Discrepancies.

### **Sprint 4: RAG & Knowledge Base (The Memory)**

  * Setup `Qdrant` (Local).
  * Implement `Indexing Agent` & `Retrieval Agent`.
  * Implement RAG logic (Embeddings -\> Search -\> Rerank -\> Generate).
  * **Goal:** Chat with the invoice ("What is the total for SKU-001?").

### **Sprint 5: Orchestration & UI (The Body)**

  * Stitch agents together using `LangGraph`.
  * Build `Streamlit` Dashboard.
  * Implement `Reflection Agent` for final report quality.
  * **Goal:** End-to-End flow visible in UI.

### **Sprint 6: Observability, Guardrails & Polish**

  * Integrate `LangFuse` for tracing.
  * Finalize `RAI Guardrails` (Input/Output filtering).
  * Write startup scripts (`run.sh`, `run.bat`).
  * **Goal:** Production-ready demo.

-----

## 4\. Immediate Action: Sprint 0 Authorization

I am ready to start **Sprint 0**.

**Sprint 0 Tasks:**

1.  Initialize `uv` project.
2.  Create directory structure.
3.  Create `.env` and `config.yaml`.
4.  Create `mock_data` JSON files (from your prompt).
5.  Create `logger` configuration.

**Do you approve the Architecture and the Sprint Plan? If yes, type "Start Sprint 0".**