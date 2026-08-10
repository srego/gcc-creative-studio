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

import os
import re
import shutil
import tempfile

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import FileResponse
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
                if "youtube.com" in video_source or "youtu.be" in video_source:
                    try:
                        target_video_path = (
                            subtitle_service.engine.download_youtube_audio(
                                video_source, job_dir
                            )
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

    elif "multipart/form-data" in content_type:
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
            with open(upload_path, "wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)
            target_video_path = upload_path

        video_url = form.get("video_url") or form.get("video_uri")
        if video_url and not target_video_path:
            if "youtube.com" in str(video_url) or "youtu.be" in str(video_url):
                try:
                    target_video_path = (
                        subtitle_service.engine.download_youtube_audio(
                            str(video_url), job_dir
                        )
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to download YouTube audio: {str(e)}",
                    ) from e
            else:
                target_video_path = str(video_url)

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
        res_dto = subtitle_service.process_job(
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
def download_output_file(
    job_id: str,
    file_type: str = "vtt",
) -> FileResponse:
    """Streams or downloads the specified generated artifact for a job."""
    status_dto = subtitle_service.get_job_status(job_id)
    if not status_dto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found.",
        )

    if file_type in ("zip", "all"):
        zip_file = subtitle_service.create_job_zip_package(job_id)
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

    if not file_path or not os.path.exists(file_path):
        resolved_file = subtitle_service.get_artifact_file(job_id, file_type)
        if resolved_file and os.path.exists(resolved_file):
            file_path = resolved_file
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Requested file type '{file_type}' is not available for job {job_id}.",
            )

    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
