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

import os
from google.adk.agents import Agent

# Bridge V2 Cloud Run environment variables (PROJECT_ID) to Google GenAI / ADK Vertex AI settings
if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get(
    "GEMINI_API_KEY"
):
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    if os.environ.get("PROJECT_ID"):
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ["PROJECT_ID"])
    os.environ.setdefault(
        "GOOGLE_CLOUD_LOCATION", os.environ.get("LOCATION", "global")
    )

AGENT_NAME = "creative_studio_assistant"
AGENT_MODEL = "gemini-3.7-flash"
AGENT_INSTRUCTION = (
    "You are the Google Cloud Creative Studio AI Assistant. Assist users "
    "with prompt engineering for Imagen and Veo, brand guideline adherence, "
    "workflow automation, and multimodal creative generation. Provide concise, "
    "high-impact creative recommendations and structured prompt templates."
)

root_agent = Agent(
    name=AGENT_NAME,
    model=AGENT_MODEL,
    instruction=AGENT_INSTRUCTION,
    description="Google Cloud Creative Studio AI Assistant for multimodal creative workflows.",
)
