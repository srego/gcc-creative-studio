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
"""ADK Agent definition for Google Cloud Creative Studio AI Assistant."""

from collections.abc import AsyncGenerator
import logging
import os

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import Client
from google.genai.errors import ClientError

logger = logging.getLogger(__name__)

# Bridge Cloud Run environment variables (PROJECT_ID) to Google GenAI / ADK Vertex AI settings.
# Always pin Vertex AI Gemini text/agent calls to `global`, where Gemini 3.x/4.x publisher models live.
if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get(
    "GEMINI_API_KEY"
):
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    if os.environ.get("PROJECT_ID"):
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ["PROJECT_ID"])
    os.environ["GOOGLE_CLOUD_LOCATION"] = os.environ.get(
        "CUSTOM_GENAI_LOCATION", "global"
    )

DEFAULT_FLASH_MODEL = "gemini-3.5-flash"
FALLBACK_FLASH_MODELS = (
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-4-argon",
    "gemini-2.5-pro",
)

_shared_global_client: Client | None = None


class ResilientVertexGemini(Gemini):
    """Vertex AI Gemini ADK wrapper with global endpoint pinning and automatic model fallback."""

    fallback_models: tuple[str, ...] = FALLBACK_FLASH_MODELS

    @property
    def api_client(self) -> Client:
        global _shared_global_client
        if self.client is not None:
            return self.client
        if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
            return super().api_client
        if _shared_global_client is None:
            project_id = os.environ.get("PROJECT_ID") or os.environ.get(
                "GOOGLE_CLOUD_PROJECT"
            )
            location = os.environ.get("CUSTOM_GENAI_LOCATION", "global")
            _shared_global_client = Client(
                vertexai=True,
                project=project_id,
                location=location,
            )
        return _shared_global_client

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        primary = llm_request.model or self.model
        candidates: list[str] = [primary]
        for candidate in self.fallback_models:
            if candidate not in candidates:
                candidates.append(candidate)

        last_exc: ClientError | None = None
        for idx, candidate_model in enumerate(candidates):
            attempt_request = llm_request.model_copy(deep=True)
            attempt_request.model = candidate_model
            try:
                async for llm_response in super().generate_content_async(
                    attempt_request, stream=stream
                ):
                    if self.model != candidate_model:
                        logger.info(
                            "ADK Assistant promoted active Vertex AI model '%s' -> '%s'",
                            self.model,
                            candidate_model,
                        )
                        self.model = candidate_model
                    yield llm_response
                return
            except ClientError as exc:
                last_exc = exc
                if exc.code in (400, 403, 404) and idx < len(candidates) - 1:
                    logger.warning(
                        "Vertex AI model '%s' unavailable (HTTP %s); falling back to '%s'",
                        candidate_model,
                        exc.code,
                        candidates[idx + 1],
                    )
                    continue
                raise

        if last_exc is not None:  # pragma: no cover
            raise last_exc


AGENT_NAME = "creative_studio_assistant"
AGENT_MODEL = os.environ.get("CUSTOM_FLASH_MODEL", "").strip() or DEFAULT_FLASH_MODEL
AGENT_INSTRUCTION = (
    "You are the Google Cloud Creative Studio AI Assistant. Assist users "
    "with prompt engineering for Imagen and Veo, brand guideline adherence, "
    "workflow automation, and multimodal creative generation. Provide concise, "
    "high-impact creative recommendations and structured prompt templates."
)

llm_model = ResilientVertexGemini(model=AGENT_MODEL)

root_agent = Agent(
    name=AGENT_NAME,
    model=llm_model,
    instruction=AGENT_INSTRUCTION,
    description="Google Cloud Creative Studio AI Assistant for multimodal creative workflows.",
)


def get_active_agent_model() -> str:
    """Returns the currently active (or fallback-resolved) Gemini model name."""
    return llm_model.model or AGENT_MODEL
