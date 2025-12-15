import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from src.a2a_agents.translator.executor import TranslatorAgentExecutor

def main():
    skill = AgentSkill(
        id="translate",
        name="Translate Text",
        description="Translates text and extracts data.",
        tags=['translate', 'extract'],
    )

    card = AgentCard(
        name="translation_agent",
        description="Agent that translates and structures invoice data.",
        url="http://localhost:8002/",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=['text'],
        default_output_modes=['data'],
        skills=[skill]
    )

    handler = DefaultRequestHandler(
        agent_executor=TranslatorAgentExecutor(),
        task_store=InMemoryTaskStore()
    )

    app = A2AStarletteApplication(
        http_handler=handler,
        agent_card=card
    )

    print("Starting Translation Agent on http://0.0.0.0:8002")
    uvicorn.run(app.build(), host="0.0.0.0", port=8002)

if __name__ == '__main__':
    main()
