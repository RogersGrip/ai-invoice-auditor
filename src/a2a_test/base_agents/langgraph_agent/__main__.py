# A2A Server

import logging
import os
import sys

import click
import httpx
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore
)

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill
)

from dotenv import load_dotenv
from agent_executor import HelloAgentExecutor
from agent import HelloAgent

load_dotenv()

class MissingAPIKeyError(Exception):
    """Custom exception for missing API key."""
    pass

def main():
    host = "localhost"
    port = 10001

    try:
        capabilities = AgentCapabilities(streaming=True, push_notifications=True)

        skill = AgentSkill(
            id = "hello_agent",
            name = "Hello Agent",
            description = "Greets the user and add two numbers based on query",
            tags=['add', 'hello'],
            examples=['Hey, I am Zoro', "Add 3 and 4"]
        )

        agent_card = AgentCard(
            name="Hello Agent",
            description="Helps with greet user and add two numbers",
            url=f'http://{host}:{port}/',
            version="1.0.0",
            default_input_modes=HelloAgent.SUPPORTED_TYPES,
            default_output_modes=HelloAgent.SUPPORTED_TYPES,
            capabilities=capabilities,
            skills=[skill]
        )

        httpx_client = httpx.AsyncClient()

        push_config_store = InMemoryPushNotificationConfigStore()
        push_sender = BasePushNotificationSender(
            httpx_client=httpx_client,
            config_store=push_config_store
        )

        # Create an instance of the executor, not the class
        agent_executor_instance = HelloAgentExecutor()

        request_handler = DefaultRequestHandler(
            agent_executor=agent_executor_instance,  # ✅ Pass instance, not class
            push_config_store=push_config_store,
            push_sender=push_sender,
            task_store=InMemoryTaskStore()
        )

        server = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler
        )

        print(f"Starting Hello Agent server on http://{host}:{port}")
        uvicorn.run(server.build(), host=host, port=port)

    except MissingAPIKeyError as e:
        print("Error: ", e)
        sys.exit(1)

    except Exception as e:
        print("Error in server startup: ", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()