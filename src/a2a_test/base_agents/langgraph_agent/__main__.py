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

