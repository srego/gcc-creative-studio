# Creative Studio Mod Guide: Extending Creative Studio While Keeping Core Updated

# PRE-FLIGHT CHECK: CREATIVE STUDIO EXTENSION COMPATIBILITY ASSESSOR & TRIAGE MATRIX

Before applying custom extensions, execute the following triage invariant checks to verify integration baselines and resolve upstream drift:

| # | Invariant Check | CLI Verification Command | Expected Baseline | If Upstream Drift Detected (Remediation) |
|---|---|---|---|---|
| **1** | **Frontend Routing Pattern** | `test -f frontend/src/app/app-routing.module.ts && echo "NgModule" \|\| echo "Standalone"` | File exists (`app-routing.module.ts`) using Angular `Routes` array. | **If Standalone (`app.routes.ts`):** Register the route `{ path: 'custom/adk-assistant', loadComponent: () => import(...) }` in `frontend/src/app/app.routes.ts` instead of `app-routing.module.ts`. |
| **2** | **Navigation Container** | `grep -n "routerLink" frontend/src/app/header/header.component.html` | Top navigation toolbar with floating circular icon items. | **If Nav Moved to Sidebar (`sidebar.component.html`):** Place the `<mat-icon>auto_awesome</mat-icon>` button inside the sidebar menu list item rather than the header. |
| **3** | **Backend Router Hook** | `grep -n "app.include_router" backend/main.py` | `main.py` initializes FastAPI and mounts routers via `app.include_router(...)`. | **If Factory Pattern (`create_app()`):** Mount `app.include_router(adk_assistant_router)` inside the application factory function in `backend/main.py`. |
| **4** | **Python Package Manager** | `which uv && uv --version` | `uv` package manager installed (Python 3.12+ runtime). | **If Using Poetry/Pipenv:** Run `poetry add google-adk` or `pip install google-adk` instead of `uv add`. |

---

## 1. Executive Summary & Architecture
This guide provides a paved path to extend an existing Google Cloud Creative Studio instance with custom capabilities while preserving the upstream update path.

### Target Environment Details
- **Base Upstream Repository:** https://github.com/GoogleCloudPlatform/gcc-creative-studio
- **Active Working Branch:** feature/adk-assistant
- **Target GCP Project ID:** creative-studio-delta2
- **Target GCP Project Number:** 456871514227

### The Rule of Isolation
All extensions MUST reside strictly within isolated namespaces:
- **Backend Custom Code:** `backend/src/custom/adk_assistant/`
- **Frontend Custom Code:** `frontend/src/app/custom/adk_assistant/`
- **Unit Tests:** `backend/tests/custom/adk_assistant/`
- **Rule:** Never modify core business logic outside of `/custom/`. Core edits are restricted to routing (`app-routing.module.ts`) and navigation header links.

---

## 2. Prerequisites & Initial Setup
- Creative Studio is deployed on GCP project `creative-studio-delta2`.
- Local tools verified: `gcloud`, `terraform` (v1.14.1+), `uv`, `node` (v18+).

---

## 3. The 4-Stage Agent Implementation Recipes

### Stage 1: Domain Scaffolding
- **Stage 1 Prompt:**
  ```text
  # STAGE 2.1: DOMAIN SCAFFOLDING & CORE INTEGRATION HOOKS
  Create the isolated domain structure under backend/src/custom/adk_assistant/, frontend/src/app/custom/adk_assistant/, and backend/tests/custom/adk_assistant/. Register the 3 minimal core integration hooks in backend/main.py, frontend/src/app/app-routing.module.ts, and frontend/src/app/header/header.component.html.
  ```
- **Key Files Created/Modified:**
  - `backend/src/custom/adk_assistant/__init__.py`
  - `backend/src/custom/adk_assistant/schemas.py`
  - `backend/src/custom/adk_assistant/router.py`
  - `frontend/src/app/custom/adk_assistant/adk-assistant.component.ts`
  - `frontend/src/app/custom/adk_assistant/adk-assistant.component.html`
  - `frontend/src/app/custom/adk_assistant/adk-assistant.component.scss`
  - `frontend/src/app/custom/adk_assistant/adk-assistant.service.ts`
  - `backend/tests/custom/adk_assistant/__init__.py`
  - Core Hook 1: `backend/main.py`
  - Core Hook 2: `frontend/src/app/app-routing.module.ts`
  - Core Hook 3: `frontend/src/app/header/header.component.html`

### Stage 2: Backend ADK Integration
- **Stage 2 Prompt:**
  ```text
  # STAGE 2.2: BACKEND ADK AGENT & FASTAPI ROUTER IMPLEMENTATION + ASSESSOR TRIAGE MATRIX
  Implement the backend ADK domain files (agent.py, schemas.py, router.py) and update docs/CREATIVE_STUDIO_MOD.md with the actionable Pre-Flight Triage Matrix.
  ```
- **ADK Agent Definition (`backend/src/custom/adk_assistant/agent.py`):**
  - **Agent Name:** `creative_studio_assistant`
  - **Model:** `gemini-3.7-flash`
  - **Instructions:** "You are the Google Cloud Creative Studio AI Assistant. Assist users with prompt engineering for Imagen and Veo, brand guideline adherence, workflow automation, and multimodal creative generation. Provide concise, high-impact creative recommendations and structured prompt templates."
