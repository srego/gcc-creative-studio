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
"""Unit and integration tests for ADK Assistant custom domain."""

import asyncio
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.adk.events import Event
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from google.genai.errors import ClientError

from src.custom.adk_assistant.agent import (
    AGENT_INSTRUCTION,
    AGENT_MODEL,
    AGENT_NAME,
    ResilientVertexGemini,
    root_agent,
)
from src.custom.adk_assistant.router import (
    router,
    runner,
)
from src.custom.adk_assistant.schemas import (
    HealthResponse,
    QueryResponse,
)

# Instantiate FastAPI application instance for TestClient
app = FastAPI(title="Creative Studio Custom Domain Test App")
app.include_router(router)


class TestAdkAssistantSuite(unittest.TestCase):
    """Comprehensive test suite for ADK Assistant agent, schemas, and router."""

    def setUp(self):
        """Initializes FastAPI test client before each test execution."""
        self.client = TestClient(app)

    def test_agent_initialization(self):
        """Asserts root_agent metadata, model configuration, and prompt instructions."""
        self.assertEqual(root_agent.name, "creative_studio_assistant")
        self.assertEqual(root_agent.name, AGENT_NAME)
        resolved_model = getattr(root_agent.model, "model", root_agent.model)
        self.assertEqual(resolved_model, "gemini-3.5-flash")
        self.assertEqual(resolved_model, AGENT_MODEL)
        self.assertIn(
            "Google Cloud Creative Studio AI Assistant",
            root_agent.instruction,
        )
        self.assertIn("Imagen and Veo", root_agent.instruction)
        self.assertEqual(root_agent.instruction, AGENT_INSTRUCTION)
        self.assertIsNotNone(root_agent.description)

    def test_resilient_model_fallback_on_404(self):
        """Verifies ResilientVertexGemini automatically falls back and promotes the working model on 404."""
        test_llm = ResilientVertexGemini(
            model="gemini-retired-model",
            fallback_models=("gemini-retired-model", "gemini-3.5-flash"),
        )
        attempted_models: list[str] = []

        async def fake_parent_generate(self_obj, req, stream=False):
            attempted_models.append(req.model)
            if req.model == "gemini-retired-model":
                raise ClientError(
                    404,
                    {"error": {"code": 404, "message": "Model not found", "status": "NOT_FOUND"}},
                )
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text="Fallback model succeeded")],
                )
            )

        async def run_fallback_check():
            req = LlmRequest(
                model="gemini-retired-model",
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text="Test prompt")],
                    )
                ],
            )
            outputs = []
            with patch.object(
                Gemini, "generate_content_async", new=fake_parent_generate
            ):
                async for resp in test_llm.generate_content_async(req):
                    outputs.append(resp)
            return outputs

        results = asyncio.run(run_fallback_check())
        self.assertEqual(
            attempted_models, ["gemini-retired-model", "gemini-3.5-flash"]
        )
        self.assertEqual(test_llm.model, "gemini-3.5-flash")
        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0].content.parts[0].text, "Fallback model succeeded"
        )

    def test_health_check_endpoint(self):
        """Verifies GET /api/custom/adk-assistant/health returns HTTP 200 and valid JSON."""
        response = self.client.get("/api/custom/adk-assistant/health")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["agentName"], "creative_studio_assistant")
        self.assertEqual(data["model"], "gemini-3.5-flash")
        self.assertEqual(data["service"], "adk-assistant")
        self.assertEqual(data["version"], "0.1.0")

        # Validate schema deserialization
        health_obj = HealthResponse.model_validate(data)
        self.assertEqual(health_obj.status, "healthy")
        self.assertEqual(health_obj.agent_name, "creative_studio_assistant")

    def test_chat_endpoint_success(self):
        """Mocks google.adk.runners.Runner and session service to verify POST /chat response."""
        mock_response_text = (
            "Recommended Imagen 3 Prompt:\n"
            "A cinematic wide-angle photograph of an electric concept sports car."
        )
        mock_event = Event(
            author="creative_studio_assistant",
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=mock_response_text)],
            ),
        )

        async def mock_run_async(*args, **kwargs):
            yield mock_event

        with patch.object(
            runner,
            "run_async",
            side_effect=mock_run_async,
        ):
            payload = {
                "message": "Generate a creative prompt for an automotive campaign.",
                "sessionId": "test-session-suite-001",
            }
            response = self.client.post(
                "/api/custom/adk-assistant/chat",
                json=payload,
            )
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertEqual(data["response"], mock_response_text)
            self.assertEqual(data["sessionId"], "test-session-suite-001")
            self.assertEqual(data["agentName"], "creative_studio_assistant")
            self.assertIn("agent_name", data["metadata"])
            self.assertEqual(data["metadata"]["model"], "gemini-3.5-flash")

            # Validate response schema
            query_obj = QueryResponse.model_validate(data)
            self.assertEqual(query_obj.response, mock_response_text)
            self.assertEqual(query_obj.session_id, "test-session-suite-001")

    def test_chat_endpoint_validation_error(self):
        """Tests HTTP 400 validation when sending empty or whitespace-only payloads."""
        response_empty = self.client.post(
            "/api/custom/adk-assistant/chat",
            json={"message": ""},
        )
        self.assertEqual(response_empty.status_code, 400)
        self.assertIn("empty", response_empty.json()["detail"].lower())

        response_whitespace = self.client.post(
            "/api/custom/adk-assistant/chat",
            json={"message": "   \n\t  "},
        )
        self.assertEqual(response_whitespace.status_code, 400)
        self.assertIn("empty", response_whitespace.json()["detail"].lower())

        response_missing = self.client.post(
            "/api/custom/adk-assistant/chat",
            json={},
        )
        self.assertEqual(response_missing.status_code, 400)

    def test_query_alias_endpoint(self):
        """Verifies POST /api/custom/adk-assistant/query alias processes prompts identically."""
        mock_event = Event(
            author="creative_studio_assistant",
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="Veo 2 cinematic camera sequence."
                    )
                ],
            ),
        )

        async def mock_run_async(*args, **kwargs):
            yield mock_event

        with patch.object(
            runner,
            "run_async",
            side_effect=mock_run_async,
        ):
            response = self.client.post(
                "/api/custom/adk-assistant/query",
                json={"prompt": "Generate a Veo drone shot sequence."},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(
                data["response"], "Veo 2 cinematic camera sequence."
            )
            self.assertIsNotNone(data["sessionId"])

    def test_chat_endpoint_internal_error_handling(self):
        """Verifies HTTP 500 error propagation when runner encounters an unexpected failure."""

        async def mock_run_async_fail(*args, **kwargs):
            raise RuntimeError("Underlying Vertex AI connection timeout")
            yield  # pragma: no cover

        with patch.object(
            runner,
            "run_async",
            side_effect=mock_run_async_fail,
        ):
            response = self.client.post(
                "/api/custom/adk-assistant/chat",
                json={"message": "Simulate error."},
            )
            self.assertEqual(response.status_code, 500)
            self.assertIn(
                "Vertex AI connection timeout", response.json()["detail"]
            )

    def test_chat_endpoint_empty_parts_fallback(self):
        """Verifies fallback message when ADK runner yields events with no text parts."""
        mock_event_no_text = Event(
            author="creative_studio_assistant",
            content=types.Content(
                role="model",
                parts=[],
            ),
        )

        async def mock_run_async_empty(*args, **kwargs):
            yield mock_event_no_text

        with patch.object(
            runner,
            "run_async",
            side_effect=mock_run_async_empty,
        ):
            response = self.client.post(
                "/api/custom/adk-assistant/chat",
                json={"message": "Query expecting empty parts."},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["response"],
                "The assistant completed the request with no text output.",
            )


if __name__ == "__main__":
    unittest.main()
