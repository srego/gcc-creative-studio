# Creative Studio Mod Guide: Extending Creative Studio While Keeping Core Updated

This guide provides a structured, agent-assisted methodology to extend an existing Google Cloud Creative Studio deployment with custom capabilities while preserving a clean upstream update path.

---

## 1. Executive Summary & Architecture

To ensure zero merge conflicts when updating from `GoogleCloudPlatform/gcc-creative-studio`, all custom features MUST adhere to the **Isolated Domain Pattern**.

### Target Environment Parameters
- **Base Upstream Repository:** `https://github.com/GoogleCloudPlatform/gcc-creative-studio`
- **Active Working Branch:** `feature/adk-assistant`
- **Target GCP Project ID:** `creative-studio-delta2` (Project Number: `456871514227`)

### The Isolated Domain Rule
gcc-creative-studio/
├── backend/
│ └── src/
│ └── custom/
│ └── [feature-slug]/ <-- ALL custom backend logic lives here
├── frontend/
│ └── src/app/
│ └── custom/
│ └── [feature-slug]/ <-- ALL custom Angular components live here
└── backend/tests/
└── custom/
└── [feature-slug]/ <-- ALL custom tests live here

*   **Allowed Core Hook Points (3 Files Max):**
    1. `backend/main.py` (Router mounting)
    2. `frontend/src/app/app-routing.module.ts` (Route mapping)
    3. `frontend/src/app/header/header.component.html` (Navbar icon link)

---

## 2. Prerequisites & Pre-Flight Assessment

### Step 0: Pre-Flight Compatibility Assessment
Before generating or applying custom code, run the **Pre-Flight Assessor Agent** in your local terminal/chat (`⌘ + L`) to verify current upstream integration paths:

<details>
<summary><b>▶ Click to Expand Pre-Flight Assessor Prompt</b></summary>

```text
# PRE-FLIGHT CHECK: CREATIVE STUDIO EXTENSION COMPATIBILITY ASSESSOR

You are the Environment Compatibility Assessor. Analyze the current repository structure to confirm integration invariants before applying custom extensions.

## 1. Inspection Checklist
1. Routing Pattern: Check whether routing uses `app-routing.module.ts` or standalone `app.routes.ts`.
2. Navigation Anchor: Locate the primary navigation template (e.g., `frontend/src/app/header/header.component.html` or equivalent sidebar).
3. Backend Router Registration: Inspect `backend/main.py` to identify how routers are mounted (`app.include_router(...)`).
4. Design Tokens: Verify that `UI_DESIGN_SYSTEM.md` matches current styles.

## 2. Output Report
Generate a brief Compatibility Report with:
- Compatibility Status: [READY | ADAPTATIONS REQUIRED]
- Detected Integration Paths (exact file paths for routing, navbar, and main.py)
- Any recommended parameter overrides for Stage 1/2 prompts.
3. The 4-Stage Implementation Recipes
Execute the following sequential prompts with your local agent to scaffold, implement, test, and document your feature.

Stage 1: Domain Scaffolding & Core Hooks
[FILL BY AGENT: Paste Stage 2.1 Recipe Prompt & Files Created]

Stage 2: Backend ADK Integration
[FILL BY AGENT: Paste Stage 2.2 Recipe Prompt & FastAPI Contract]

Stage 3: Frontend UI Implementation
[FILL BY AGENT: Paste Stage 2.3 Recipe Prompt & Component Details]

Stage 4: Verification, Testing & Hardening
[FILL BY AGENT: Paste Stage 2.4 Recipe Prompt & Pytest Results]

4. Upstream Synchronization Strategy
To keep your fork updated with official upstream/main updates without breaking your custom features:

yaml
# .github/workflows/upstream-sync.yml
# [FILL BY AGENT: Insert GitHub Actions workflow yaml]
5. Field Notes & Troubleshooting
Issue / Symptom	Root Cause	Resolution
[FILL BY AGENT: Issue 1]	[FILL BY AGENT: Cause 1]	[FILL BY AGENT: Fix 1]
[FILL BY AGENT: Issue 2]	[FILL BY AGENT: Cause 2]	[FILL BY AGENT: Fix 2]
 

---