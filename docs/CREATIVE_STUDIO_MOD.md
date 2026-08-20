# Creative Studio Mod Guide: Extending Creative Studio While Keeping Core Updated

# PRE-FLIGHT CHECK: CREATIVE STUDIO EXTENSION COMPATIBILITY ASSESSOR & TRIAGE MATRIX

Before applying custom extensions, execute the following triage invariant checks to verify integration baselines and resolve upstream drift:

| # | Invariant Check | CLI Verification Command | Expected Baseline | If Upstream Drift Detected (Remediation) |
|---|---|---|---|---|
| **1** | **Frontend Routing Pattern** | `test -f frontend/src/app/app-routing.module.ts && echo "NgModule" \|\| echo "Standalone"` | File exists (`app-routing.module.ts`) using Angular `Routes` array. | **If Standalone (`app.routes.ts`):** Register the route `{ path: 'custom/adk-assistant', loadComponent: () => import(...) }` in `frontend/src/app/app.routes.ts` instead of `app-routing.module.ts`. |
| **2** | **Navigation Container & Anchor Position** | `grep -n "routerLink" frontend/src/app/header/header.component.html` | Top navigation toolbar with floating circular icon items. Custom user navigation icons MUST be anchored inside the main navigation cluster immediately preceding the `/gallery` routerLink (`<div routerLink="/gallery"...`). | **If Nav Moved to Sidebar (`sidebar.component.html`):** Place the `<mat-icon>auto_awesome</mat-icon>` button inside the sidebar menu list item rather than the header, maintaining placement immediately preceding the gallery item. |
| **3** | **Backend Router Hook** | `grep -n "app.include_router" backend/main.py` | `main.py` initializes FastAPI and mounts routers via `app.include_router(...)`. | **If Factory Pattern (`create_app()`):** Mount `app.include_router(adk_assistant_router)` inside the application factory function in `backend/main.py`. |
| **4** | **Python Package Manager** | `which uv && uv --version` | `uv` package manager installed (Python 3.12+ runtime). | **If Using Poetry/Pipenv:** Run `poetry add google-adk` or `pip install google-adk` instead of `uv add`. |

---

## 1. Executive Summary & Architecture
This guide provides a paved, production-grade path to extend an existing Google Cloud Creative Studio instance with custom capabilities while preserving seamless upstream update and merge compatibility.

### Target Environment Details
- **Base Upstream Repository:** `https://github.com/GoogleCloudPlatform/gcc-creative-studio.git`
- **Active Working Branch:** `feature/adk-assistant`
- **Target GCP Project ID:** `creative-studio-delta2`
- **Target GCP Project Number:** `456871514227`

### The Rule of Isolation
To eliminate merge conflicts during upstream updates, all custom features MUST reside strictly within dedicated `/custom/` namespaces:
- **Backend Custom Code:** `backend/src/custom/adk_assistant/`
- **Frontend Custom Code:** `frontend/src/app/custom/adk_assistant/`
- **Unit & Integration Tests:** `backend/tests/custom/adk_assistant/`
- **Core Integration Constraint:** Never modify core business logic outside of `/custom/`. Core repository modifications are strictly restricted to exactly 3 minimal integration hooks:
  1. `backend/main.py` (Router registration)
  2. `frontend/src/app/app-routing.module.ts` (Route entry)
  3. `frontend/src/app/header/header.component.html` (Navigation icon)

```
gcc-creative-studio/
├── .github/workflows/
│   └── upstream-sync.yml                        # Automated CI/CD Upstream Sync & Conflict Alerting
├── backend/
│   ├── main.py                                  # Core Hook 1: app.include_router(adk_assistant_router)
│   ├── src/
│   │   └── custom/
│   │       └── adk_assistant/
│   │           ├── __init__.py                  # Module exports
│   │           ├── agent.py                     # ADK Agent definition (gemini-3.7-flash)
│   │           ├── schemas.py                   # Pydantic schema contracts
│   │           └── router.py                    # FastAPI APIRouter (/api/custom/adk-assistant)
│   └── tests/
│       └── custom/
│           └── adk_assistant/
│               ├── __init__.py
│               └── test_adk_assistant.py        # Pytest test suite (99% coverage)
└── frontend/
    └── src/
        └── app/
            ├── app-routing.module.ts            # Core Hook 2: /custom/adk-assistant route
            ├── header/
            │   └── header.component.html        # Core Hook 3: auto_awesome nav button
            └── custom/
                └── adk_assistant/
                    ├── adk-assistant.service.ts # HTTP client service
                    ├── adk-assistant.component.ts # Reactive standalone component
                    ├── adk-assistant.component.html # Dark glassmorphic template
                    └── adk-assistant.component.scss # Component styling & animations
```

---

## 2. Prerequisites & Initial Setup
- Creative Studio is deployed on GCP project `creative-studio-delta2`.
- Local tools verified: `gcloud`, `terraform` (v1.14.1+), `uv` (v0.6+), `node` (v18+), `npm` (v9+).
- Python environment initialized with `uv sync --all-extras`.
- Frontend dependencies installed with `npm ci` (or `npm install`).

---

## 3. The 5-Stage Agent Implementation Recipes

### Stage 2.1: Domain Scaffolding & Core Integration Hooks

