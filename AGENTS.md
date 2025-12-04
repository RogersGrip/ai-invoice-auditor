# System Instructions

- You are a professional senior software engineer. You have access to all the resources
- You can access google search, official docs, and github repos, example
- Keep the code clean, compact and minimal
- Use production ready standard practices
- Have proper variable names and proper spacing
- Don't vibe code the slop, Do proper research on github, official site and references before writing any code
- I don't want to break the existing code
- Everytime a change is requested, spit out either the fully fixed function or fully fixed files alone
- I want properly handled logs and follow the instructions properly
- I dont want reasons like you can replace your practice here i always want proper data fed instead of mock data being fed for testing
- Use standards of the protocols like agent cards for a2a, mcp server tools, clean architecture
- Dont add unncessary comments keep it as clean as possible, add only when necessary concise ones
- I am using uv for project dependencies so keep that in mind
- I dont want to vibe code anything, all i want you to do is completely guide me end to end and provide me organized sprints to finish this. I am mainting a github repo too.
- I am using cohere chatbedrock converse fo rthis project.
- Present the entire plan once with structure and ask me for once i am done. When i m done ill submit by work. Your task is review, tell the discripancies and bad errors that could affect future sprints
- Once you are done doing that suggest fixes and tell me to implement and also provide necessary repos, docs etc
- Everything needs to be production ready and state of the art. Should be good enough for my resume.
- Don't use docker and other imaging stuff. This is for a personal good project
- Present the low level and high level design for this. Keep everything lightweight.
- I am majorly on linux, but some might use windows to work on this project too. 
- Make desicions wisely.
- The mcp design and a2a should be really standard with tools and stuff.
- Don't hallucinate always use the search tools and docs for reference dont tell anything on your own. I you dont know something admit it.
- Follow the latest pydantic stuff and I dont want any pylance warnings.
- Keep everything neat and structured.
- Implement industry wide practices and SOLID principles so i dont end up with ai sloppy code.
- It should be easy to debug.
- Follow proper structure and naming conventions.
- Choose the techstack from problem statement and always check compatiblity while searching and providing in docs.
- Also entire architecture is must be perfect.
- The flow should be neat and production ready.
- For backend maybe use fastapi or use whats in problem statement. and for frontedn for these requirements whats the best.
- Use the best prompts, keep them in separate folder and make them dyanamic maybe use formats like {{}}
- Also write a proper file that integrates and runs everything.
- Configure properly on env, spit out .env.example and use agent personas in yaml. Eg for models
TRANSLATION_MODEL=cohere.command-r-plus-v1:0
VALIDATION_MODEL=cohere.command-r-plus-v1:0
REPORTING_MODEL=cohere.command-r-plus-v1:0
EMBEDDING_MODEL=amazon.titan-embed-text-v1
- Maintain proper scripts
- For vectors use qdrant and standard folder no docker for now.

Sscripts

- `export PYTHONPYCACHEPREFIX="$(dirname "$(pwd)")/pycache"`

- `uv venv`
- `source .venv/bin/activate`
- `mkdir -p pycache`
- `export PYTHONPYCACHEPREFIX="$PWD/pycache"`
- `find . | grep -E "(__pycache__|\.pyc$)" | xargs rm -rf`

- The error handling must be verbose, neat and easy to trace and resolve
- The workflow progress must be neatly shown in backend and frontend also logs
- Try not to hardcode and make prompts dynamic. {{}}
- Decide which agents need google adk and which need langgraph and perfectly integrate them with a2a protocol and mcp standards.
- If something can be done without llm , try doing that so that llm provides proper structured outputs.
- Make it easy to swap out llms in the future (just a consideration maybe use ollama dont add them now, just make it so that they can be added)

# toml for uv
[project]
name = "ai-invoice-auditor"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = []


# Complete Problem statement

Capstone Project: AI Invoice Auditor 

1. Project Overview 

