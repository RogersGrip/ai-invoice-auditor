import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from src.a2a_agents.extractor.executor import ExtractorAgentExecutor
import os
import sys

def main():
    # 1. Skills
    skill = AgentSkill(
        id="extract",
        name="Extract Text",
        description="Extracts raw text from documents.",
        tags=['extract', 'invoice'],
    )

    # 2. Card
    card = AgentCard(
        name="Extractor Agent",
        description="Agent that extracts text from files using DataHarvesterTool.",
        url="http://localhost:8001/",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=['text'], # Accepts paths as text or data
        default_output_modes=['data'],
        skills=[skill]
    )

    # 3. Handler
    handler = DefaultRequestHandler(
        agent_executor=ExtractorAgentExecutor(),
        task_store=InMemoryTaskStore()
    )

    # 4. App
    app = A2AStarletteApplication(
        http_handler=handler,
        agent_card=card
    )

    print("Starting Extractor Agent on http://0.0.0.0:8001")
    uvicorn.run(app.build(), host="0.0.0.0", port=8001)

if __name__ == '__main__':
    main()