#### Stage 2.1 Recipe Prompt
```text
# STAGE 2.1: DOMAIN SCAFFOLDING & CORE INTEGRATION HOOKS
Create the isolated domain structure under backend/src/custom/adk_assistant/, frontend/src/app/custom/adk_assistant/, and backend/tests/custom/adk_assistant/. Register the 3 minimal core integration hooks in backend/main.py, frontend/src/app/app-routing.module.ts, and frontend/src/app/header/header.component.html.
```

#### Core Integration Hooks Implementation

**1. Hook 1: Backend Router Mount (`backend/main.py`)**
```python
# backend/main.py (imports)
from src.custom.adk_assistant.router import (
    adk_assistant_router,
)

# backend/main.py (router inclusions)
app.include_router(workbench_router)
app.include_router(adk_assistant_router)
```

**2. Hook 2: Frontend Route Registration (`frontend/src/app/app-routing.module.ts`)**
```typescript
// frontend/src/app/app-routing.module.ts (imports)
import {AdkAssistantComponent} from './custom/adk_assistant/adk-assistant.component';

// frontend/src/app/app-routing.module.ts (routes array)
const routes: Routes = [
  // ... existing core routes ...
  {
    path: 'custom/adk-assistant',
    component: AdkAssistantComponent,
    canActivate: [AuthGuardService],
  },
];
```

**3. Hook 3: Navigation Header Link (`frontend/src/app/header/header.component.html`)**

> [!IMPORTANT]
> Custom user navigation icons MUST be anchored inside the main navigation cluster immediately preceding the `/gallery` routerLink (`<div routerLink="/gallery"...`). They must not be placed near the admin/profile section at the bottom of the navigation bar.

```html
<!-- frontend/src/app/header/header.component.html (placed immediately preceding the /gallery routerLink block) -->
<div
  routerLink="/custom/adk-assistant"
  matTooltip="ADK Assistant"
  matTooltipPosition="right"
  class="md:mb-[10px] cursor-pointer w-14 h-14 bg-blend-soft-light bg-white/40 rounded-[48px] shadow-[0px_4px_4px_0px_rgba(0,0,0,0.25)] outline outline-1 outline-offset-[-1px] outline-stone-300/80 backdrop-blur-2xl inline-flex justify-start items-start gap-2.5 overflow-hidden"
>
  <div
    *ngIf="router.isActive('/custom/adk-assistant', true)"
    class="flex-1 h-14 bg-gradient-to-r from-blue-500 via-violet-500 to-red-400 rounded-full blur-[3px] backdrop-blur-md"
  ></div>
  <div class="w-6 h-6 left-[16px] top-[16px] absolute overflow-hidden">
    <button
      matFab
      aria-label="ADK Assistant"
      class="cursor-pointer w-6 h-6 left-0 top-0 absolute text-center justify-center text-neutral-200 text-2xl"
    >
      <mat-icon>auto_awesome</mat-icon>
    </button>
  </div>
</div>
```

---

### Stage 2.2: Backend ADK Integration & FastAPI Router

#### Stage 2.2 Recipe Prompt
```text
# STAGE 2.2: BACKEND ADK AGENT & FASTAPI ROUTER IMPLEMENTATION + ASSESSOR TRIAGE MATRIX
Implement the backend ADK domain files (agent.py, schemas.py, router.py) and update docs/CREATIVE_STUDIO_MOD.md with the actionable Pre-Flight Triage Matrix.
```

#### Complete Implementation Code Blocks

**1. ADK Agent Definition (`backend/src/custom/adk_assistant/agent.py`)**
```python
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

from google.adk.agents import Agent

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
```

**2. Pydantic Schemas (`backend/src/custom/adk_assistant/schemas.py`)**
```python
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
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class ChatMessage(BaseModel):
    """Represents an individual message exchanged in an assistant session."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    role: Literal["user", "assistant", "system", "model"]
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

    message: str = Field(
        default="",
        description="User message prompt text",
    )
    prompt: str | None = Field(
        default=None,
        description="Alias for message prompt text",
    )
    session_id: str | None = Field(
        default=None,
        description="Unique session identifier for multi-turn conversation",
    )
    history: list[ChatMessage] | None = Field(
        default=None,
        description="Optional conversational history context",
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Additional context parameters",
    )

    @model_validator(mode="after")
    def populate_message(self) -> "QueryRequest":
        """Ensures message or prompt is populated."""
        if not self.message and self.prompt:
            self.message = self.prompt
        elif not self.prompt and self.message:
            self.prompt = self.message
        return self


class QueryResponse(BaseModel):
    """Response returned by the ADK Assistant for a submitted query."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    response: str
    session_id: str | None = None
    agent_name: str = "creative_studio_assistant"
    metadata: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Health check payload for the ADK Assistant service."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    status: str = "healthy"
    agent_name: str = "creative_studio_assistant"
    model: str = "gemini-3.7-flash"
    service: str = "adk-assistant"
    version: str = "0.1.0"
```

**3. FastAPI Router (`backend/src/custom/adk_assistant/router.py`)**
```python
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

        new_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_text)],
        )

        collected_texts: list[str] = []
        metadata: dict[str, Any] = {
            "agent_name": AGENT_NAME,
            "model": AGENT_MODEL,
        }

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


adk_assistant_router = router
```

#### OpenAPI Contract Specification