Project Name: AI Invoice Auditor 
Project Description: 
An end-to-end Agentic AI-powered system for automated multilingual invoice processing 
and validation. The solution uses AI Agents to extract, translate, validate, and audit invoices 
received via email in various formats and languages. It integrates Retrieval-Augmented 
Generation (RAG) and human-in-the-loop feedback for enhanced accuracy and reliability. 

## Business Context: 

A Logistic client receives invoices from global vendors to raise invoice discrepancies in 
various languages (English, Spanish, German, etc.) and formats (PDF, Word, scanned 
images) via email as an attachment. Manual processing is time consuming, error-prone, and 
a skillful process as it requires language expertise. 

2. Project Requirements: 
Design and implement an end-to-end Agentic AI-powered solution that: 

1. Monitors an email inbox for incoming invoices. (for this step only design/approach 
is expected and not the actual implementation) Use a folder for simualtion and monitor it.

2. Extracts invoice data (text, tables, key fields) from attachments which can be in any 
language and format (so the solution should be format and language agnostic) 

3. Translates extracted data to English. 

4. Validates invoice data against records in an enterprise system (e.g., ERP, database, 
or mock data) – The call to the enterprise system can be mocked for capstone 
implementation. The mock API call should return the data from ERP system to be 
validated against the data received at line item level in customer invoice. 

5. Generates a detailed validation report highlighting discrepancies (if there is data 
mismatch between the data in invoice vs data from ERP system), missing fields from 
invoice (invoice validation should be performed against the dynamic rules 
configured), and translation confidence.

6. Provide question answering capabilities (implemented using vector-based RAG) on 
the invoices to the support agent (Human Agent). 

7. RAG should be implemented using agentic AI. RAG solution should comprise of the 
following agent roles: 
➢ Indexing Agent – Parses and indexes invoice documents in a vector DB 
➢ Retrieval Agent – Accepts user query, generates query embedding, and performs 
similarity search 
➢ Augmentation Agent – Performs reranking of chunks based on similarity score.
➢ Generation Agent – Uses LLM to generate contextual responses 
➢ Reflection Agent – Evaluates response based on RAG Triad parameters including 
Answer Relevance, Context Relevance, and Groundedness. Include all RAGAS metrics.

8. As part of the RAG Implementation the following tools need to be leverages 
➢ Vector-Indexer Tool – Converts documents into embeddings and stores 
them in a vector database for efficient retrieval. 
➢ Semantic-Retriever Tool – Performs semantic search using vector similarity 
to find contextually relevant data. 
➢ Chunk-Ranker Tool – Re-ranks retrieved chunks based on relevance scores 
to improve context quality. 
➢ Response-Synthesizer Tool – Generates natural language answers using 
retrieved context and user queries. 
➢ RAG-Evaluator Tool – Assesses generated responses using RAG metrics like 
Context ,relevance and groundedness. 

9. Implements an agentic workflow using open-source LangGraph framework, with 
RAG, prompt engineering, and human-in-the-loop feedback. 

10. The overall Invoice Auditor solution should be implemented using agentic AI, and 
should include the following agent roles: 
➢ Invoice-Monitor Agent – Continuously monitors the mailbox for emails with invoice 
attachments (this agent can read the documents from file system rather than from 
live mailbox) 
➢ Extractor Agent – Extracts data from various document formats 
➢ Translation Agent – Translates extracted invoice data from different languages into 
English 
➢ Invoice Data Validation Agent – Validates missing information based on defined 
rules 
➢ Business Validation Agent – Validates extracted invoice data with enterprise system 
data to identify discrepancies 
➢ Reporting Agent – Generates detailed reports highlighting discrepancies, missing 
fields, translation confidence, and final recommendation 

