# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for ADK Assistant backend custom domain."""

import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.adk.events import Event
from google.genai import types

from src.custom.adk_assistant.agent import (
    AGENT_INSTRUCTION,
    AGENT_MODEL,
    AGENT_NAME,
    root_agent,
)
from src.custom.adk_assistant.router import router
from src.custom.adk_assistant.schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
)

test_app = FastAPI()
test_app.include_router(router)


class TestAdkAssistant(unittest.TestCase):
    """Test suite for ADK Assistant agent and router endpoints."""

    def setUp(self):
        self.client = TestClient(test_app)

    def test_root_agent_configuration(self):
        """Validates root_agent configuration and instructions."""
        self.assertEqual(root_agent.name, "creative_studio_assistant")
        self.assertEqual(root_agent.model, "gemini-3.7-flash")
        self.assertIn(
            "Google Cloud Creative Studio AI Assistant",
            root_agent.instruction,
        )
        self.assertIn("Imagen and Veo", root_agent.instruction)

    def test_health_endpoint(self):
        """Validates GET /health returns expected status and agent metadata."""
        response = self.client.get("/api/custom/adk-assistant/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["agentName"], "creative_studio_assistant")
        self.assertEqual(data["model"], "gemini-3.7-flash")
        self.assertEqual(data["service"], "adk-assistant")

    def test_chat_endpoint_empty_message(self):
        """Validates POST /chat rejects empty messages with 400 Bad Request."""
        response = self.client.post(
            "/api/custom/adk-assistant/chat",
            json={"message": ""},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("empty", response.json()["detail"].lower())

    def test_chat_endpoint_successful_execution(self):
        """Validates POST /chat handles agent execution asynchronously."""
        mock_event = Event(
            author="creative_studio_assistant",
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="Here is a recommended Imagen prompt template."
                    )
                ],
            ),
        )

        async def mock_run_async(*args, **kwargs):
            yield mock_event

        with patch(
            "src.custom.adk_assistant.router.runner.run_async",
            side_effect=mock_run_async,
        ):
            response = self.client.post(
                "/api/custom/adk-assistant/chat",
                json={
                    "message": "Create a prompt for a luxury watch advertisement.",
                    "sessionId": "test-session-123",
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(
                data["response"],
                "Here is a recommended Imagen prompt template.",
            )
            self.assertEqual(data["sessionId"], "test-session-123")
            self.assertEqual(data["agentName"], "creative_studio_assistant")

    def test_query_alias_endpoint(self):
        """Validates POST /query alias endpoint works seamlessly."""
        mock_event = Event(
            author="creative_studio_assistant",
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(text="Veo video generation prompt.")
                ],
            ),
        )

        async def mock_run_async(*args, **kwargs):
            yield mock_event

        with patch(
            "src.custom.adk_assistant.router.runner.run_async",
            side_effect=mock_run_async,
        ):
            response = self.client.post(
                "/api/custom/adk-assistant/query",
                json={
                    "prompt": "Create a Veo prompt for a cinematic shot.",
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["response"], "Veo video generation prompt.")


if __name__ == "__main__":
    unittest.main()
