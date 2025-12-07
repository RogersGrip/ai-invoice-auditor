import sys
from unittest.mock import MagicMock, patch

# Mock dependencies that might be missing or fail to import
mock_tess = MagicMock()
mock_tess.__spec__ = MagicMock()
sys.modules["pytesseract"] = mock_tess
sys.modules["src.tools.ocr_engine"] = MagicMock()

# Mock langfuse to avoid auth errors
sys.modules["langfuse"] = MagicMock()
sys.modules["langfuse.decorators"] = MagicMock()

import json
from src.langgraph_agents.rag.reflector import ReflectionAgent

def test_reflection_fallback():
    # Setup
    agent = ReflectionAgent()
    
    # Mock Inputs
    inputs = {
        "query": "What is the capital of France?",
        "answer": "Paris",
        "context": "Paris is the capital of France.",
        "context_id": "test_123"
    }

    # Mock Ragas Tool to Fail
    # The real tool returns a JSON string, so we mock that.
    agent.evaluator_tool.run = MagicMock(return_value=json.dumps({
        "error": "RAGAS_FAILED", 
        "details": "Simulated Timeout", 
        "faithfulness": 0.0
    }))

    # Mock MLflow Evaluator to Succeed
    # We need to patch the class that is imported INSIDE the method
    with patch("src.langgraph_agents.rag.reflector.MLflowEvaluator") as MockEvaluator:
        instance = MockEvaluator.return_value
        instance.evaluate.return_value = {
            "faithfulness": 0.9,
            "answer_relevance": 0.8,
            "context_precision": 0.0,
            "context_recall": 0.0,
            "context_entity_recall": 0.0
        }

        # Execute
        response = agent.process(inputs)
        
        # Verify
        print(f"Agent Response Payload: {response.payload}")
        
        evaluation = json.loads(response.payload["evaluation"])
        
        # Assertions
        assert evaluation["faithfulness"] == 0.9
        assert "answer_relevance" in evaluation
        assert "error" not in evaluation
        
        # Verify Fallback was called
        MockEvaluator.assert_called_once()
        instance.evaluate.assert_called_once()

if __name__ == "__main__":
    test_reflection_fallback()
    print("Test Passed!")
