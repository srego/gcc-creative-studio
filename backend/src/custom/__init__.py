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
"""Creative Studio Custom Module Shell.

Provides:
1. Auto-discovery and router mounting (`include_custom_routers(app)`) with
   router-level authentication guard enforcement.
2. Shared Vertex AI / GenAI client factory (`get_custom_genai_client(module_slug)`)
   aligned with upstream `GenAIModelSetup` (`location="global"`) and automatic
   `creative-studio/custom-<module_slug>` User-Agent telemetry attribution.
3. Resilient Vertex AI Gemini Flash model resolution (`get_default_flash_model()`,
   `get_flash_model_candidates()`, `record_working_flash_model()`) defaulting to
   `gemini-3.5-flash` (Google ADK's official `LlmAgent.DEFAULT_MODEL`, GA on
   Vertex AI `global` with `ALLOW_ALL`) backed by an ordered automatic fallback
   chain across live Vertex AI `global` publisher models.
"""

import importlib
import importlib.metadata
import logging
import os
import pkgutil
import threading
from typing import Dict, List

from fastapi import APIRouter, Depends, FastAPI
from google.genai import Client

from src.auth.auth_guard import RoleChecker
from src.config.config_service import config_service
from src.users.user_model import UserRoleEnum

logger = logging.getLogger(__name__)

try:
    VERSION = importlib.metadata.version("creative-studio")
except importlib.metadata.PackageNotFoundError:
    VERSION = "0.1.0"

DEFAULT_FLASH_MODEL = "gemini-3.5-flash"
FALLBACK_FLASH_MODELS = (
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-4-argon",
    "gemini-2.5-pro",
)

_custom_clients: Dict[str, Client] = {}
_clients_lock = threading.Lock()
_resolved_working_model: str | None = None


def get_default_flash_model() -> str:
    """Returns the configured or last-verified working Vertex AI Gemini Flash model."""
    env_override = os.environ.get("CUSTOM_FLASH_MODEL", "").strip()
    if env_override:
        return env_override
    if _resolved_working_model:
        return _resolved_working_model
    return DEFAULT_FLASH_MODEL


def record_working_flash_model(model_name: str) -> None:
    """Caches the first verified working Vertex AI model in-process to avoid repeat 404 probes."""
    global _resolved_working_model
    cleaned = (model_name or "").strip()
    if cleaned:
        _resolved_working_model = cleaned


def get_flash_model_candidates() -> List[str]:
    """Returns an ordered, deduplicated list of Vertex AI Gemini models to try."""
    primary = get_default_flash_model()
    candidates = [primary]
    for model in FALLBACK_FLASH_MODELS:
        if model not in candidates:
            candidates.append(model)
    return candidates


def get_custom_model_labels(module_slug: str = "custom") -> Dict[str, str]:
    """Returns standard Google Cloud Solutions attribution labels for a custom module."""
    clean_slug = module_slug.strip().lower().replace("_", "-") or "custom"
    return {
        "goog-solutions": "creative-studio-custom",
        "cs-custom-module": clean_slug,
    }


def get_custom_genai_client(
    module_slug: str = "custom",
    project_id: str | None = None,
    location: str = "global",
) -> Client:
    """Returns a cached Google GenAI client for a custom module on the global endpoint.

    Injects the `creative-studio/custom-<module_slug>/<version>` User-Agent header
    so custom module adoption is tracked in Creative Studio's existing telemetry.
    """
    clean_slug = module_slug.strip().lower().replace("_", "-") or "custom"
    resolved_project = (
        project_id
        or getattr(config_service, "PROJECT_ID", None)
        or os.environ.get("PROJECT_ID")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
    )
    cache_key = f"{clean_slug}:{resolved_project}:{location}"

    if cache_key not in _custom_clients:
        with _clients_lock:
            if cache_key not in _custom_clients:
                user_agent = (
                    f"creative-studio/custom-{clean_slug}/{VERSION} "
                    "(+https://github.com/GoogleCloudPlatform/gcc-creative-studio)"
                )
                _custom_clients[cache_key] = Client(
                    vertexai=getattr(config_service, "INIT_VERTEX", True),
                    project=resolved_project,
                    location=location,
                    http_options={"headers": {"user-agent": user_agent}},
                )
    return _custom_clients[cache_key]


def include_custom_routers(app: FastAPI) -> List[str]:
    """Auto-discovers and mounts all custom module routers under `src.custom.*`.

    Enforces router-level authentication (`RoleChecker([USER, ADMIN])`) on any
    custom router that does not already declare its own router-level dependencies
    (unless the module explicitly sets `PUBLIC_CUSTOM_ROUTER = True`).
    """
    mounted_modules: List[str] = []
    custom_pkg_dir = os.path.dirname(__file__)
    existing_prefixes = {
        getattr(r, "path", "") for r in getattr(app, "routes", [])
    }

    default_auth_dep = Depends(
        RoleChecker(allowed_roles=[UserRoleEnum.USER, UserRoleEnum.ADMIN])
    )

    for finder, subpkg_name, is_pkg in sorted(
        pkgutil.iter_modules([custom_pkg_dir]), key=lambda x: x[1]
    ):
        if not is_pkg or subpkg_name.startswith("_"):
            continue

        subpkg_path = os.path.join(custom_pkg_dir, subpkg_name)
        candidate_files = ["router"]
        for _, mod_name, mod_is_pkg in sorted(
            pkgutil.iter_modules([subpkg_path]), key=lambda x: x[1]
        ):
            if not mod_is_pkg and (
                mod_name.endswith("_controller") or mod_name == "controller"
            ):
                if mod_name not in candidate_files:
                    candidate_files.append(mod_name)

        for mod_file in candidate_files:
            full_module_name = f"src.custom.{subpkg_name}.{mod_file}"
            try:
                mod = importlib.import_module(full_module_name)
            except Exception as exc:
                logger.warning(
                    "Skipping custom module %s due to import error: %s",
                    full_module_name,
                    exc,
                )
                continue

            router_obj = getattr(mod, "router", None)
            if not isinstance(router_obj, APIRouter):
                continue

            sample_route_paths = {
                f"{router_obj.prefix}{getattr(rt, 'path', '')}"
                for rt in router_obj.routes
            }
            if sample_route_paths and sample_route_paths.issubset(
                existing_prefixes
            ):
                mounted_modules.append(subpkg_name)
                break

            is_public = bool(getattr(mod, "PUBLIC_CUSTOM_ROUTER", False))
            has_own_deps = bool(getattr(router_obj, "dependencies", None))
            extra_deps = (
                [] if (is_public or has_own_deps) else [default_auth_dep]
            )

            app.include_router(router_obj, dependencies=extra_deps)
            for p in sample_route_paths:
                existing_prefixes.add(p)

            logger.info(
                "Mounted custom module '%s' (%s, prefix='%s')",
                subpkg_name,
                full_module_name,
                router_obj.prefix,
            )
            mounted_modules.append(subpkg_name)
            break

    return mounted_modules
