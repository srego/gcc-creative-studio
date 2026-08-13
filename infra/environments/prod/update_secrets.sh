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

# A script to securely update secrets in Google Secret Manager
# for the Production environment.

set -e
set -o pipefail

C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_CYAN='\033[0;36m'

info() { echo -e "${C_CYAN}> $1${C_RESET}"; }
success() { echo -e "${C_GREEN}✅  $1${C_RESET}"; }
warn() { echo -e "${C_YELLOW}⚠️  $1${C_RESET}"; }
fail() { echo -e "${C_RED}❌  $1${C_RESET}" >&2; exit 1; }

info "Checking for required tools (gcloud, jq, terraform)..."
command -v gcloud >/dev/null || fail "gcloud CLI not found. Please install it."
command -v jq >/dev/null || fail "jq is not installed. Please install it."
command -v terraform >/dev/null || fail "Terraform not found. Please install it."
command -v firebase >/dev/null || fail "Firebase CLI not found. Please install it."
info "All tools found."

configure_firebase_site_id() {
  info "Checking Firebase Hosting Site configuration..."
  local tfvars_file=$1
  local project_id=$2

  if grep -q "YOUR_FIREBASE_SITE_ID" "$tfvars_file"; then
    warn "Placeholder 'YOUR_FIREBASE_SITE_ID' found in ${tfvars_file}."
    local default_site_name
    default_site_name=$(firebase hosting:sites:list --project "$project_id" --json | jq -r 'first(.result.sites[] | select(.type == "DEFAULT_SITE") | .name) // first(.result.sites[].name) // ""')
    local site_id_to_use=$project_id
    [ -n "$default_site_name" ] && site_id_to_use=$(basename "$default_site_name")
    info "Setting 'firebase_site_id' to '${C_YELLOW}${site_id_to_use}${C_RESET}' in ${tfvars_file}."
    sed -i.bak "s/YOUR_FIREBASE_SITE_ID/${site_id_to_use}/" "$tfvars_file" && rm "${tfvars_file}.bak"
  fi
}

TFVARS_FILE=$(find . -maxdepth 1 -name "*.tfvars" ! -name "terraform.tfvars.dist" | head -n 1)
if [ -z "$TFVARS_FILE" ]; then
  fail "No .tfvars file found in the current directory. Cannot proceed."
fi
info "Using variables from: ${C_YELLOW}${TFVARS_FILE}${C_RESET}"

TERRAFORM_OUTPUTS=$(terraform output -json)
PROJECT_ID=$(echo "$TERRAFORM_OUTPUTS" | jq -r .gcp_project_id.value)
FRONTEND_SECRETS=$(echo "$TERRAFORM_OUTPUTS" | jq -r .frontend_secrets.value[])
BACKEND_SECRETS=$(echo "$TERRAFORM_OUTPUTS" | jq -r .backend_secrets.value[])

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "null" ]; then
  fail "Could not find 'gcp_project_id' in Terraform outputs. Did you run 'terraform apply'?"
fi

configure_firebase_site_id "$TFVARS_FILE" "$PROJECT_ID"

ALL_SECRETS=$(echo "${FRONTEND_SECRETS} ${BACKEND_SECRETS}" | tr ' ' '\n' | sort -u | grep .)
if [ -z "$ALL_SECRETS" ]; then
  success "No secrets listed. Nothing to do."
  exit 0
fi

info "Project: ${C_YELLOW}${PROJECT_ID}${C_RESET}"
warn "The following secrets will be updated: \n${C_YELLOW}$ALL_SECRETS${C_RESET}"

read -p "Continue? (y/n): " -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  fail "Operation cancelled."
fi

FIREBASE_SITE_ID=$(grep 'firebase_site_id' "$TFVARS_FILE" | awk -F'"' '{print $2}')
WEB_APP_ID=$(firebase apps:list --project="$PROJECT_ID" --json 2>/dev/null | jq -r --arg name "$FIREBASE_SITE_ID" '.result[]? | select(.displayName == $name) | .appId' || echo "")

if [ -n "$WEB_APP_ID" ]; then
  WEB_APP_CONFIG_RAW=$(firebase apps:sdkconfig WEB "$WEB_APP_ID" --project="$PROJECT_ID" --json 2>/dev/null)
  WEB_APP_SDK_CONFIG=$(echo "$WEB_APP_CONFIG_RAW" | jq -r '.result.sdkConfig')
