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
"""FastAPI router for Google Cloud Creative Studio ADK Assistant."""

import logging
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException, status
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.custom.adk_assistant.agent import AGENT_MODEL, AGENT_NAME, root_agent
from src.custom.adk_assistant.schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/custom/adk-assistant",
    tags=["Custom: ADK Assistant"],
)

# Persistent in-memory session service and runner for the ADK agent
session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name=AGENT_NAME,
    session_service=session_service,
)

DEFAULT_USER_ID = "creative_studio_user"


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check for ADK Assistant",
)
async def health_check() -> HealthResponse:
    """Returns the health and model metadata for the ADK Assistant service."""
    return HealthResponse(
        status="healthy",
        agent_name=AGENT_NAME,
        model=AGENT_MODEL,
        service="adk-assistant",
        version="0.1.0",
    )


@router.post(
    "/chat",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with the ADK Assistant",
)
async def chat_with_assistant(request: QueryRequest) -> QueryResponse:
    """Executes a multi-turn or single-turn prompt query using the ADK Runner."""
    prompt_text = (request.message or request.prompt or "").strip()
    if not prompt_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request 'message' or 'prompt' must not be empty.",
        )

    session_id = request.session_id or str(uuid.uuid4())

    try:
        # Ensure session exists in the session service
        existing_session = await session_service.get_session(
            app_name=AGENT_NAME,
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
        )
        if not existing_session:
            await session_service.create_session(
                app_name=AGENT_NAME,
                user_id=DEFAULT_USER_ID,
                session_id=session_id,
            )

        # Build user Content part
        new_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_text)],
        )

        collected_texts: list[str] = []
        metadata: dict[str, Any] = {
            "agent_name": AGENT_NAME,
            "model": AGENT_MODEL,
        }

        # Asynchronously run the agent
        async for event in runner.run_async(
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
            new_message=new_content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        collected_texts.append(part.text)

        response_content = (
            "".join(collected_texts)
            if collected_texts
            else "The assistant completed the request with no text output."
        )

        return QueryResponse(
            response=response_content,
            session_id=session_id,
            agent_name=AGENT_NAME,
            metadata=metadata,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error executing ADK Assistant query: %s", exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute ADK Assistant request: {str(exc)}",
        ) from exc


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Legacy query endpoint alias for ADK Assistant",
    include_in_schema=True,
)
async def query_assistant(request: QueryRequest) -> QueryResponse:
    """Alias for /chat to maintain full backward compatibility."""
    return await chat_with_assistant(request)


# Export router aliases for naming flexibility
adk_assistant_router = router
