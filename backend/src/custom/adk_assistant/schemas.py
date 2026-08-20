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
"""Pydantic schemas for ADK Assistant custom domain."""

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ChatMessage(BaseModel):
    """Represents an individual message exchanged in an assistant session."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class QueryRequest(BaseModel):
    """Payload for submitting a prompt query to the ADK Assistant."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    prompt: str
    session_id: str | None = None
    context: dict[str, Any] | None = None


class QueryResponse(BaseModel):
    """Response returned by the ADK Assistant for a submitted query."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    response: str
    session_id: str | None = None
    metadata: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Health check payload for the ADK Assistant service."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    status: str = "ok"
    service: str = "adk-assistant"
    version: str = "0.1.0"