fi

if [ -n "$WEB_APP_SDK_CONFIG" ]; then
  success "Found Firebase Web App config."
  AUTO_FIREBASE_API_KEY=$(echo "$WEB_APP_SDK_CONFIG" | jq -r .apiKey)
  AUTO_FIREBASE_AUTH_DOMAIN=$(echo "$WEB_APP_SDK_CONFIG" | jq -r .authDomain)
  AUTO_FIREBASE_STORAGE_BUCKET=$(echo "$WEB_APP_SDK_CONFIG" | jq -r .storageBucket)
  AUTO_FIREBASE_MESSAGING_SENDER_ID=$(echo "$WEB_APP_SDK_CONFIG" | jq -r .messagingSenderId)
  AUTO_FIREBASE_APP_ID=$(echo "$WEB_APP_SDK_CONFIG" | jq -r .appId)
  AUTO_FIREBASE_MEASUREMENT_ID=$(echo "$WEB_APP_SDK_CONFIG" | jq -r .measurementId)
  AUTO_OAUTH_CLIENT_ID=$(echo "$WEB_APP_SDK_CONFIG" | jq -r .oauthClientId)
fi

for SECRET_NAME in $ALL_SECRETS; do
  info "Updating secret: ${C_YELLOW}${SECRET_NAME}${C_RESET}"
  SECRET_VALUE=""
  AUTO_DISCOVERED=false

  case $SECRET_NAME in
    "FIREBASE_API_KEY")           SECRET_VALUE=$AUTO_FIREBASE_API_KEY; AUTO_DISCOVERED=true ;;
    "FIREBASE_AUTH_DOMAIN")       SECRET_VALUE=$AUTO_FIREBASE_AUTH_DOMAIN; AUTO_DISCOVERED=true ;;
    "FIREBASE_PROJECT_ID")        SECRET_VALUE=$PROJECT_ID; AUTO_DISCOVERED=true ;;
    "FIREBASE_STORAGE_BUCKET")    SECRET_VALUE=$AUTO_FIREBASE_STORAGE_BUCKET; AUTO_DISCOVERED=true ;;
    "FIREBASE_MESSAGING_SENDER_ID") SECRET_VALUE=$AUTO_FIREBASE_MESSAGING_SENDER_ID; AUTO_DISCOVERED=true ;;
    "FIREBASE_APP_ID")            SECRET_VALUE=$AUTO_FIREBASE_APP_ID; AUTO_DISCOVERED=true ;;
    "FIREBASE_MEASUREMENT_ID")    SECRET_VALUE=$AUTO_FIREBASE_MEASUREMENT_ID; AUTO_DISCOVERED=true ;;
    "GOOGLE_CLIENT_ID")           SECRET_VALUE=$AUTO_OAUTH_CLIENT_ID; AUTO_DISCOVERED=true ;;
    "GOOGLE_TOKEN_AUDIENCE")      SECRET_VALUE=$AUTO_OAUTH_CLIENT_ID; AUTO_DISCOVERED=true ;;
  esac

  if [ "$AUTO_DISCOVERED" = true ] && [ -n "$SECRET_VALUE" ] && [ "$SECRET_VALUE" != "null" ]; then
    info "  Auto-populating from Firebase config."
  elif [ "$SECRET_NAME" == "GOOGLE_CLIENT_ID" ] || [ "$SECRET_NAME" == "GOOGLE_TOKEN_AUDIENCE" ]; then
    read -s -p "  Enter OAuth Client ID: " SECRET_VALUE
    echo
  else
    read -s -p "  Enter new value: " SECRET_VALUE
    echo
  fi

  if [ -z "$SECRET_VALUE" ]; then
    if [ "$SECRET_NAME" == "FIREBASE_MEASUREMENT_ID" ]; then
      SECRET_VALUE=""
    else
      warn "  Skipping ${SECRET_NAME}."
      continue
    fi
  fi

  LATEST_VERSION=$(gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$PROJECT_ID" 2>/dev/null || echo "")
  if [ "$LATEST_VERSION" == "$SECRET_VALUE" ]; then
    success "  Secret ${SECRET_NAME} is up-to-date."
  else
    echo -n "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_NAME" \
      --data-file="-" \
      --project="$PROJECT_ID" \
      --quiet
    success "  Updated ${SECRET_NAME}."
  fi
done

success "All production secrets updated."
