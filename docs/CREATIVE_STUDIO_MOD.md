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
- **Stage 4 Prompt:**
  ```text
  # STAGE 2.4: VERIFICATION, AUTOMATED TESTING & HARDENING
  Implement the full pytest test suite in backend/tests/custom/adk_assistant/test_adk_assistant.py, execute tests with coverage validation, verify container and build packaging for /custom/ domains, update the master guide docs/CREATIVE_STUDIO_MOD.md, and record post-execution debrief.
  ```
- **Test Suite Architecture (`backend/tests/custom/adk_assistant/test_adk_assistant.py`):**
  - `test_agent_initialization`: Validates `root_agent` metadata, model configuration (`gemini-3.7-flash`), and system instructions.
  - `test_health_check_endpoint`: Validates `GET /api/custom/adk-assistant/health` returns HTTP 200, status `healthy`, and correct model metadata.
  - `test_chat_endpoint_success`: Validates `POST /api/custom/adk-assistant/chat` with mocked `google.adk.runners.Runner` and session service, asserting structured responses.
  - `test_chat_endpoint_validation_error`: Validates HTTP 400 rejection for empty and whitespace payloads.
  - `test_query_alias_endpoint`: Validates legacy `POST /api/custom/adk-assistant/query` alias endpoint.
  - `test_chat_endpoint_internal_error_handling`: Validates HTTP 500 error mapping when runner fails.
  - `test_chat_endpoint_empty_parts_fallback`: Validates fallback messaging when agent events contain no text parts.

- **Verification Results & Test Coverage:**
  ```text
  ============================= test session starts ==============================
  platform linux -- Python 3.13.14, pytest-9.0.2, pluggy-1.6.0
  rootdir: backend
  configfile: pytest.ini
  plugins: anyio-4.12.0, cov-7.0.0, asyncio-1.3.0
  collected 7 items

  tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_agent_initialization PASSED [ 14%]
  tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_chat_endpoint_empty_parts_fallback PASSED [ 28%]
  tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_chat_endpoint_internal_error_handling PASSED [ 42%]
  tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_chat_endpoint_success PASSED [ 57%]
  tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_chat_endpoint_validation_error PASSED [ 71%]
  tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_health_check_endpoint PASSED [ 85%]
  tests/custom/adk_assistant/test_adk_assistant.py::TestAdkAssistantSuite::test_query_alias_endpoint PASSED [100%]

  ================================ tests coverage ================================
  Name                                   Stmts   Miss  Cover   Missing
  --------------------------------------------------------------------
  src/custom/adk_assistant/__init__.py       4      0   100%
  src/custom/adk_assistant/agent.py          5      0   100%
  src/custom/adk_assistant/router.py        46      1    98%   134
  src/custom/adk_assistant/schemas.py       36      0   100%
  --------------------------------------------------------------------
  TOTAL                                     91      1    99%
  ======================== 7 passed, 2 warnings in 0.31s =========================
  ```

- **Container & Packaging Verification:**
  - **Backend Container (`backend/Dockerfile`):** Copies entire project context (`COPY . /app`) and syncs locked dependencies via `uv sync --locked --no-dev`. Custom domain modules under `backend/src/custom/` and `google-adk` dependencies in `pyproject.toml` / `uv.lock` are packaged automatically with zero Dockerfile overrides.
  - **Frontend Container (`frontend/Dockerfile`):** Multi-stage build copies workspace context (`COPY . /app/`) and runs Angular compilation (`npm run build-dev`), packaging `frontend/src/app/custom/` into static nginx assets without requiring custom build steps.
  - **TypeScript Static Analysis:** Verified with `npm run compile` (`tsc --noEmit`) passing with 0 errors.

---

## 4. Automated Upstream Sync Strategy
To ensure long-term maintainability and effortless synchronization with Google's upstream `gcc-creative-studio` releases, configure a GitHub Actions upstream synchronization workflow:

```yaml
# .github/workflows/upstream-sync.yml
name: Upstream Sync & Conflict Check

on:
  schedule:
    - cron: '0 3 * * 1' # Runs weekly on Mondays at 03:00 UTC
  workflow_dispatch:

jobs:
  sync-upstream:
    name: Sync Upstream & Detect Drift
    runs-on: ubuntu-latest
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
          git remote add upstream https://github.com/GoogleCloudPlatform/gcc-creative-studio.git
          git fetch upstream main

      - name: Check for upstream drift / mergeability
        run: |
          echo "Attempting dry-run merge of upstream/main..."
          git merge --no-commit --no-ff upstream/main || {
            echo "::error::Merge conflict detected between upstream/main and feature/adk-assistant!"
            git merge --abort
            exit 1
          }
          git merge --abort
          echo "Upstream main is cleanly mergeable with custom domain."

      - name: Run Backend & Custom Domain Tests
        run: |
          cd backend
          curl -LsSf https://astral.sh/uv/install.sh | sh
          export PATH="$HOME/.local/bin:$PATH"
          uv sync --all-extras
          uv run pytest tests/ -v
```

---

## 5. Troubleshooting & Field Notes
| Issue / Symptom | Root Cause | Resolution |
|---|---|---|
| Direct `TestClient(router)` raises `fastapi_middleware_astack not found` | In FastAPI 0.141+, raw APIRouter in TestClient lacks middleware stack | Mount router on a `FastAPI()` application instance in tests |
| Global Python lacks ADK package | Environment isolation using uv virtualenv | Execute all Python scripts and tests with `uv run` |
| Pytest collects FastAPI app instance as a test function | Test runner matches variables starting with `test_` | Rename test FastAPI application instance to `app` |

