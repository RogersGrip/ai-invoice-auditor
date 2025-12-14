import os
import asyncio
from typing import Any
from uuid import uuid4

import httpx 

from a2a.client import A2AClient, A2ACardResolver, ClientFactory
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest
)

from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    EXTENDED_AGENT_CARD_PATH
)


async def main() -> None:
    base_url = os.getenv("A2A_SERVER_URL", "http://localhost:10001")

    async with httpx.AsyncClient() as httpx_client:
        card_resolver = A2ACardResolver(
            base_url=base_url,
            httpx_client=httpx_client
        )

        final_agent_card_to_use: AgentCard

        try:
            _public_card = await card_resolver.get_agent_card()
            print("Agent Card: ", _public_card.model_dump_json(indent=2, exclude_none=True))

            final_agent_card_to_use = _public_card
    
        except Exception as e:
            raise RuntimeError("Failed to fetch the public agent card.") from e

        # Client

        client = A2AClient(
            httpx_client=httpx_client,
            agent_card=final_agent_card_to_use
        )

        print("\nA2A Client Started\n")

        # First query - addition
        query = "What is sum of 3 and 9?"

        message_payload = {
            'message': {
                'role': 'user',
                'parts': [
                    {'kind': 'text', 'text': query}
                ],
                'message_id': uuid4().hex
            }
        }

        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**message_payload)
        )

        print(f"Sending first message: {query}")
        response = await client.send_message(request)

        # Check if response has error
        if hasattr(response, 'error') and response.error:
            print(f"Error in response: {response.error}")
            return
        
        print("\nFirst Response:")
        print(response.model_dump_json(indent=2))

        # Extract task_id and context_id safely
        if hasattr(response.root, 'result'):
            task_id = response.root.result.id
            context_id = response.root.result.context_id
            
            print(f"\nTask ID: {task_id}")
            print(f"Context ID: {context_id}")

            # Second query - greeting
            query_2 = "Hey, I am Luffy!"

            second_send_message_payload_multiturn = {
                'message': {
                    'role': 'user',
                    'parts': [
                        {'kind': 'text', 'text': query_2}
                    ],
                    'message_id': uuid4().hex,
                    'task_id': task_id,
                    'context_id': context_id
                }
            }

            request2 = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(**second_send_message_payload_multiturn)  # ✅ Fixed
            )

            print(f"\nSending second message: {query_2}")
            response2 = await client.send_message(request2)

            print("\nSecond Response:")
            print(response2.model_dump_json(indent=2))
        else:
            print("No result in response")

if __name__ == '__main__':
    asyncio.run(main())