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

"""DTO schemas for the custom subtitle processing service."""

from typing import Optional
from pydantic import BaseModel, Field


class SubtitleRequestDTO(BaseModel):
    """Request model for subtitle generation."""

    video_url: Optional[str] = Field(
        default=None,
        description="URL (HTTP/YouTube) or GCS URI (gs://...) of the source video/audio.",
    )
    video_uri: Optional[str] = Field(
        default=None,
        description="Alternative field for local file path or GCS URI.",
    )
    language_code: str = Field(
        default="en-US",
        description="BCP-47 language code for Speech-to-Text transcription.",
    )
    output_format: str = Field(
        default="vtt",
        description="Subtitle file format: 'vtt' or 'srt'.",
    )
    burn_subtitles: bool = Field(
        default=False,
        description="Whether to generate hardburned video track.",
    )
    package_name: Optional[str] = Field(
        default=None,
        description="Custom package / folder name to organize outputs in output_subtitles/.",
    )


class SubtitleResponseDTO(BaseModel):
    """Response model for subtitle generation and status tracking."""

    job_id: str = Field(description="Unique job tracking identifier.")
    status: str = Field(
        description="Processing status: pending, processing, completed, failed."
    )
    subtitle_url: Optional[str] = Field(
        default=None,
        description="URL/Path to the primary generated subtitle file.",
    )
    processed_video_url: Optional[str] = Field(
        default=None,
        description="URL/Path to the subtitled video output.",
    )
    transcript_text: Optional[str] = Field(
        default=None,
        description="Full extracted transcript text.",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error details if processing failed.",
    )
    default_toggleable_video: Optional[str] = Field(
        default=None,
        description="Path or URL to video with soft toggleable subtitles.",
    )
    burned_in_video: Optional[str] = Field(
        default=None,
        description="Path or URL to video with hardburned subtitles.",
    )
    subtitles_vtt: Optional[str] = Field(
        default=None,
        description="Path or URL to WebVTT sidecar file.",
    )
    subtitles_srt: Optional[str] = Field(
        default=None,
        description="Path or URL to SubRip SRT sidecar file.",
    )
    segment_count: Optional[int] = Field(
        default=0,
        description="Total count of subtitle segments.",
    )
    local_output_dir: Optional[str] = Field(
        default=None,
        description="Local directory path where deliverables are saved.",
    )
    step: Optional[str] = Field(
        default="idle",
        description="Current detailed stage: idle, uploading, extracting, transcribing, formatting, packaging, completed, failed.",
    )
    progress: Optional[int] = Field(
        default=0,
        description="Estimated completion percentage (0-100).",
    )
    operation_name: Optional[str] = Field(
        default=None,
        description="GCP Speech-to-Text LRO operation resource name.",
    )
    source_video_path: Optional[str] = Field(
        default=None,
        description="Path or URI to source video being processed.",
    )
    burn_subtitles: Optional[bool] = Field(
        default=False,
        description="Whether burned-in video was requested for this job.",
    )
    language_code: Optional[str] = Field(
        default="en-US",
        description="Language code used for transcription.",
    )


class SubtitleUploadUrlRequestDTO(BaseModel):
    """Request model for acquiring a GCS presigned upload URL."""

    filename: str = Field(
        description="Original name of the video file to be uploaded.",
    )
    content_type: str = Field(
        default="video/mp4",
        description="MIME content type of the video file.",
    )
    size: Optional[int] = Field(
        default=None,
        description="Approximate file size in bytes.",
    )


class SubtitleUploadUrlResponseDTO(BaseModel):
    """Response model with the GCS presigned upload URL and target GCS URI."""

    upload_url: str = Field(
        description="V4 presigned PUT URL for direct client-side GCS upload.",
    )
    gcs_uri: str = Field(
        description="Final Cloud Storage URI (gs://bucket/object) of the uploaded file.",
    )


class SaveToGalleryRequestDTO(BaseModel):
    """Request model for persisting subtitle package deliverables to the Media Gallery."""

    job_id: str = Field(
        description="ID of the completed subtitle generation job."
    )
    workspace_id: Optional[int] = Field(
        default=None,
        description="Target workspace ID for saving the asset.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Optional title override for the saved media item.",
    )


class SaveToGalleryResponseDTO(BaseModel):
    """Response model indicating successful persistence into the Media Gallery."""

    success: bool = Field(
        description="Whether the asset was saved successfully."
    )
    asset_id: Optional[int] = Field(
        default=None,
        description="Database ID of the created MediaItem.",
    )
    asset_name: str = Field(description="Name of the saved creation.")
    gcs_uri: str = Field(description="Primary GCS URI of the saved creation.")
    thumbnail_uri: Optional[str] = Field(
        default=None, description="GCS URI of the video thumbnail."
    )
    saved_items_count: int = Field(
        default=1, description="Total number of deliverables attached."
    )
    saved_filenames: list[str] = Field(
        default_factory=list,
        description="List of all attached deliverable filenames.",
    )
    message: str = Field(description="Informative message.")
