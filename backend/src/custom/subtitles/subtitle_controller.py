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

"""FastAPI router controller for custom subtitle processing endpoints."""

import asyncio
import logging
import os
import re
import shutil
import tempfile
from urllib.parse import urlparse

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.auth_guard import RoleChecker, get_current_user
from src.custom.subtitles.subtitle_dto import (
    SaveToGalleryRequestDTO,
    SaveToGalleryResponseDTO,
    SubtitleRequestDTO,
    SubtitleResponseDTO,
    SubtitleUploadUrlRequestDTO,
    SubtitleUploadUrlResponseDTO,
)
from src.custom.subtitles.subtitle_service import subtitle_service
from src.database import get_db
from src.users.user_model import UserModel, UserRoleEnum

logger = logging.getLogger(__name__)


def is_valid_youtube_url(url: str) -> bool:
    """Strictly validates if a URL belongs to legitimate YouTube domains."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        return hostname in (
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
            "www.youtu.be",
        )
    except Exception:
        return False


router = APIRouter(
    prefix="/api/v1/custom/subtitles",
    tags=["Custom Subtitles"],
    dependencies=[
        Depends(
            RoleChecker(allowed_roles=[UserRoleEnum.USER, UserRoleEnum.ADMIN])
        )
    ],
)


@router.post(
    "/generate-upload-url",
    response_model=SubtitleUploadUrlResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Get Signed URL for Direct Video Upload",
)
async def generate_upload_url(
    request_dto: SubtitleUploadUrlRequestDTO,
) -> SubtitleUploadUrlResponseDTO:
    """Generates a secure GCS v4 presigned URL to upload video files directly to Cloud Storage."""
    try:
        signed_url, gcs_uri = subtitle_service.generate_signed_upload_url(
            filename=request_dto.filename,
            content_type=request_dto.content_type,
        )
        return SubtitleUploadUrlResponseDTO(
            upload_url=signed_url,
            gcs_uri=gcs_uri,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to generate upload URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate upload URL: {str(exc)}",
        ) from exc


@router.post(
    "/generate",
    response_model=SubtitleResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Generate Subtitles and Subtitled Videos",
    description=(
        "Processes input video/audio (via JSON body, file upload, or YouTube URL). "
        "Transcribes using STT v2 chirp_3, refines formatting with Gemini, and "
        "generates WebVTT/SRT sidecars and MP4 videos."
    ),
)
async def generate_subtitles(
    request: Request,
    background_tasks: BackgroundTasks,
    sync: bool = False,
) -> SubtitleResponseDTO:
    """Endpoint for generating subtitles and subtitle-embedded videos."""
    job_id = subtitle_service.create_job()
    target_video_path = ""
    req_lang = "en-US"
    req_format = "vtt"
    req_burn = False
    pkg_name = None

    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            body = await request.json()
            request_dto = SubtitleRequestDTO(**body)
            req_lang = request_dto.language_code
            req_format = request_dto.output_format
            req_burn = request_dto.burn_subtitles
            pkg_name = request_dto.package_name
            video_source = request_dto.video_url or request_dto.video_uri
            job_dir = subtitle_service.resolve_output_dir(
                package_name=pkg_name, job_id=job_id
            )

            if video_source:
                if is_valid_youtube_url(video_source):
                    try:
                        target_video_path = await asyncio.to_thread(
                            subtitle_service.engine.download_youtube_audio,
                            video_source,
                            job_dir,
                        )
                    except Exception as e:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Failed to download YouTube audio: {str(e)}",
                        ) from e
                else:
                    target_video_path = video_source
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON request body: {str(e)}",
            ) from e

    elif (
        "multipart/form-data" in content_type
        or "application/x-www-form-urlencoded" in content_type
    ):
        form = await request.form()
        pkg_name = (
            str(form.get("package_name")) if form.get("package_name") else None
        )
        job_dir = subtitle_service.resolve_output_dir(
            package_name=pkg_name, job_id=job_id
        )

        uploaded_file = form.get("file")
        if (
            uploaded_file
            and hasattr(uploaded_file, "filename")
            and uploaded_file.filename
        ):
            safe_basename = os.path.basename(uploaded_file.filename)
            safe_filename = (
                re.sub(r"[^a-zA-Z0-9_\-\.]", "_", safe_basename)
                or "source_video.mp4"
            )
            upload_path = os.path.join(job_dir, safe_filename)
            file_bytes = await uploaded_file.read()
            with open(upload_path, "wb") as buffer:
                buffer.write(file_bytes)
            target_video_path = upload_path

        video_url = form.get("video_url") or form.get("video_uri")
        if video_url and not target_video_path:
            video_url_str = str(video_url)
            if is_valid_youtube_url(video_url_str):
                try:
                    target_video_path = await asyncio.to_thread(
                        subtitle_service.engine.download_youtube_audio,
                        video_url_str,
                        job_dir,
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to download YouTube audio: {str(e)}",
                    ) from e
            else:
                target_video_path = video_url_str

        req_lang = str(form.get("language_code", "en-US"))
        req_format = str(form.get("output_format", "vtt"))
        burn_val = form.get("burn_subtitles")
        if burn_val is not None:
            req_burn = str(burn_val).lower() in ["true", "1", "yes"]
    else:
        job_dir = subtitle_service.resolve_output_dir(
            package_name=None, job_id=job_id
        )

    if not target_video_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either video_url/video_uri or file upload must be provided.",
        )

    if sync:
        res_dto = await asyncio.to_thread(
            subtitle_service.process_job,
            job_id=job_id,
            video_path=target_video_path,
            burn_subtitles=req_burn,
            output_format=req_format,
            language_code=req_lang,
            package_name=pkg_name,
            job_dir=job_dir,
        )

        if res_dto.status == "failed":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=res_dto.error_message or "Subtitle generation failed.",
            )

        return res_dto

    background_tasks.add_task(
        subtitle_service.process_job,
        job_id=job_id,
        video_path=target_video_path,
        burn_subtitles=req_burn,
        output_format=req_format,
        language_code=req_lang,
        package_name=pkg_name,
        job_dir=job_dir,
    )

    return SubtitleResponseDTO(
        job_id=job_id,
        status="processing",
        step="extracting",
        progress=10,
        local_output_dir=os.path.abspath(job_dir),
    )


@router.get(
    "/status/{job_id}",
    response_model=SubtitleResponseDTO,
    summary="Track Subtitle Job Status",
)
def get_job_status(job_id: str) -> SubtitleResponseDTO:
    """Retrieve current processing status for a subtitle job."""
    status_dto = subtitle_service.get_job_status(job_id)
    if not status_dto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        )
    return status_dto


@router.get(
    "/download/{job_id}",
    summary="Download Generated Subtitle or Video File",
)
async def download_output_file(
    job_id: str,
    file_type: str = "vtt",
) -> Response:
    """Streams or downloads the specified generated artifact for a job."""
    try:
        status_dto = subtitle_service.get_job_status(job_id)
        if not status_dto:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found.",
            )

        if file_type in ("zip", "all"):
            signed_zip = subtitle_service.get_artifact_signed_url(
                job_id, "zip", for_download=True
            )
            if signed_zip:
                return RedirectResponse(
                    url=signed_zip,
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                )

            zip_file = await asyncio.to_thread(
                subtitle_service.create_job_zip_package, job_id
            )
            if not zip_file or not os.path.exists(zip_file):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Unable to construct ZIP package for job {job_id}.",
                )
            filename = f"subtitles_{job_id[:8]}_package.zip"
            return FileResponse(
                path=zip_file,
                media_type="application/zip",
                filename=filename,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                },
            )

        # 1. Try V4 Presigned URL directly from Cloud Storage (Range requests, high-speed streaming)
        signed_url = subtitle_service.get_artifact_signed_url(
            job_id, file_type, for_download=True
        )
        if signed_url:
            return RedirectResponse(
                url=signed_url,
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )

        # 2. Local fallback for local development and test suites
        file_path = None
        media_type = "text/vtt"

        if file_type == "vtt":
            file_path = status_dto.subtitles_vtt
            media_type = "text/vtt"
        elif file_type == "srt":
            file_path = status_dto.subtitles_srt
            media_type = "application/x-subrip"
        elif file_type == "burned_in_video":
            file_path = status_dto.burned_in_video
            media_type = "video/mp4"
        elif file_type == "toggleable_video":
            file_path = status_dto.default_toggleable_video
            media_type = "video/mp4"
        elif file_type == "source_video":
            file_path = status_dto.source_video_path
            media_type = "video/mp4"

        if not file_path or not os.path.exists(file_path):
            resolved_file = subtitle_service.get_artifact_file(
                job_id, file_type
            )
            if resolved_file and os.path.exists(resolved_file):
                file_path = resolved_file
            elif file_type == "burned_in_video":
                # Gracefully fallback to toggleable or source video if burned video is not present
                for alt_type in ("toggleable_video", "source_video"):
                    alt_signed = subtitle_service.get_artifact_signed_url(
                        job_id, alt_type, for_download=True
                    )
                    if alt_signed:
                        return RedirectResponse(
                            url=alt_signed,
                            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                        )
                    alt_file = subtitle_service.get_artifact_file(
                        job_id, alt_type
                    )
                    if alt_file and os.path.exists(alt_file):
                        file_path = alt_file
                        break

            if not file_path or not os.path.exists(file_path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Requested file type '{file_type}' is not available for job {job_id}.",
                )

        filename = os.path.basename(file_path)
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=filename,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error processing download for job {job_id} ({file_type}): {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process download request: {str(e)}",
        )


@router.post(
    "/save-to-gallery",
    response_model=SaveToGalleryResponseDTO,
    summary="Save Subtitle Job Outputs to Media Gallery",
)
async def save_to_media_gallery(
    request_dto: SaveToGalleryRequestDTO,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SaveToGalleryResponseDTO:
    """Registers the complete subtitle package folder into the PostgreSQL database as SourceAssets."""
    target_workspace_id = (
        request_dto.workspace_id
        if request_dto.workspace_id
        else (current_user.default_workspace_id or 1)
    )
    (
        media_item_id,
        pkg_name,
        primary_video_gcs,
        thumbnail_gcs,
        items_count,
        saved_files,
    ) = await subtitle_service.save_job_to_gallery(
        job_id=request_dto.job_id,
        workspace_id=target_workspace_id,
        user_id=current_user.id,
        user_email=current_user.email,
        db=db,
        title=request_dto.title,
    )
    return SaveToGalleryResponseDTO(
        success=True,
        asset_id=media_item_id,
        asset_name=pkg_name,
        gcs_uri=primary_video_gcs,
        thumbnail_uri=thumbnail_gcs,
        saved_items_count=items_count,
        saved_filenames=saved_files,
        message=f"Successfully saved {pkg_name} to Media Gallery with {items_count} attached deliverables.",
    )
