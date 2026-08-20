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
"""API router for ADK Assistant custom extension."""

import logging
from fastapi import APIRouter, status

from src.custom.adk_assistant.schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/custom/adk-assistant",
    tags=["ADK Assistant"],
)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check for ADK Assistant extension",
)
async def health_check() -> HealthResponse:
    """Returns the operational status of the ADK Assistant service."""
    return HealthResponse()


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query the ADK Assistant",
)
async def query_assistant(request: QueryRequest) -> QueryResponse:
    """Handles query execution against the ADK Assistant."""
    logger.info(
        "Received query for ADK Assistant: %s",
        request.prompt[:50] if request.prompt else "",
    )
    return QueryResponse(
        response=f"ADK Assistant stub response for: {request.prompt}",
        sessionId=request.session_id,
        metadata={"status": "stub"},
    )


# Export alias to support direct named import
adk_assistant_router = router
