import json
from pathlib import Path
from typing import Dict
from src.core.protocol import AgentCard
from src.core.logger import logger

class AgentDiscovery:
    _cards: Dict[str, AgentCard] = {}

    @classmethod
    def load_cards(cls, config_dir: str = "src/config/cards"):
        path = Path(config_dir)
        if not path.exists():
            logger.warning(f"Agent card directory {path} not found.")
            return

        for card_file in path.glob("*.json"):
            try:
                with open(card_file, "r") as f:
                    data = json.load(f)
                    card = AgentCard(**data)
                    # Use the agent name or a specific ID as key
                    cls._cards[card.name] = card
                    logger.info(f"Loaded Agent Card: {card.name}")
            except Exception as e:
                logger.error(f"Failed to load agent card {card_file}: {e}")

    @classmethod
    def get_card(cls, agent_name: str) -> AgentCard:
        return cls._cards.get(agent_name)

    @classmethod
    def get_all_cards(cls) -> Dict[str, AgentCard]:
        return cls._cards

# Initialize discovery on import
AgentDiscovery.load_cards()