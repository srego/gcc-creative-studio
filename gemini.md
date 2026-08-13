# Gemini Agent Context - Subtitles Studio & Podcast Transcription Suite

## System Overview
This repository is a customized enterprise-grade fork of `gcc-creative-studio`. It contains the **Subtitles Studio**, implementing Speech-to-Text v2 (`chirp_3`), Vertex AI Gemini multimodal fallback transcription, and multithreaded FFmpeg video burned-in preview rendering.

## Zero-Collision Architecture Guidelines
To ensure seamless continuous synchronization with the upstream repository (`GoogleCloudPlatform/gcc-creative-studio`) with minimal merge conflicts:

1. **Custom Backend Namespace:** All custom APIs, services, and models MUST live strictly under `backend/src/custom/subtitles/`.
2. **Custom Frontend Namespace:** All custom UI elements MUST live under `frontend/src/app/custom/subtitles/`.
3. **Custom Tests:** Unit tests for custom modules live strictly in `backend/tests/custom/`.
4. **Core Code Preservation:** Never modify files outside the `/custom` namespaces unless registering minimal routing glue in `backend/main.py` or `frontend/src/app/app-routing.module.ts`.
5. **Zero-Collision CI/CD:** Upstream CI workflows (`backend-tests.yml`, `frontend-quality.yml`) remain 100% stock. Custom feature testing is managed independently in `.github/workflows/custom-suite.yml`.

## Deployment & Environments
Terraform configurations use an isolated modular architecture:
- `infra/environments/dev-infra-example/`: Default development blueprint template.
- `infra/environments/staging/`: Staging environment configuration.
- `infra/environments/prod/`: Production environment configuration (provisioned with `4000m` CPU and `8192Mi` memory for high-performance FFmpeg rendering).

To update Secret Manager secrets in any environment:
```bash
cd infra/environments/<environment>
./update_secrets.sh
```

## Quality Assurance & Verification
- **Run Custom Backend Tests:**
  ```bash
  cd backend && uv run pytest tests/custom -v --cov=src/custom --cov-fail-under=80
  ```
- **Run Full Backend Quality Suite:**
  ```bash
  cd backend && uv run pytest tests -v --cov=src --cov-fail-under=80
  ```

## Upstream Synchronization
- **Manual Sync CLI Helper:**
  ```bash
  ./scripts/sync_upstream.sh [upstream_branch] [target_branch]
  ```
- **Automated GitHub Action:** Scheduled weekly in `.github/workflows/upstream-sync.yml` to pull updates, verify the test suite, and open automated review PRs.
