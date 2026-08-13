gcp_project_id = "YOUR_GCP_PROJECT_ID"
gcp_region     = "us-central1"
environment    = "staging"

# --- Service Names ---
backend_service_name  = "cstudio-backend-staging"
frontend_service_name = "cstudio-frontend-staging"
firebase_site_id      = "YOUR_FIREBASE_SITE_ID" # (Optional) Custom Firebase Hosting Site ID, defaults to gcp_project_id

# --- GitHub Repo Details ---
github_conn_name   = "gh-repo-owner-con"
github_repo_owner  = "RepoOwnerName"
github_repo_name   = "repo-owner-gcc-creative-studio"
github_branch_name = "develop"

# --- Sizing & Performance for Media Workloads ---
be_cpu    = "2000m"
be_memory = "4096Mi"
fe_cpu    = "2000m"
fe_memory = "2048Mi"

# --- Custom Audiences ---
backend_custom_audiences  = ["YOUR_OAUTH_WEB_CLIENT_ID_HERE", "YOUR_GCP_PROJECT_ID"]
frontend_custom_audiences = ["YOUR_OAUTH_WEB_CLIENT_ID_HERE", "YOUR_GCP_PROJECT_ID"]

# --- Service-Specific Environment Variables ---
be_env_vars = {
  common = {
    LOG_LEVEL = "INFO"
  }
  staging = {
    ENVIRONMENT                    = "staging"
    GOOGLE_TOKEN_AUDIENCE          = "YOUR_OAUTH_WEB_CLIENT_ID_HERE"
    IDENTITY_PLATFORM_ALLOWED_ORGS = "" # If empty then any org is allowed
  }
}

fe_build_substitutions = {
  _ANGULAR_BUILD_COMMAND = "build-dev"
}

frontend_secrets = [
  "FIREBASE_API_KEY",
  "FIREBASE_AUTH_DOMAIN",
  "FIREBASE_PROJECT_ID",
  "FIREBASE_STORAGE_BUCKET",
  "FIREBASE_MESSAGING_SENDER_ID",
  "FIREBASE_APP_ID",
  "FIREBASE_MEASUREMENT_ID",
  "GOOGLE_CLIENT_ID",
]

backend_secrets = [
  "GOOGLE_TOKEN_AUDIENCE",
]

backend_runtime_secrets = {
  "GOOGLE_TOKEN_AUDIENCE" = "GOOGLE_TOKEN_AUDIENCE"
}

apis_to_enable = [
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
