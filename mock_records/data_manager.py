import yaml
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from util.logging_config import setup_logger

logger = setup_logger(__name__)

class DataManager:
    """
    Manages loading and accessing configuration from rules.yaml, persona_invoice_agent.yaml, 
    and mock ERP data from JSON files.
    """
    
    def __init__(self, rules_path: Path | str = None, erp_data_path: Path | str = None):
        """
        Initializes the DataManager with paths for configuration and ERP data.
        """
        
        # Set paths, defaulting to the current directory if not provided
        self.RULES_PATH = Path(rules_path) if rules_path else Path('.')
        self.ERP_DATA_PATH = Path(erp_data_path) if erp_data_path else Path('.')
            
        self.rules = self._load_yaml('rules.yaml')
        self.personas = self._load_persona_yaml('persona_invoice_agent.yaml') 
        
        self.po_records: List[Dict] = self._load_json('PO_Records.json')
        self.vendors: List[Dict] = self._load_json('vendors.json')
        self.sku_master: List[Dict] = self._load_json('sku_master.json')

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """Loads a critical YAML file (like rules.yaml) from the rules path."""
        file_path = self.RULES_PATH / filename
        try:
            with open(file_path, 'r') as f:
                return yaml.safe_load(f)
            
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing YAML file {filename}: {e}")
            
    def _load_persona_yaml(self, filename: str) -> Dict[str, Any]:
        """Loads the optional persona YAML file."""
        file_path = self.RULES_PATH / filename
        try:
            with open(file_path, 'r') as f:
                return yaml.safe_load(f)
            
        except FileNotFoundError:
            logger.info(f"WARNING: Persona file {file_path} not found. Returning empty dict.")
            return {}
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing YAML file {filename}: {e}")

    def _load_json(self, filename: str) -> List[Dict]:
        """Loads a JSON file (ERP data) from the ERP data path."""
        file_path = self.ERP_DATA_PATH / filename
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        
        except FileNotFoundError:
            logger.info(f"Warning: Mock ERP data file not found: {file_path}. Returning empty list.")
            return []
        except json.JSONDecodeError as e:
            raise ValueError(f"Error decoding JSON from {filename}: {e}")

    def get_rules(self) -> Dict[str, Any]:
        """Returns the loaded validation rules."""
        return self.rules

    def get_persona(self, agent_name: str) -> Dict[str, str]:
        """
        Retrieves the persona details (role and responsibility) for a specific agent.
        """

        # Returns a safe default if the agent name is not found in the YAML
        return self.personas.get(agent_name, {
            'persona_role': 'Professional Assistant',
            'core_responsibility': 'Fulfill the user request accurately and concisely.'
        })

    # Helper methods to query mock ERP data
    def get_po_details(self, po_number: str) -> Optional[Dict]:
        """Retrieves details for a given Purchase Order Number."""
        return next((po for po in self.po_records if po['po_number'] == po_number), None)

    def get_vendor_details(self, vendor_id: str) -> Optional[Dict]:
        """Retrieves details for a given Vendor ID."""
        return next((vendor for vendor in self.vendors if vendor['vendor_id'] == vendor_id), None)

    def get_sku_details(self, item_code: str) -> Optional[Dict]:
        """Retrieves details for a given SKU Item code."""
        return next((sku for sku in self.sku_master if sku['item_code'] == item_code), None)