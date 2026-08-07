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