| Path | HTTP Method | Summary | Request Body | Success Response (200) | Error Responses |
|---|---|---|---|---|---|
| `/api/custom/adk-assistant/health` | `GET` | Service Health Check | None | `HealthResponse` (`status="healthy"`, `agent_name`, `model="gemini-3.7-flash"`, `version="0.1.0"`) | `500 Internal Server Error` |
| `/api/custom/adk-assistant/chat` | `POST` | Execute Multi-turn Chat | `QueryRequest` (`message`, `sessionId`, `history`, `context`) | `QueryResponse` (`response`, `sessionId`, `agentName`, `metadata`) | `400 Bad Request` (empty prompt)<br>`500 Internal Server Error` |
| `/api/custom/adk-assistant/query` | `POST` | Legacy Query Endpoint Alias | `QueryRequest` (`prompt`, `sessionId`) | `QueryResponse` (`response`, `sessionId`, `agentName`) | `400 Bad Request`<br>`500 Internal Server Error` |

---

### Stage 2.3: Frontend Reactive UI & Client Service

#### Stage 2.3 Recipe Prompt
```text
# STAGE 2.3: FRONTEND REACTIVE UI & SERVICE IMPLEMENTATION
Implement the Angular client service (adk-assistant.service.ts) and interactive chat UI component (adk-assistant.component.ts, .html, .scss) adhering to the Creative Studio UI design system (dark glassmorphism, Gemini Spectrum accents, live status pill, message thread, suggestion chips, clipboard copy, and thinking animation).
```

#### Complete Implementation Code Blocks

**1. Angular Client Service (`frontend/src/app/custom/adk_assistant/adk-assistant.service.ts`)**
```typescript
// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import {HttpClient} from '@angular/common/http';
import {Injectable} from '@angular/core';
import {Observable} from 'rxjs';
import {environment} from '../../../environments/environment';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'model';
  content: string;
  timestamp?: string | Date;
}

export interface QueryRequest {
  message?: string;
  prompt?: string;
  sessionId?: string;
  history?: ChatMessage[];
  context?: Record<string, unknown>;
}

export interface QueryResponse {
  response: string;
  sessionId?: string;
  agentName?: string;
  metadata?: Record<string, unknown>;
}

export interface HealthResponse {
  status: string;
  agentName?: string;
  model?: string;
  service?: string;
  version?: string;
}

@Injectable({
  providedIn: 'root',
})
export class AdkAssistantService {
  private readonly apiUrl = `${environment.backendURL}/custom/adk-assistant`;

  constructor(private readonly http: HttpClient) {}

  checkHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.apiUrl}/health`);
  }

  sendMessage(
    message: string,
    sessionId?: string,
    history?: ChatMessage[],
  ): Observable<QueryResponse> {
    const payload: QueryRequest = {
      message,
      prompt: message,
      sessionId,
      history,
    };
    return this.http.post<QueryResponse>(`${this.apiUrl}/chat`, payload);
  }

  query(prompt: string, sessionId?: string): Observable<QueryResponse> {
    return this.sendMessage(prompt, sessionId);
  }
}
```

**2. Standalone Angular Component (`frontend/src/app/custom/adk_assistant/adk-assistant.component.ts`)**
```typescript
// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import {Clipboard, ClipboardModule} from '@angular/cdk/clipboard';
import {CommonModule} from '@angular/common';
import {
  AfterViewChecked,
  Component,
  ElementRef,
  OnInit,
  ViewChild,
} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {MatButtonModule} from '@angular/material/button';
import {MatChipsModule} from '@angular/material/chips';
import {MatIconModule} from '@angular/material/icon';
import {MatProgressSpinnerModule} from '@angular/material/progress-spinner';
import {MatTooltipModule} from '@angular/material/tooltip';
import {
  AdkAssistantService,
  ChatMessage,
} from './adk-assistant.service';

export interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export interface QuickSuggestion {
  label: string;
  icon: string;
  prompt: string;
}