11. The above-mentioned agents should have the appropriate tools to accomplish the 
assigned task. 
➢ Invoice-Watcher Tool – Monitors a designated mailbox or file system to detect 
and retrieve emails containing invoice attachments. (this agent can read the 
documents from file system rather than from live mailbox) 
➢ Data Harvester Tool – Extracts data from a wide range of document formats, 
enabling downstream processing. 
➢ Lang-Bridge Tool – Converts extracted invoice content from various languages 
into English for standardized interpretation. 
➢ DataCompletenessChecker Tool – Validates invoice data for completeness and 
accuracy based on predefined business rules. 
➢ Business Validation Tool – Cross-verifies extracted invoice data against 
enterprise systems to identify mismatches or inconsistencies. 
➢ Insight Reporter Tool – Generates comprehensive reports highlighting data 
gaps, validation results, translation confidence, and final recommendations. 

12. Out of the agents defined above, some should be developed using LangGraph, while 
others should be implemented using Google ADK. 

13. The solution should enable seamless communication between agents implemented 
by different frameworks by adhering to the Agent-to-Agent Protocol, ensuring 
standardized and secure interactions across components. 

14. Implements RAI (Responsible AI) guardrails across agents and tools wherever 
applicable, ensuring ethical, secure, and compliant use of AI components throughout 
the solution 

15. The solution should integrate observability tools such as LangFuse to enable real
time tracing, monitoring, and debugging of the agentic AI workflows, ensuring 
transparency and operational reliability throughout the system. 

3. Solution Architecture 

The Agentic AI Invoice Auditor is built on a modular agentic architecture using open source 
LangGraph Agentic framework. It orchestrates specialized agents for tasks like monitoring, 
extraction, translation, validation, and reporting through a centralized LLM Gateway (Lite 
LLM). A RAG-based question answering system enables contextual queries with agents for 
indexing, retrieval, augmentation, generation, and reflection. The system includes human
in-the-loop feedback, and audit trails for reliability and transparency. 
Solution should leverage prompt templates while defining prompts. 

The solution should utilize the Model Context Protocol to dynamically discover, access, and 
invoke the appropriate tools required for task execution. 

The solution should integrate RAI (Responsible AI) guardrails within agents and tools to 
enforce responsible behavior, enhance trustworthiness, and align with ethical AI practices 
wherever necessary. 

The solution should implement agents using two distinct agentic frameworks LangGraph 
and Google ADK while ensuring agent discovery, invocation, and communication are aligned 
with the guidelines to the Agent-to-Agent Protocol. 
The solution should embed observability features using tools like LangFuse to enable deep 
visibility into agentic workflows facilitating trace analysis, performance tracking, and 
intelligent debugging for improved system resilience and operational clarity. 

4. Technology Stack 
Backend: 
• Python and required Libraries  
• LangGraph Agentic framework 
• Google ADK framework 
• Vector DB (FAISS, Qdrant, Weaviate) 
• OCR tools (e.g., Tesseract) 
Models (Open source): 
• Text Generation models 
• Embedding model 
• Multi-modal model 
Communication Protocol: 
• Model Context Protocol (MCP): Facilitates the interaction between an agent and the 
specific tools it needs to use 
• Agent-to-Agent Protocol (A2A): Defines the standards and mechanisms for seamless 
discovery, invocation, and communication between agents, enabling coordinated 
task execution and interoperability within an agentic ecosystem. 
LLM Gateway: 
• Lite LLM 
Frontend: 
• Streamlit / React for the UI 
Deployment: 
• NuvePro Lab 
Observability Tool: 
• LangFuse 

5. Non-Functional Requirements 
• Performance: Efficient processing of large invoice batches 
• Scalability: Modular agent design allows horizontal scaling 
• Security: Secure email access and document handling 
• Reliability: Robust error handling and fallback mechanisms 
• Usability: Intuitive UI for support agents 
• Maintainability: Modular codebase with documentation 

6. Input Data set 
Masked Invoice.pdf

7. Final Deliverables 
• Solution Design Diagram 
• Source Code (Python, modularized) 
• Functional Application (demo UI + backend agents) 
• Sample Data (multilingual invoices, mock enterprise records) 
• Validation Reports (PDF/HTML/CSV) 
• Documentation (setup, usage, agent design, prompt templates) 