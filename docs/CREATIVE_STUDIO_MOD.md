# Creative Studio Mod Guide: Extending Creative Studio While Keeping Core Updated

# PRE-FLIGHT CHECK: CREATIVE STUDIO EXTENSION COMPATIBILITY ASSESSOR

You are the Environment Compatibility Assessor. Before we apply custom extensions, analyze the current repository structure to confirm integration invariants.

## 1. Inspection Checklist
1. Routing Pattern: Check whether routing uses `app-routing.module.ts` or standalone `app.routes.ts`.
2. Navigation Anchor: Locate the primary navigation template (e.g., `frontend/src/app/header/header.component.html` or equivalent sidebar).
3. Backend Router Registration: Inspect `backend/main.py` to identify how routers are mounted (`app.include_router(...)`).
4. Design Tokens: Verify that `UI_DESIGN_SYSTEM.md` matches the current `styles.scss` and `tailwind.config.js`.

## 2. Output Report
Generate a brief Compatibility Report with:
- Compatibility Status: [READY | ADAPTATIONS REQUIRED]
- Detected Integration Paths (exact file paths for routing, navbar, and main.py)
- Any recommended parameter overrides for Stage 1/2 prompts.

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
[FILL BY AGENT: Paste the exact Stage 2 prompt used to wrap agent.py into FastAPI]
- **FastAPI Router Contract:**
  [FILL BY AGENT: Show the request/response schema]

### Stage 3: Frontend UI Implementation
[FILL BY AGENT: Paste the exact Stage 3 prompt used to build the Angular component]
- **Component Details:**
  [FILL BY AGENT: Describe reactive signals and UI elements]

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
| [FILL BY AGENT: Issue 1] | [FILL BY AGENT: Cause 1] | [FILL BY AGENT: Fix 1] |
| [FILL BY AGENT: Issue 2] | [FILL BY AGENT: Cause 2] | [FILL BY AGENT: Fix 2] |











