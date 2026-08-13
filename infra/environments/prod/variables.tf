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

variable "gcp_project_id" {
  type        = string
  description = "The GCP Project ID for the production environment."
}

variable "gcp_region" {
  type        = string
  description = "The GCP region for the production environment. Defaults to us-central1."
  default     = "us-central1"
}

variable "environment" {
  type        = string
  description = "The name of the environment, e.g., 'production'."
  default     = "production"
}

# --- Service Names ---
variable "backend_service_name" {
  type        = string
  description = "The full name of the backend Cloud Run service for this environment."
}

variable "frontend_service_name" {
  type        = string
  description = "The full name of the frontend Cloud Run/Firebase service for this environment."
}

variable "firebase_site_id" {
  type        = string
  description = "The site ID for the Firebase Hosting site. Must be unique across all Firebase projects."
  default     = ""
}

# --- GitHub Repo Details ---
variable "github_conn_name" {
  type        = string
  description = "The name of the Cloud Build GitHub connection."
}

variable "github_repo_owner" {
  type        = string
  description = "The owner of the GitHub repository."
}

variable "github_repo_name" {
  type        = string
  description = "The name of the GitHub repository."
}

variable "github_branch_name" {
  type        = string
  description = "The branch name to trigger builds from (e.g. main)."
}

# --- Resource Sizing ---
variable "be_cpu" {
  type        = string
  description = "CPU allocation for the backend container in production."
  default     = "4000m"
}

variable "be_memory" {
  type        = string
  description = "Memory allocation for the backend container in production."
  default     = "8192Mi"
}

variable "fe_cpu" {
  type        = string
  description = "CPU allocation for the frontend container."
  default     = "2000m"
}

variable "fe_memory" {
  type        = string
  description = "Memory allocation for the frontend container."
  default     = "2048Mi"
}

# --- Custom Audiences ---
variable "backend_custom_audiences" {
  type        = list(string)
  description = "List of custom audiences for the backend service."
}

variable "frontend_custom_audiences" {
  type        = list(string)
  description = "List of custom audiences for the frontend service."
}

# --- Service-Specific Environment Variables ---
variable "be_env_vars" {
  type        = map(map(string))
  description = "A map containing common and environment-specific variables for the backend."
}

variable "be_build_substitutions" {
  type        = map(string)
  description = "A map of substitution variables for the backend Cloud Build trigger."
  default     = {}
}

variable "fe_build_substitutions" {
  type        = map(string)
  description = "A map of substitution variables for the frontend Cloud Build trigger."
  default     = {}
}

variable "frontend_secrets" {
  type        = list(string)
  description = "A list of secret names required by the frontend build."
  default     = []
}

variable "backend_secrets" {
  type        = list(string)
  description = "A list of secret names required by the backend build."
  default     = []
}

variable "backend_runtime_secrets" {
  type        = map(string)
  description = "Secrets to mount in the backend container at runtime."
  default     = {}
}

# --- List of APIs to enable ---
variable "apis_to_enable" {
  type        = list(string)
  description = "A list of Google Cloud APIs to enable on the project."
  default = [
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "cloudfunctions.googleapis.com",
    "iamcredentials.googleapis.com",
    "aiplatform.googleapis.com",
    "firestore.googleapis.com",
    "texttospeech.googleapis.com",
    "speech.googleapis.com",
    "workflows.googleapis.com",
  ]
}