@Component({
  selector: 'app-adk-assistant',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ClipboardModule,
    MatButtonModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  templateUrl: './adk-assistant.component.html',
  styleUrls: ['./adk-assistant.component.scss'],
})
export class AdkAssistantComponent implements OnInit, AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;
  @ViewChild('promptInput') private promptInput?: ElementRef<HTMLTextAreaElement>;

  status: 'Online' | 'Connecting' | 'Offline' = 'Connecting';
  modelName = 'gemini-3.7-flash';
  serviceName = 'adk-assistant';
  sessionId = this.generateSessionId();
  prompt = '';
  isLoading = false;
  copiedMessageId: string | null = null;
  private shouldScrollToBottom = false;

  readonly quickSuggestions: QuickSuggestion[] = [
    {
      label: 'Optimize Imagen Prompt',
      icon: 'photo_camera',
      prompt:
        'Optimize this prompt for Imagen 3 photorealism: A modern studio portrait of a product designer in a glass architecture atelier during golden hour, 85mm lens, shallow depth of field, dramatic cinematic lighting.',
    },
    {
      label: 'Generate Veo Storyboard',
      icon: 'movie_filter',
      prompt:
        'Create a 4-shot cinematic video storyboard prompt sequence for Veo depicting an autonomous electric sports car navigating a futuristic neon city in rainy night with smooth drone tracking shots.',
    },
    {
      label: 'Brand Consistency Check',
      icon: 'verified',
      prompt:
        'Evaluate this campaign copy against Google Cloud brand guidelines: clean typography, inspiring tone, technological clarity, and human-centric benefits.',
    },
    {
      label: 'Multimodal Concept Ideas',
      icon: 'auto_awesome_motion',
      prompt:
        'Suggest 3 multimodal creative concept variations combining 4K hero stills with 5-second cinematic motion loops for a luxury eco-resort brand launch.',
    },
  ];

  messages: DisplayMessage[] = [
    {
      id: 'msg-init',
      role: 'assistant',
      content:
        'Welcome to Google Cloud Creative Studio AI Assistant! I can help you craft high-impact prompts for Imagen 3 and Veo, enforce brand consistency guidelines, structure storyboard narratives, and automate multimodal creative workflows. How can I assist your campaign today?',
      timestamp: new Date(),
    },
  ];

  constructor(
    private readonly adkService: AdkAssistantService,
    private readonly clipboard: Clipboard,
  ) {}

  ngOnInit(): void {
    this.checkHealth();
  }

  ngAfterViewChecked(): void {
    if (this.shouldScrollToBottom) {
      this.scrollToBottom();
      this.shouldScrollToBottom = false;
    }
  }

  checkHealth(): void {
    this.status = 'Connecting';
    this.adkService.checkHealth().subscribe({
      next: res => {
        this.status = res.status === 'healthy' || res.status === 'ok' ? 'Online' : 'Online';
        if (res.model) {
          this.modelName = res.model;
        }
        if (res.service) {
          this.serviceName = res.service;
        }
      },
      error: () => {
        this.status = 'Offline';
      },
    });
  }

  sendMessage(customPrompt?: string): void {
    const textToSend = (customPrompt ?? this.prompt).trim();
    if (!textToSend || this.isLoading) {
      return;
    }

    const userMessage: DisplayMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: textToSend,
      timestamp: new Date(),
    };

    this.messages.push(userMessage);
    this.prompt = '';
    this.isLoading = true;
    this.shouldScrollToBottom = true;

    const historyPayload: ChatMessage[] = this.messages.map(m => ({
      role: m.role,
      content: m.content,
      timestamp: m.timestamp.toISOString(),
    }));

    this.adkService
      .sendMessage(textToSend, this.sessionId, historyPayload)
      .subscribe({
        next: res => {
          if (res.sessionId) {
            this.sessionId = res.sessionId;
          }
          const assistantMessage: DisplayMessage = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: res.response,
            timestamp: new Date(),
          };
          this.messages.push(assistantMessage);
          this.isLoading = false;
          this.shouldScrollToBottom = true;
        },
        error: err => {
          const errorMessage: DisplayMessage = {
            id: `err-${Date.now()}`,
            role: 'assistant',
            content: `⚠️ Error executing ADK Assistant query: ${
              err.error?.detail || err.message || 'Service temporarily unreachable.'
            }`,
            timestamp: new Date(),
          };
          this.messages.push(errorMessage);
          this.isLoading = false;
          this.shouldScrollToBottom = true;
        },
      });
  }

  onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  applySuggestion(suggestionPrompt: string): void {
    this.prompt = suggestionPrompt;
    if (this.promptInput) {
      this.promptInput.nativeElement.focus();
    }
  }

  copyContent(content: string, id: string): void {
    this.clipboard.copy(content);
    this.copiedMessageId = id;
    setTimeout(() => {
      if (this.copiedMessageId === id) {
        this.copiedMessageId = null;
      }
    }, 2000);
  }

  resetSession(): void {
    this.sessionId = this.generateSessionId();
    this.messages = [
      {
        id: `msg-init-${Date.now()}`,
        role: 'assistant',
        content:
          'Session refreshed. Ready for your next creative generation, prompt refinement, or brand alignment query.',
        timestamp: new Date(),
      },
    ];
    this.prompt = '';
    this.shouldScrollToBottom = true;
    if (this.promptInput) {
      this.promptInput.nativeElement.focus();
    }
  }

  private scrollToBottom(): void {
    if (this.scrollContainer) {
      try {
        const el = this.scrollContainer.nativeElement;
        el.scrollTo({
          top: el.scrollHeight,
          behavior: 'smooth',
        });
      } catch {
        // Fallback for non-smooth scrolling
      }
    }
  }

  trackByMsgId(_index: number, msg: DisplayMessage): string {
    return msg.id;
  }

  private generateSessionId(): string {
    return 'cs-adk-' + Math.random().toString(36).substring(2, 11) + '-' + Date.now();
  }
}
```

**3. Component Template (`frontend/src/app/custom/adk_assistant/adk-assistant.component.html`)**
```html
<div class="adk-assistant-view p-4 sm:p-6 lg:p-8 max-w-6xl mx-auto flex flex-col h-[calc(100vh-80px)]">
  <div class="flex-1 flex flex-col bg-zinc-900/90 backdrop-blur-2xl border border-white/10 rounded-3xl shadow-2xl overflow-hidden relative">

    <div class="absolute -top-32 -left-32 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute -bottom-32 -right-32 w-80 h-80 bg-violet-500/10 rounded-full blur-3xl pointer-events-none"></div>

    <header class="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-zinc-950/40 backdrop-blur-md z-10">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-2xl bg-gradient-to-r from-blue-500 via-violet-500 to-red-400 p-[1.5px] shadow-lg flex items-center justify-center">
          <div class="w-full h-full bg-zinc-950 rounded-[14px] flex items-center justify-center">
            <mat-icon class="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-violet-400 to-red-300 text-xl leading-none">auto_awesome</mat-icon>
          </div>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-lg font-semibold tracking-tight text-white">ADK Creative Assistant</h1>
            <span class="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-zinc-400">Custom Domain</span>
          </div>
          <p class="text-xs text-zinc-400">Google Cloud Creative Studio • {{ serviceName }}</p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <div
          class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-zinc-950/80 border border-white/10 text-xs font-mono text-zinc-300 shadow-inner"
          [matTooltip]="'Connected to model ' + modelName"
        >
          <span
            class="w-2 h-2 rounded-full transition-colors"
            [ngClass]="{
              'bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]': status === 'Online',
              'bg-amber-400 animate-pulse': status === 'Connecting',
              'bg-rose-500': status === 'Offline'
            }"
          ></span>
          <span class="font-medium capitalize">{{ status }}</span>
          <span class="text-zinc-500">•</span>
          <span class="text-zinc-400 font-sans text-[11px]">{{ modelName }}</span>
        </div>

        <button
          mat-icon-button
          (click)="resetSession()"
          matTooltip="New Session (Clear Chat)"
          aria-label="New Session"
          class="!text-zinc-400 hover:!text-zinc-100 !bg-white/5 hover:!bg-white/10 !border !border-white/10 !rounded-xl transition-all"
        >
          <mat-icon class="text-base">refresh</mat-icon>
        </button>
      </div>
    </header>

    <div
      #scrollContainer
      class="flex-1 overflow-y-auto p-6 space-y-6 scroll-smooth custom-scrollbar z-10"
    >
      <div *ngFor="let msg of messages; trackBy: trackByMsgId" class="flex flex-col">
        <!-- Assistant Message Bubble -->
        <div *ngIf="msg.role === 'assistant'" class="flex items-start gap-3 max-w-3xl">
          <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-500 via-violet-500 to-red-400 p-[1px] flex-shrink-0 mt-1 shadow-md">
            <div class="w-full h-full bg-zinc-950 rounded-[11px] flex items-center justify-center">
              <mat-icon class="text-violet-400 text-sm leading-none">auto_awesome</mat-icon>
            </div>
          </div>

          <div class="flex flex-col gap-1.5 flex-1 min-w-0">
            <div class="bg-zinc-900/90 border border-white/10 rounded-2xl rounded-tl-sm p-4 text-zinc-100 shadow-xl backdrop-blur-xl group relative">
              <div class="text-sm leading-relaxed whitespace-pre-wrap selection:bg-violet-500/30">{{ msg.content }}</div>

              <div class="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-xs text-zinc-400">
                <span class="text-[11px] text-zinc-500">{{ msg.timestamp | date:'shortTime' }}</span>
                <button
                  type="button"
                  (click)="copyContent(msg.content, msg.id)"
                  class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 hover:border-white/20 text-zinc-300 hover:text-white transition-all text-xs cursor-pointer"
                  [matTooltip]="copiedMessageId === msg.id ? 'Copied to clipboard!' : 'Copy response text'"
                >
                  <mat-icon class="text-xs !w-3.5 !h-3.5 leading-none">{{ copiedMessageId === msg.id ? 'check' : 'content_copy' }}</mat-icon>
                  <span>{{ copiedMessageId === msg.id ? 'Copied' : 'Copy' }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- User Message Bubble -->
        <div *ngIf="msg.role === 'user'" class="flex items-start justify-end gap-3 max-w-3xl ml-auto">
          <div class="flex flex-col items-end gap-1.5">
            <div class="bg-gradient-to-br from-indigo-600/30 to-blue-600/20 border border-indigo-500/30 rounded-2xl rounded-tr-sm p-4 text-zinc-100 shadow-lg backdrop-blur-xl max-w-2xl">
              <div class="text-sm leading-relaxed whitespace-pre-wrap selection:bg-blue-500/30">{{ msg.content }}</div>
            </div>
            <span class="text-[11px] text-zinc-500 mr-2">{{ msg.timestamp | date:'shortTime' }}</span>
          </div>

          <div class="w-8 h-8 rounded-xl bg-zinc-800 border border-white/10 flex-shrink-0 mt-1 flex items-center justify-center shadow-md">
            <mat-icon class="text-zinc-300 text-sm leading-none">person</mat-icon>
          </div>
        </div>
      </div>

      <!-- Thinking State Indicator -->
      <div *ngIf="isLoading" class="flex items-start gap-3 max-w-xl animate-fade-in">
        <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-500 via-violet-500 to-red-400 p-[1px] flex-shrink-0 mt-1 animate-pulse">
          <div class="w-full h-full bg-zinc-950 rounded-[11px] flex items-center justify-center">
            <mat-icon class="text-violet-400 text-sm leading-none animate-spin">auto_awesome</mat-icon>
          </div>
        </div>

        <div class="bg-zinc-900/90 border border-white/10 rounded-2xl rounded-tl-sm p-4 text-zinc-300 shadow-xl backdrop-blur-xl flex items-center gap-3">
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-blue-400 animate-bounce"></span>
            <span class="w-2 h-2 rounded-full bg-violet-400 animate-bounce [animation-delay:0.2s]"></span>
            <span class="w-2 h-2 rounded-full bg-red-400 animate-bounce [animation-delay:0.4s]"></span>
          </div>
          <span class="text-xs text-zinc-400 font-medium">Assistant is reasoning with {{ modelName }}...</span>
        </div>
      </div>
    </div>

    <!-- Suggestions Bar -->
    <div class="px-6 py-2.5 border-t border-white/5 bg-zinc-950/20 backdrop-blur-md z-10">
      <div class="flex items-center gap-2 overflow-x-auto no-scrollbar py-1">
        <span class="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider flex-shrink-0 flex items-center gap-1 mr-1">
          <mat-icon class="text-xs !w-3.5 !h-3.5">tips_and_updates</mat-icon>
          Suggestions:
        </span>
        <button
          *ngFor="let suggestion of quickSuggestions"
          type="button"
          (click)="applySuggestion(suggestion.prompt)"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-zinc-800/60 hover:bg-zinc-800/90 border border-white/10 hover:border-violet-500/40 text-zinc-300 hover:text-white text-xs whitespace-nowrap transition-all duration-200 shadow-sm cursor-pointer"
        >
          <mat-icon class="text-violet-400 text-xs !w-3.5 !h-3.5 leading-none">{{ suggestion.icon }}</mat-icon>
          <span>{{ suggestion.label }}</span>
        </button>
      </div>
    </div>

    <!-- Input Footer -->
    <footer class="p-4 sm:p-6 border-t border-white/10 bg-zinc-950/60 backdrop-blur-xl z-10">
      <div class="relative flex flex-col bg-zinc-950/80 border border-white/10 focus-within:border-indigo-500/80 focus-within:ring-1 focus-within:ring-indigo-500/40 rounded-2xl transition-all shadow-inner">
        <textarea
          #promptInput
          [(ngModel)]="prompt"
          (keydown)="onKeyDown($event)"
          placeholder="Ask anything about Imagen 3, Veo, prompt tuning, or brand guidelines... (Enter to send, Shift+Enter for newline)"
          rows="3"
          [disabled]="isLoading"
          class="w-full bg-transparent p-4 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none resize-none selection:bg-violet-500/30 custom-scrollbar disabled:opacity-50"
        ></textarea>

        <div class="flex items-center justify-between px-4 pb-3 pt-1">
          <div class="flex items-center gap-2 text-[11px] text-zinc-500">
            <mat-icon class="text-xs !w-3.5 !h-3.5">tune</mat-icon>
            <span class="font-mono">Session: {{ sessionId | slice:0:16 }}...</span>
          </div>

          <div class="flex items-center gap-2">
            <button
              mat-flat-button
              type="button"
              (click)="sendMessage()"
              [disabled]="!prompt.trim() || isLoading"
              class="!bg-gradient-to-r !from-blue-500 !via-violet-500 !to-red-400 hover:!opacity-95 !text-white !rounded-xl !px-5 !py-2 font-medium transition-all shadow-lg disabled:!opacity-40 disabled:!cursor-not-allowed flex items-center gap-2 cursor-pointer"
            >
              <span *ngIf="!isLoading" class="flex items-center gap-1.5 text-xs font-semibold tracking-wide">
                <span>Send</span>
                <mat-icon class="text-xs !w-3.5 !h-3.5 leading-none">send</mat-icon>
              </span>
              <span *ngIf="isLoading" class="flex items-center gap-2 text-xs">
                <mat-spinner diameter="14" class="!stroke-white"></mat-spinner>
                <span>Processing</span>
              </span>
            </button>
          </div>
        </div>
      </div>
    </footer>
  </div>
</div>
```

**4. Component SCSS (`frontend/src/app/custom/adk_assistant/adk-assistant.component.scss`)**
```scss
:host {
  display: block;
  min-height: calc(100vh - 64px);
  background-color: transparent;
}

.custom-scrollbar {
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.15) transparent;

  &::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.15);
    border-radius: 9999px;

    &:hover {
      background: rgba(255, 255, 255, 0.25);
    }
  }
}