- **FastAPI Router Contract (`backend/src/custom/adk_assistant/router.py`):**
  - **Prefix:** `/api/custom/adk-assistant`
  - **Tags:** `["Custom: ADK Assistant"]`
  - **Endpoints:**
    - `GET /health` -> Returns `HealthResponse(status="healthy", agent_name="creative_studio_assistant", model="gemini-3.7-flash", service="adk-assistant", version="0.1.0")`
    - `POST /chat` -> Accepts `QueryRequest(message, session_id, history, context)`, runs `google.adk.runners.Runner` with `InMemorySessionService`, and returns `QueryResponse(response, session_id, agent_name, metadata)`
    - `POST /query` -> Backward-compatible endpoint alias for `/chat`
- **Pydantic Schemas (`backend/src/custom/adk_assistant/schemas.py`):**
  ```python
  class ChatMessage(BaseModel):
      role: Literal["user", "assistant", "system", "model"]
      content: str
      timestamp: datetime

  class QueryRequest(BaseModel):
      message: str
      prompt: str | None = None
      session_id: str | None = None
      history: list[ChatMessage] | None = None
      context: dict[str, Any] | None = None

  class QueryResponse(BaseModel):
      response: str
      session_id: str | None = None
      agent_name: str = "creative_studio_assistant"
      metadata: dict[str, Any] | None = None

  class HealthResponse(BaseModel):
      status: str = "healthy"
      agent_name: str = "creative_studio_assistant"
      model: str = "gemini-3.7-flash"
      service: str = "adk-assistant"
      version: str = "0.1.0"
  ```
- **Verification & Unit Tests:**
  - Automated test suite in `backend/tests/custom/adk_assistant/test_adk_assistant.py` verified via `uv run python -m unittest`.

### Stage 3: Frontend UI Implementation
- **Stage 3 Prompt:**
  ```text
  # STAGE 2.3: FRONTEND REACTIVE UI & SERVICE IMPLEMENTATION
  Implement the Angular client service (adk-assistant.service.ts) and interactive chat UI component (adk-assistant.component.ts, .html, .scss) adhering to the Creative Studio UI design system (dark glassmorphism, Gemini Spectrum accents, live status pill, message thread, suggestion chips, clipboard copy, and thinking animation).
  ```
- **Client Service Contract (`frontend/src/app/custom/adk_assistant/adk-assistant.service.ts`):**
  - **Interfaces:** `ChatMessage`, `QueryRequest`, `QueryResponse`, `HealthResponse`.
  - **Methods:**
    - `sendMessage(message: string, sessionId?: string, history?: ChatMessage[]): Observable<QueryResponse>` -> `POST ${environment.backendURL}/custom/adk-assistant/chat`
    - `checkHealth(): Observable<HealthResponse>` -> `GET ${environment.backendURL}/custom/adk-assistant/health`
    - `query(prompt: string, sessionId?: string): Observable<QueryResponse>` -> Legacy query alias
- **Component Architecture (`frontend/src/app/custom/adk_assistant/`):**
  - **Surface & Design Tokens:** High-contrast dark glassmorphic cards (`bg-zinc-900/90`, `backdrop-blur-2xl`, `border border-white/10`, `shadow-2xl`) with Gemini Spectrum gradient accents (`bg-gradient-to-r from-blue-500 via-violet-500 to-red-400`).
  - **Live Connection Header:** Real-time status pill (`Online • gemini-3.7-flash`), session identifier display, and one-click session reset (`resetSession()`).
  - **Message Thread:** Chat bubble stream distinguishing user prompts from assistant responses, including timestamps and clipboard copy actions with visual confirmation.
  - **Quick Suggestions:** Interactive chips for rapid prompt engineering:
    - *Optimize Imagen Prompt*
    - *Generate Veo Storyboard*
    - *Brand Consistency Check*
    - *Multimodal Concept Ideas*
  - **Input Box & Interactivity:** Textarea with auto-focus, keyboard listeners (`Enter` to submit, `Shift+Enter` for multiline), and gradient submit button with loading spinner.
  - **Animated Thinking State:** Multi-dot gradient bouncing indicator active while awaiting model generation.

### Stage 4: Testing & Hardening
[FILL BY AGENT: Paste the exact Stage 4 prompt used for tests and Docker/Terraform review]
- **Verification Results:**
  [FILL BY AGENT: Show pytest coverage output and build status]

---

## 4. Automated Upstream Sync Strategy
[FILL BY AGENT: Insert GitHub Actions workflow yaml for upstream tracking]

---

## 5. Troubleshooting & Field Notes
| Issue / Symptom | Root Cause | Resolution |
|---|---|---|
| Direct `TestClient(router)` raises `fastapi_middleware_astack not found` | In FastAPI 0.141+, raw APIRouter in TestClient lacks middleware stack | Mount router on a `FastAPI()` application instance in tests |
| Global Python lacks ADK package | Environment isolation using uv virtualenv | Execute all Python scripts and tests with `uv run` |
