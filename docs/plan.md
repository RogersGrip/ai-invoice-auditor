# Capstone Project: AI Invoice Auditor - End-to-End Implementation Plan

This is a comprehensive blueprint for building the **AI Invoice Auditor**. I have designed this to meet your strict constraints: **clean code, production standards (SOLID, clean architecture), hybrid agentic frameworks (LangGraph + Google ADK), and strict interoperability protocols (MCP + A2A).**

## 1\. High-Level Design (HLD)

The system follows a **Micro-Agent Architecture**. We will treat the LangGraph agents as the "Orchestrators" (Client side of A2A) and the Google ADK agents as "Specialized Workers" (Server side of A2A). This perfectly demonstrates the interoperability requirement.

### **Core Components**

1.  **Orchestrator Core (LangGraph):**
      * **Responsibilities:** State management, Decision making, RAG loops, Human-in-the-loop (HITL).
      * **Agents:** Invoice Monitor, Extractor, RAG Triad (Indexing, Retrieval, Generation).
2.  **Specialized Service Mesh (Google ADK):**
      * **Responsibilities:** Deterministic tasks, high-reliability standardized processing.
      * **Agents:** Translation Agent, Validation Agent, Reporting Agent.
      * **Protocol:** Exposed via **Agent-to-Agent (A2A)** Protocol.
3.  **Tool Layer (Model Context Protocol - MCP):**
      * **Responsibilities:** Standardized access to external systems.
      * **Servers:**
          * `filesystem-mcp`: For reading invoices.
          * `erp-mock-mcp`: For querying the mock Enterprise database.
          * `vector-mcp`: For Qdrant interactions.
4.  **Interface Layer:**
      * **Backend:** FastAPI (Serving the LangGraph workflow and ADK endpoints).
      * **Frontend:** Streamlit (Admin Dashboard, HITL Interface).
      * **Gateway:** LiteLLM (Unified interface for AWS Bedrock Cohere/Titan).

-----

## 2\. Low-Level Design (LLD) & Tech Stack Decisions

### **Directory Structure (Monorepo)**

```text
ai-invoice-auditor/
├── agents/
│   ├── adk_workers/        # Google ADK Agents (Translation, Validation)
│   │   ├── src/
│   │   ├── agent_cards/    # A2A JSON Cards
│   │   └── main.py         # Runs the ADK A2A Server
│   └── langgraph_core/     # LangGraph Orchestrator
│       ├── graph.py
│       └── nodes/
├── tools/                  # MCP Servers
│   ├── erp_server.py       # FastMCP server for Mock ERP
│   └── file_server.py      # FastMCP server for File Ops
├── shared/
│   ├── protocols/          # A2A Client wrappers
│   └── utils/              # Logger, Env Config, LiteLLM setup
├── backend/                # FastAPI Application
├── frontend/               # Streamlit Dashboard
├── scripts/                # Startup bash/bat scripts
├── pyproject.toml          # uv config
└── .env.example
```

### **Critical Technical Decisions**

1.  **Google ADK with Bedrock:** Google ADK defaults to Gemini. We will implement a `Model` Adapter using `LiteLLM` to force it to use your AWS Bedrock (`cohere.command-r-plus-v1:0`) credentials.
2.  **A2A Implementation:** We will run the ADK agents as a local HTTP service acting as an "A2A Remote Node". The LangGraph nodes will use an `A2AClient` to dispatch tasks to them.
3.  **Vector DB:** Qdrant (Embedded mode or Local server) to avoid Docker complexity as requested.
4.  **Observability:** LangFuse Python SDK will be initialized at the entry point of both LangGraph and ADK processes.

-----

## 3\. Sprint Plan

We will execute this in **5 Organized Sprints**.

### **Sprint 1: Foundation & The Tool Layer (MCP)**

  * **Goal:** Setup `uv` environment, standard logging, and the MCP Servers (ERP & File System).
  * **Deliverable:** Working `erp_server` and `file_server` that can be queried via MCP Inspector.
  * **Tech:** Python 3.12, `mcp`, `fastmcp`.

### **Sprint 2: The Specialized Workers (Google ADK + A2A)**

  * **Goal:** Build Translation and Validation agents using Google ADK. Wrap them in the A2A Protocol.
  * **Deliverable:** A running background service where I can send a JSON task "Translate this" and get a response, utilizing `cohere` via Bedrock.
  * **Tech:** `google-adk`, `a2a-sdk`, `litellm`.

### **Sprint 3: The Orchestrator (LangGraph & RAG)**

  * **Goal:** Build the RAG system (Qdrant) and the main Workflow State Machine.
  * **Deliverable:** A LangGraph workflow that detects a file, extracts text (using simple OCR/Text library), calls the ADK agents (from Sprint 2), and indexes data.
  * **Tech:** `langgraph`, `langchain-aws`, `qdrant-client`.

### **Sprint 4: Integration & Interface**

  * **Goal:** Connect Backend (FastAPI) and Frontend (Streamlit).
  * **Deliverable:** A UI where I can upload an invoice (or drop it in a folder), see the live agent steps, and view the final report.
  * **Tech:** FastAPI, Streamlit.

### **Sprint 5: Hardening & Observability**

  * **Goal:** Add Guardrails, Human-in-the-loop (HITL) breakpoints in LangGraph, and full LangFuse tracing.
  * **Deliverable:** Production-ready code, final demo scripts.

-----

## 4\. Immediate Next Step: Environment & Foundation

I will now start **Sprint 1**. This involves setting up the strict project structure and the `pyproject.toml` with `uv`.

**Does this Design and Sprint Plan meet your expectations?**
*If yes, I will proceed to generate the Setup Script and Sprint 1 Code.*