.no-scrollbar {
  scrollbar-width: none;
  &::-webkit-scrollbar {
    display: none;
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in {
  animation: fadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
```

---

### Stage 2.4: Verification, Automated Testing & Hardening

#### Stage 2.4 Recipe Prompt
```text
# STAGE 2.4: VERIFICATION, AUTOMATED TESTING & HARDENING
Implement the full pytest test suite in backend/tests/custom/adk_assistant/test_adk_assistant.py, execute tests with coverage validation, verify container and build packaging for /custom/ domains, update the master guide docs/CREATIVE_STUDIO_MOD.md, and record post-execution debrief.
```

#### Test Suite Implementation (`backend/tests/custom/adk_assistant/test_adk_assistant.py`)
```python
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
        self.assertEqual(root_agent.model, "gemini-3.7-flash")
        self.assertEqual(root_agent.model, AGENT_MODEL)
        self.assertIn(
            "Google Cloud Creative Studio AI Assistant",
            root_agent.instruction,
        )
        self.assertIn("Imagen and Veo", root_agent.instruction)
        self.assertEqual(root_agent.instruction, AGENT_INSTRUCTION)
        self.assertIsNotNone(root_agent.description)

    def test_health_check_endpoint(self):
        """Verifies GET /api/custom/adk-assistant/health returns HTTP 200 and valid JSON."""
        response = self.client.get("/api/custom/adk-assistant/health")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["agentName"], "creative_studio_assistant")
        self.assertEqual(data["model"], "gemini-3.7-flash")
        self.assertEqual(data["service"], "adk-assistant")
        self.assertEqual(data["version"], "0.1.0")

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
            self.assertEqual(data["metadata"]["model"], "gemini-3.7-flash")

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
            yield

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
```

#### Actual Captured Pytest Execution Logs & Coverage Output
```text
============================= test session starts ==============================
platform linux -- Python 3.13.14, pytest-9.0.2, pluggy-1.6.0 -- /usr/local/google/home/sergiorego/creative_studio_mod_guide/gcc-creative-studio/backend/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /usr/local/google/home/sergiorego/creative_studio_mod_guide/gcc-creative-studio/backend
configfile: pytest.ini
plugins: anyio-4.12.0, cov-7.0.0, asyncio-1.3.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ...
collected 7 items

tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_agent_initialization PASSED [ 14%]
tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_chat_endpoint_empty_parts_fallback PASSED [ 28%]
tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_chat_endpoint_internal_error_handling PASSED [ 42%]
tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_chat_endpoint_success PASSED [ 57%]
tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_chat_endpoint_validation_error PASSED [ 71%]
tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_health_check_endpoint PASSED [ 85%]
tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_query_alias_endpoint PASSED [100%]

================================ tests coverage ================================
_______________ coverage: platform linux, python 3.13.14-final-0 _______________

Name                                   Stmts   Miss  Cover   Missing
--------------------------------------------------------------------
src/custom/adk_assistant/__init__.py       4      0   100%
src/custom/adk_assistant/agent.py          5      0   100%
src/custom/adk_assistant/router.py        46      1    98%   134
src/custom/adk_assistant/schemas.py       36      0   100%
--------------------------------------------------------------------
TOTAL                                     91      1    99%
======================== 7 passed, 2 warnings in 0.22s =========================
```

#### Container Packaging & Build Verification
- **Backend Dockerfile (`backend/Dockerfile`):**
  Uses `COPY . /app` and `uv sync --locked --no-dev`. Custom domain modules under `backend/src/custom/` are bundled directly into the container image with zero custom Dockerfile edits.
- **Frontend Dockerfile (`frontend/Dockerfile`):**
  Uses multi-stage build (`npm run build-dev`) producing nginx static distribution assets. Standalone Angular components under `frontend/src/app/custom/` compile natively.
- **TypeScript Static Compilation:**
  `npm run compile` (`tsc --noEmit`) validates all components and services with 0 errors.

---

### Stage 2.5: Upstream Sync CI/CD Workflow & Maintenance

#### Stage 2.5 Recipe Prompt
```text
# STAGE 2.5: UPSTREAM SYNC CI/CD WORKFLOW & MASTER PLAYBOOK FINALIZATION
Implement the automated GitHub Actions upstream sync workflow file (.github/workflows/upstream-sync.yml) with scheduled cron execution, dry-run merge conflict detection, backend pytest execution, frontend TypeScript compilation, and automated issue creation upon regression. Finalize docs/CREATIVE_STUDIO_MOD.md as the master enablement playbook.
```

#### GitHub Actions Upstream Sync Workflow (`.github/workflows/upstream-sync.yml`)
```yaml
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

name: Upstream Sync & Conflict Check

on:
  schedule:
    - cron: '0 4 * * 1' # Runs weekly on Mondays at 04:00 UTC
  workflow_dispatch:

permissions:
  contents: write
  issues: write
  pull-requests: write

jobs:
  sync-upstream:
    name: Sync Upstream & Verify Domain Integrity
    runs-on: ubuntu-latest
    env:
      PROJECT_ID: 'dummy-project-id'

    steps:
      - name: Checkout working branch
        uses: actions/checkout@v4
        with:
          ref: feature/adk-assistant
          fetch-depth: 0

      - name: Configure upstream remote
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git remote add upstream https://github.com/GoogleCloudPlatform/gcc-creative-studio.git || git remote set-url upstream https://github.com/GoogleCloudPlatform/gcc-creative-studio.git
          git fetch upstream main

      - name: Dry-run merge check
        id: merge_check
        run: |
          echo "Executing dry-run merge of upstream/main to detect merge conflicts or drift..."
          if ! git merge --no-commit --no-ff upstream/main; then
            echo "::error::Merge conflict detected between upstream/main and feature/adk-assistant!"
            git merge --abort || true
            exit 1
          fi
          git merge --abort || true
          echo "Upstream main is cleanly mergeable with feature/adk-assistant."

      - name: Execute upstream merge
        run: |
          echo "Merging upstream/main into feature/adk-assistant..."
          git merge upstream/main -m "chore(sync): merge upstream/main into feature/adk-assistant" --no-edit

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Set up uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
          cache-dependency-glob: "backend/uv.lock"

      - name: Install backend dependencies
        run: |
          cd backend
          uv sync --all-extras

      - name: Run Backend & Custom Domain Tests
        run: |
          cd backend
          uv run pytest tests/custom/adk_assistant/ -v --cov=src/custom/adk_assistant

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install frontend dependencies
        run: |
          cd frontend
          npm ci

      - name: Run Frontend Compilation Check
        run: |
          cd frontend
          npm run compile

      - name: Create GitHub Issue Alert on Failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
            const issueTitle = `🚨 [Upstream Sync Alert] Conflict or Test Failure Detected on ${context.ref}`;
            const issueBody = `### Upstream Sync Automated Failure Report\n\n` +
              `An automated upstream synchronization workflow run has **failed** on branch \`${context.ref}\`.\n\n` +
              `- **Run URL:** [View Workflow Run Details](${runUrl})\n` +
              `- **Trigger:** \`${context.eventName}\`\n` +
              `- **Commit SHA:** \`${context.sha}\`\n` +
              `- **Upstream Repository:** \`GoogleCloudPlatform/gcc-creative-studio:main\`\n\n` +
              `### Required Action Items:\n` +
              `1. Check if merge conflicts occurred between \`upstream/main\` and \`feature/adk-assistant\`.\n` +
              `2. Verify if breaking upstream changes impacted \`backend/src/custom/adk_assistant/\` or \`frontend/src/app/custom/adk_assistant/\`.\n` +
              `3. Re-run local test validation via \`uv run pytest tests/custom/adk_assistant/\` and \`npm run compile\` in \`frontend\`.\n`;
            
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: issueTitle,
              body: issueBody,
              labels: ['upstream-sync', 'automated-alert', 'bug']
            });
