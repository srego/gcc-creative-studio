#!/bin/bash
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

# ==============================================================================
# Upstream Synchronization Helper Script (Zero-Collision Strategy)
#
# Safely pulls updates from upstream gcc-creative-studio into a dedicated
# sync branch and runs local regression checks without modifying working state.
# ==============================================================================

set -e

C_RESET='\033[0m'
C_RED='\033[1;31m'
C_GREEN='\033[1;32m'
C_YELLOW='\033[1;33m'
C_BLUE='\033[1;34m'
C_CYAN='\033[1;36m'

info() { echo -e "${C_CYAN}➡️  $1${C_RESET}"; }
success() { echo -e "${C_GREEN}✅  $1${C_RESET}"; }
warn() { echo -e "${C_YELLOW}⚠️  $1${C_RESET}"; }
fail() { echo -e "${C_RED}❌  $1${C_RESET}" >&2; exit 1; }
step() { echo -e "\n${C_BLUE}--- $1 ---${C_RESET}"; }

UPSTREAM_URL="https://github.com/GoogleCloudPlatform/gcc-creative-studio.git"
UPSTREAM_BRANCH="${1:-main}"
BASE_BRANCH="${2:-develop}"
DATE_STAMP=$(date +%Y%m%d-%H%M%S)
SYNC_BRANCH="sync/upstream-${UPSTREAM_BRANCH}-${DATE_STAMP}"

step "1. Verifying Git Remotes"
if ! git remote get-url upstream >/dev/null 2>&1; then
    info "Adding remote 'upstream' -> ${UPSTREAM_URL}"
    git remote add upstream "$UPSTREAM_URL"
else
    info "Upstream remote found: $(git remote get-url upstream)"
fi

step "2. Fetching Latest Changes from Upstream"
info "Fetching upstream/${UPSTREAM_BRANCH}..."
git fetch upstream "$UPSTREAM_BRANCH"

step "3. Checking for Divergence"
MERGE_BASE=$(git merge-base "$BASE_BRANCH" "upstream/${UPSTREAM_BRANCH}" 2>/dev/null || echo "")
NEW_COMMITS_COUNT=$(git rev-list --count "${MERGE_BASE}..upstream/${UPSTREAM_BRANCH}" 2>/dev/null || echo "0")

if [ "$NEW_COMMITS_COUNT" -eq 0 ]; then
    success "Repository is already 100% up-to-date with upstream/${UPSTREAM_BRANCH}. No sync required!"
    exit 0
fi

info "Found ${NEW_COMMITS_COUNT} new commit(s) in upstream/${UPSTREAM_BRANCH}."

step "4. Creating Isolated Sync Branch: ${SYNC_BRANCH}"
CURRENT_BRANCH=$(git branch --show-current)
git checkout -b "$SYNC_BRANCH" "$BASE_BRANCH"

step "5. Attempting Safe 3-Way Merge"
if git merge --no-ff "upstream/${UPSTREAM_BRANCH}" -m "chore(sync): merge upstream/${UPSTREAM_BRANCH} into ${SYNC_BRANCH}"; then
    success "Clean merge achieved with ZERO conflicts!"
else
    warn "Automatic merge encountered conflicts in non-isolated files."
    warn "Please resolve conflicts manually, then run: git commit"
    exit 1
fi

step "6. Running Quality & Regression Verification"
info "Running backend custom unit tests..."
if (cd backend && uv run pytest tests/custom -v --cov=src/custom --cov-fail-under=80); then
    success "All backend custom tests passed with >= 80% coverage!"
else
    fail "Custom backend tests failed after merge. Please inspect changes."
fi

step "7. Summary & Next Steps"
success "Upstream sync branch created and verified: ${SYNC_BRANCH}"
echo -e "To push this sync branch and open a Pull Request:"
echo -e "   ${C_YELLOW}git push -u origin ${SYNC_BRANCH}${C_RESET}"
echo -e "To return to your previous branch (${CURRENT_BRANCH}):"
echo -e "   ${C_YELLOW}git checkout ${CURRENT_BRANCH}${C_RESET}\n"