```

---

## 4. Automated Upstream Sync & Maintenance Operational Playbook

### Upstream Synchronization Cycle
```
┌─────────────────────────────────────────────────────────────┐
│ Weekly Cron Schedule (Mondays 04:00 UTC) / Manual Dispatch  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Fetch upstream/main with full history depth (depth: 0)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Dry-Run Non-Commit Merge (git merge --no-commit --no-ff) │
└──────────────────────────────┬──────────────────────────────┘
                               │
             ┌─────────────────┴─────────────────┐
             │ Clean                             │ Conflict Detected
             ▼                                   ▼
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ 3. Execute git merge upstream│   │ 3b. Abort merge              │
│ 4. Run uv sync & Pytest (99%)│   │ 4b. Fail workflow step       │
│ 5. Run npm compile           │   │ 5b. Auto-create GitHub Issue │
└──────────────────────────────┘   └──────────────────────────────┘
```

### Conflict Resolution Protocol
1. If the CI/CD workflow creates an automated conflict issue, check out `feature/adk-assistant` locally.
2. Fetch and review upstream diffs: `git fetch upstream main && git merge --no-commit upstream/main`.
3. If conflicts occur on core hook files (`backend/main.py`, `frontend/src/app/app-routing.module.ts`, or `header.component.html`), consult the **Pre-Flight Invariants & Triage Matrix** in Section 1.
4. Keep all `/custom/` files untouched and re-apply hook registrations.
5. Validate with `uv run pytest tests/custom/adk_assistant/ -v` and `npm run compile`.
6. Commit the merge resolution and push to `origin/feature/adk-assistant`.

---

## 5. Troubleshooting & Field Notes Matrix

| Domain / Area | Issue / Symptom | Root Cause | Verified Resolution |
|---|---|---|---|
| **ADK Version Handling** | `DeprecationWarning: BaseAgentConfig is deprecated` | In recent Google ADK releases, configuration schemas load via reflection rather than static config classes. | Define agents directly via `Agent(name=..., model=..., instruction=...)` without initializing deprecated `BaseAgentConfig` objects. |
| **CORS Configuration** | Browser blocks `OPTIONS /custom/adk-assistant/chat` (CORS Preflight Error) | Custom router mounted with `/api/` prefix or CORS origins missing local dev ports. | Ensure `configure_cors(app)` runs in `backend/main.py` before router mounting, and use the standard prefix `/api/custom/adk-assistant` with Angular proxy forwarding. |
| **Session State Persistence** | Context lost between subsequent chat turns in multi-worker deployment | `InMemorySessionService` stores sessions locally in Python process memory; Cloud Run or multi-worker Gunicorn spawns independent memories. | In single-instance dev, `InMemorySessionService` maintains turn state per `sessionId`. For multi-instance production, plug a persistent Redis/Firestore `SessionService` into the `Runner(session_service=...)`. |
| **Angular Routing Guards** | Navigating to `/custom/adk-assistant` redirects to `/login` or blank screen | `canActivate: [AuthGuardService]` blocks unauthenticated route entry; or standalone component is missing necessary Angular imports. | Ensure test sessions are authenticated or pass token headers. In standalone components, explicitly import `CommonModule`, `FormsModule`, `MatIconModule`, and `MatButtonModule` in the `@Component` imports array. |
| **FastAPI Middleware Stack** | Direct `TestClient(router)` raises `fastapi_middleware_astack not found` | In FastAPI 0.140+, passing an unmounted `APIRouter` to `TestClient` lacks application-level middleware context. | Instantiate a test application wrapper in unit test files: `app = FastAPI(); app.include_router(router); client = TestClient(app)`. |
| **Pytest Runner Collection** | `PytestCollectionWarning: cannot collect test class 'TestApp'` | Test runner matches variables or instances starting with `test_` or `Test`. | Name test FastAPI application instance `app` instead of `test_app`. |
| **Environment Isolation** | `ModuleNotFoundError: No module named 'google.adk'` when running global Python | Local Python environment does not have project dependencies installed globally. | Always execute commands through `uv run` (e.g., `uv run pytest`, `uv run python`) to execute within the project virtual environment. |
