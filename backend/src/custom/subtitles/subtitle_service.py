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

"""Subtitle processing engine service wrapping GCP STT v2, Gemini, and FFmpeg."""

import concurrent.futures
import datetime
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
import zipfile
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import HTTPException, status
from google import genai
from google.api_core.client_options import ClientOptions
from google.cloud import speech_v2, storage
from google.cloud.speech_v2.types import cloud_speech
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.base_dto import AspectRatioEnum, MimeTypeEnum
from src.common.schema.media_item_model import JobStatusEnum, MediaItem
from src.config.config_service import config_service
from src.custom.subtitles.subtitle_dto import SubtitleResponseDTO
from src.source_assets.schema.source_asset_model import (
    AssetScopeEnum,
    AssetTypeEnum,
    SourceAsset,
)

logger = logging.getLogger(__name__)


class PodcastSubtitleEngine:
    """Podcast Subtitle Engine powered by GCP STT v2 (chirp_3), Gemini, and FFmpeg."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        region: str = "us",
        gcs_bucket_name: Optional[str] = None,
    ):
        self.project_id = (
            project_id
            or getattr(config_service, "PROJECT_ID", None)
            or "creative-studio-delta"
        )
        self.region = region
        self.gcs_bucket_name = (
            gcs_bucket_name
            or getattr(config_service, "GENMEDIA_BUCKET", None)
            or "creative-studio-delta-cs-development-bucket"
        )

        credentials = self._get_credentials()

        try:
            self.speech_client = speech_v2.SpeechClient(
                credentials=credentials,
                client_options=ClientOptions(
                    api_endpoint=f"{self.region}-speech.googleapis.com"
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to initialize STT v2 client: {e}")
            self.speech_client = None

        try:
            if credentials:
                self.storage_client = storage.Client(
                    project=self.project_id, credentials=credentials
                )
            else:
                self.storage_client = storage.Client(project=self.project_id)
        except Exception:
            try:
                self.storage_client = storage.Client(project=self.project_id)
            except Exception as e:
                logger.warning(f"Failed to initialize Storage client: {e}")
                self.storage_client = None

        try:
            self.genai_client = genai.Client(
                vertexai=True, project=self.project_id, location="us-central1"
            )
        except Exception:
            try:
                self.genai_client = genai.Client()
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                self.genai_client = None

    def _get_credentials(self) -> Any:
        """Fetch valid Application Default Credentials."""
        try:
            import google.auth

            creds, _ = google.auth.default()
            return creds
        except Exception as e:
            logger.debug(f"Could not load application default credentials: {e}")
            return None

    def download_youtube_audio(self, youtube_url: str, target_dir: str) -> str:
        """Downloads audio track from YouTube URL using yt-dlp."""
        os.makedirs(target_dir, exist_ok=True)
        output_template = os.path.join(target_dir, "yt_download.%(ext)s")
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format",
            "mp3",
            "-o",
            output_template,
            youtube_url,
        ]
        logger.info(f"Downloading YouTube audio from {youtube_url}...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"yt-dlp download failed: {res.stderr}")

        downloaded_file = os.path.join(target_dir, "yt_download.mp3")
        if not os.path.exists(downloaded_file):
            for f in os.listdir(target_dir):
                if f.startswith("yt_download"):
                    downloaded_file = os.path.join(target_dir, f)
                    break
        return downloaded_file

    def parse_speech_response(
        self, response: cloud_speech.BatchRecognizeResponse
    ) -> Dict[str, Any]:
        """Parses speech recognition results into word-level timestamps and transcript."""
        words_data: List[Dict[str, Any]] = []
        full_transcript_parts: List[str] = []

        if not response or not hasattr(response, "results"):
            return {"full_text": "", "words": []}

        for _, file_res in response.results.items():
            err_code = getattr(getattr(file_res, "error", None), "code", 0)
            if isinstance(err_code, int) and err_code != 0:
                raise RuntimeError(
                    f"Speech-to-Text v2 error ({err_code}): {getattr(file_res.error, 'message', '')}"
                )
            if not hasattr(file_res, "transcript") or not file_res.transcript:
                continue
            for result in file_res.transcript.results:
                if not result.alternatives:
                    continue
                alt = result.alternatives[0]
                full_transcript_parts.append(alt.transcript)
                for w in alt.words:
                    start_sec = (
                        w.start_offset.total_seconds()
                        if hasattr(w.start_offset, "total_seconds")
                        else (
                            w.start_offset.seconds + w.start_offset.nanos / 1e9
                        )
                    )
                    end_sec = (
                        w.end_offset.total_seconds()
                        if hasattr(w.end_offset, "total_seconds")
                        else (w.end_offset.seconds + w.end_offset.nanos / 1e9)
                    )
                    speaker_tag = (
                        str(w.speaker_label)
                        if hasattr(w, "speaker_label") and w.speaker_label
                        else "1"
                    )
                    words_data.append(
                        {
                            "word": w.word,
                            "start_time": round(start_sec, 3),
                            "end_time": round(end_sec, 3),
                            "speaker": f"Speaker {speaker_tag}",
                        }
                    )

        return {
            "full_text": " ".join(full_transcript_parts),
            "words": words_data,
        }

    def transcribe_chirp3(
        self,
        audio_path_or_gcs_uri: str,
        language_code: str = "en-US",
        on_operation_started: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Transcribe audio using Speech-to-Text v2 chirp_3 model with diarization."""
        gcs_uri = audio_path_or_gcs_uri
        temp_wav_path = None
        staged_blob = None

        if not audio_path_or_gcs_uri.startswith("gs://"):
            if not os.path.exists(audio_path_or_gcs_uri):
                raise FileNotFoundError(
                    f"Audio file not found: {audio_path_or_gcs_uri}"
                )

            temp_wav_path = f"{audio_path_or_gcs_uri}.stt_tmp.wav"
            logger.info(
                f"Extracting 16kHz mono audio from {audio_path_or_gcs_uri}..."
            )
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                audio_path_or_gcs_uri,
                "-f",
                "wav",
                "-ar",
                "16000",
                "-ac",
                "1",
                temp_wav_path,
            ]
            subprocess.run(cmd, capture_output=True, check=True, timeout=300)

            staged_blob = None
            if self.storage_client:
                bucket = self.storage_client.bucket(self.gcs_bucket_name)
                filename = os.path.basename(temp_wav_path)
                blob_name = f"staging/{int(time.time())}_{filename}"
                staged_blob = bucket.blob(blob_name)
                logger.info(
                    f"Staging audio to GCS bucket gs://{self.gcs_bucket_name}/{blob_name}..."
                )
                staged_blob.upload_from_filename(temp_wav_path)
                gcs_uri = f"gs://{self.gcs_bucket_name}/{blob_name}"

        try:
            logger.info(f"Running STT v2 chirp_3 on {gcs_uri}...")

            if self.speech_client:
                config = cloud_speech.RecognitionConfig(
                    auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                    language_codes=[language_code],
                    model="chirp_3",
                    features=cloud_speech.RecognitionFeatures(
                        enable_word_time_offsets=True,
                        diarization_config=cloud_speech.SpeakerDiarizationConfig(
                            min_speaker_count=1,
                            max_speaker_count=4,
                        ),
                    ),
                )

                file_metadata = cloud_speech.BatchRecognizeFileMetadata(
                    uri=gcs_uri
                )
                inline_output_config = cloud_speech.InlineOutputConfig()

                request = cloud_speech.BatchRecognizeRequest(
                    recognizer=f"projects/{self.project_id}/locations/{self.region}/recognizers/_",
                    config=config,
                    files=[file_metadata],
                    recognition_output_config=cloud_speech.RecognitionOutputConfig(
                        inline_response_config=inline_output_config
                    ),
                )

                operation = self.speech_client.batch_recognize(request=request)
                if hasattr(operation, "operation") and hasattr(
                    operation.operation, "name"
                ):
                    op_name = operation.operation.name
                    logger.info("Chirp 3 BatchRecognize LRO: %s", op_name)
                    if on_operation_started:
                        on_operation_started(op_name)

                start_wait = time.time()
                while not operation.done():
                    time.sleep(1.5)
                    if time.time() - start_wait > 600:
                        raise TimeoutError(
                            "Speech-to-Text v2 batch operation timed out after 10 minutes."
                        )

                response = operation.result()
                return self.parse_speech_response(response)

            return {"full_text": "", "words": []}
        finally:
            if temp_wav_path and os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except Exception:
                    pass
            if staged_blob:
                try:
                    staged_blob.delete()
                except Exception:
                    pass

    def _refine_chunk_gemini(
        self, chunk_words: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Refines a single chunk of words with Gemini."""
        if not chunk_words:
            return []

        prompt = f"""
You are an expert subtitle editor.
Given a list of words with word-level start_time, end_time, and speaker tags, group them into clean subtitle segments.

STRICT CONSTRAINTS:
1. Maximum 42 characters per line (<= 42 chars/line).
2. Segment start_time MUST be start_time of its first word; end_time MUST be end_time of its last word.
3. Fix capitalization and punctuation naturally.
4. Return ONLY a valid JSON list of objects with fields:
   - "speaker": string
   - "start_time": float
   - "end_time": float
   - "text": string

Word timing data:
{json.dumps(chunk_words, separators=(',', ':'))}
"""
        candidate_models = ["gemini-2.5-flash", "gemini-1.5-flash"]
        raw_response_text = ""

        if self.genai_client:
            for model in candidate_models:
                try:
                    config_kwargs: Dict[str, Any] = {
                        "response_mime_type": "application/json"
                    }
                    if "2.5" in model or "thinking" in model:
                        config_kwargs["thinking_config"] = types.ThinkingConfig(
                            thinking_budget=0
                        )
                    res = self.genai_client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(**config_kwargs),
                    )
                    raw_response_text = res.text.strip()
                    break
                except Exception as e:
                    logger.warning(
                        f"Gemini chunk refinement with '{model}' failed: {e}"
                    )
                    continue

        if not raw_response_text:
            return self._fallback_rule_based_segmenter(chunk_words)

        try:
            segments = json.loads(raw_response_text)
            if isinstance(segments, list):
                return segments
        except Exception:
            pass

        return self._fallback_rule_based_segmenter(chunk_words)

    def refine_gemini36(
        self, raw_transcript_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Refines raw transcript words using parallel chunked Gemini calls."""
        words_data = raw_transcript_data.get("words", [])
        if not words_data:
            return []

        chunk_size = 75
        if len(words_data) <= chunk_size:
            segments = self._refine_chunk_gemini(words_data)
        else:
            chunks = [
                words_data[i : i + chunk_size]
                for i in range(0, len(words_data), chunk_size)
            ]
            logger.info(
                f"Refining {len(words_data)} words across {len(chunks)} parallel chunks..."
            )
            segments = []
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(len(chunks), 4)
            ) as executor:
                results = list(executor.map(self._refine_chunk_gemini, chunks))
                for chunk_segs in results:
                    segments.extend(chunk_segs)

        return self._enforce_max_char_limit(segments, max_chars=42)

    def _enforce_max_char_limit(
        self, segments: List[Dict[str, Any]], max_chars: int = 42
    ) -> List[Dict[str, Any]]:
        """Splits long subtitle segments to guarantee <= max_chars per line."""
        refined = []
        for seg in segments:
            text = seg.get("text", "").strip()
            if len(text) <= max_chars:
                refined.append(seg)
                continue

            words = text.split()
            speaker = seg.get("speaker", "Speaker 1")
            total_start = seg.get("start_time", 0.0)
            total_end = seg.get("end_time", 0.0)
            total_duration = max(total_end - total_start, 0.1)

            sub_lines = []
            curr_words: List[str] = []
            curr_len = 0
            for w in words:
                word_len = len(w) + (1 if curr_words else 0)
                if curr_len + word_len <= max_chars:
                    curr_words.append(w)
                    curr_len += word_len
                else:
                    if curr_words:
                        sub_lines.append(" ".join(curr_words))
                    curr_words = [w]
                    curr_len = len(w)
            if curr_words:
                sub_lines.append(" ".join(curr_words))

            total_chars = sum(len(sl) for sl in sub_lines) or 1
            curr_time = total_start
            for sl in sub_lines:
                frac = len(sl) / total_chars
                line_duration = frac * total_duration
                line_end = round(curr_time + line_duration, 3)
                refined.append(
                    {
                        "speaker": speaker,
                        "start_time": round(curr_time, 3),
                        "end_time": line_end,
                        "text": sl,
                    }
                )
                curr_time = line_end

        return refined

    def _fallback_rule_based_segmenter(
        self, words_data: List[Dict[str, Any]], max_chars: int = 42
    ) -> List[Dict[str, Any]]:
        """Rule-based fallback segmentation when LLM refinement is unavailable."""
        segments: List[Dict[str, Any]] = []
        if not words_data:
            return segments

        curr_words: List[str] = []
        curr_len = 0
        curr_speaker = words_data[0].get("speaker", "Speaker 1")
        start_time = words_data[0].get("start_time", 0.0)

        for item in words_data:
            w = item["word"]
            word_len = len(w) + (1 if curr_words else 0)
            if (
                curr_len + word_len <= max_chars
                and item.get("speaker") == curr_speaker
            ):
                curr_words.append(w)
                curr_len += word_len
            else:
                if curr_words:
                    end_time = item["start_time"]
                    segments.append(
                        {
                            "speaker": curr_speaker,
                            "start_time": start_time,
                            "end_time": end_time,
                            "text": " ".join(curr_words),
                        }
                    )
                curr_words = [w]
                curr_len = len(w)
                curr_speaker = item.get("speaker", "Speaker 1")
                start_time = item["start_time"]

        if curr_words and words_data:
            segments.append(
                {
                    "speaker": curr_speaker,
                    "start_time": start_time,
                    "end_time": words_data[-1]["end_time"],
                    "text": " ".join(curr_words),
                }
            )

        return segments

    def export_vtt_srt(
        self, subtitle_data: List[Dict[str, Any]], vtt_path: str, srt_path: str
    ) -> Dict[str, str]:
        """Export subtitle data to WebVTT (.vtt) and SubRip SRT (.srt) files."""
        vtt_lines = ["WEBVTT\n"]
        srt_lines = []

        valid_idx = 1
        for seg in subtitle_data:
            start_sec = float(
                seg.get("start_time")
                if seg.get("start_time") is not None
                else seg.get("startTime") or 0.0
            )
            end_sec = float(
                seg.get("end_time")
                if seg.get("end_time") is not None
                else seg.get("endTime") or (start_sec + 1.0)
            )
            text = str(seg.get("text", "")).strip()
            if not text:
                continue

            start_vtt = self._format_vtt_timestamp(start_sec)
            end_vtt = self._format_vtt_timestamp(end_sec)
            vtt_lines.append(
                f"{valid_idx}\n{start_vtt} --> {end_vtt}\n{text}\n"
            )

            start_srt = self._format_srt_timestamp(start_sec)
            end_srt = self._format_srt_timestamp(end_sec)
            srt_lines.append(
                f"{valid_idx}\n{start_srt} --> {end_srt}\n{text}\n"
            )
            valid_idx += 1

        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(vtt_lines))

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))

        return {"vtt": vtt_path, "srt": srt_path}

    def burn_subtitles_ffmpeg(
        self, video_path: str, subtitle_path: str, output_video_path: str
    ) -> str:
        """Hardburn subtitles into MP4 using FFmpeg CLI."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Input video file not found: {video_path}")
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

        escaped_sub_path = (
            subtitle_path.replace("\\", "/")
            .replace(":", "\\:")
            .replace("'", "'\\''")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )
        filter_str = f"subtitles='{escaped_sub_path}'"
        temp_output_path = output_video_path + ".tmp.mp4"

        cmd = [
            "ffmpeg",
            "-y",
            "-threads",
            "0",
            "-i",
            video_path,
            "-vf",
            filter_str,
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-level",
            "4.0",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            temp_output_path,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
            raise RuntimeError(f"FFmpeg subtitle burning failed: {res.stderr}")

        os.replace(temp_output_path, output_video_path)
        return output_video_path

    def embed_soft_subtitles_ffmpeg(
        self, video_path: str, subtitle_path: str, output_video_path: str
    ) -> str:
        """Embed soft toggleable subtitles into MP4 container using FFmpeg."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Input video file not found: {video_path}")
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

        temp_output_path = output_video_path + ".tmp.mp4"

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-i",
            subtitle_path,
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
            "-movflags",
            "+faststart",
            temp_output_path,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
            raise RuntimeError(
                f"FFmpeg soft subtitle embedding failed: {res.stderr}"
            )

        os.replace(temp_output_path, output_video_path)
        return output_video_path

    def process_video(
        self,
        video_path: str,
        job_dir: Optional[str] = None,
        generate_burned_in: bool = True,
        language_code: str = "en-US",
        progress_callback: Optional[Callable[[str, int], None]] = None,
        on_operation_started: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Runs complete subtitle extraction, refinement, and rendering pipeline."""
        if not job_dir:
            job_dir = (
                os.path.dirname(video_path)
                if not video_path.startswith("gs://")
                else "/tmp/output_subtitles"
            )
        os.makedirs(job_dir, exist_ok=True)

        if video_path.startswith("gs://"):
            if progress_callback:
                progress_callback("extracting", 10)
            parts = video_path.replace("gs://", "").split("/", 1)
            bucket_name = parts[0]
            blob_name = parts[1] if len(parts) > 1 else "source_video.mp4"
            local_video_name = (
                re.sub(r"[^a-zA-Z0-9_\-\.]", "_", os.path.basename(blob_name))
                or "source_video.mp4"
            )
            local_video_path = os.path.join(job_dir, local_video_name)
            logger.info(
                "Downloading source video from %s to %s",
                video_path,
                local_video_path,
            )
            blob = self.storage_client.bucket(bucket_name).blob(blob_name)
            blob.download_to_filename(local_video_path)
            video_path = local_video_path

        if not os.path.exists(video_path):
            raise FileNotFoundError(
                f"Source video file not found: {video_path}"
            )

        if progress_callback:
            progress_callback("extracting", 15)

        if progress_callback:
            progress_callback("transcribing", 35)

        raw_asr = self.transcribe_chirp3(
            video_path,
            language_code=language_code,
            on_operation_started=on_operation_started,
        )

        return self.finalize_downstream(
            raw_asr=raw_asr,
            video_path=video_path,
            job_dir=job_dir,
            generate_burned_in=generate_burned_in,
            progress_callback=progress_callback,
        )

    def finalize_downstream(
        self,
        raw_asr: Dict[str, Any],
        video_path: str,
        job_dir: str,
        generate_burned_in: bool = True,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> Dict[str, Any]:
        """Runs Gemini refinement, formatting, subtitle export, and video packaging."""
        vtt_path = os.path.join(job_dir, "subtitles.vtt")
        srt_path = os.path.join(job_dir, "subtitles.srt")
        toggleable_video_path = os.path.join(job_dir, "output_toggleable.mp4")
        burned_in_video_path = (
            os.path.join(job_dir, "output_burned_in.mp4")
            if generate_burned_in
            else None
        )

        if progress_callback:
            progress_callback("formatting", 65)

        refined_subtitles = self.refine_gemini36(raw_asr)
        self.export_vtt_srt(refined_subtitles, vtt_path, srt_path)

        if progress_callback:
            progress_callback("packaging", 85)

        self.embed_soft_subtitles_ffmpeg(
            video_path, vtt_path, toggleable_video_path
        )

        # Save word-level transcript metadata
        transcript_json_path = os.path.join(job_dir, "transcript.json")
        try:
            with open(transcript_json_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "full_text": raw_asr.get("full_text", ""),
                        "segments": refined_subtitles,
                        "words": raw_asr.get("words", []),
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.warning(f"Could not write transcript.json: {e}")

        if generate_burned_in and burned_in_video_path:
            self.burn_subtitles_ffmpeg(
                video_path, vtt_path, burned_in_video_path
            )

        # Extract a preview thumbnail frame
        thumbnail_path = os.path.join(job_dir, "thumbnail.jpg")
        preview_video = (
            burned_in_video_path
            if (generate_burned_in and os.path.exists(burned_in_video_path))
            else video_path
        )
        self.generate_thumbnail(preview_video, thumbnail_path)

        if progress_callback:
            progress_callback("completed", 100)

        return {
            "job_dir": job_dir,
            "source_video": video_path,
            "default_toggleable_video": toggleable_video_path,
            "burned_in_video": burned_in_video_path,
            "subtitles_vtt": vtt_path,
            "subtitles_srt": srt_path,
            "thumbnail_jpg": thumbnail_path,
            "transcript_json": transcript_json_path,
            "segment_count": len(refined_subtitles),
            "transcript_text": raw_asr.get("full_text", ""),
        }

    def generate_thumbnail(
        self, video_path: str, thumbnail_path: str
    ) -> Optional[str]:
        """Extracts a crisp frame from the video at 1.0s to serve as a preview thumbnail."""
        if not video_path or not os.path.exists(video_path):
            return None
        try:
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                video_path,
                "-vframes",
                "1",
                "-q:v",
                "2",
                thumbnail_path,
            ]
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            if (
                os.path.exists(thumbnail_path)
                and os.path.getsize(thumbnail_path) > 0
            ):
                return thumbnail_path
            # Fallback to 0.1s
            cmd[3] = "00:00:00.100"
            subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=10
            )
            if (
                os.path.exists(thumbnail_path)
                and os.path.getsize(thumbnail_path) > 0
            ):
                return thumbnail_path
        except Exception as e:
            logger.warning(f"Could not generate video thumbnail: {e}")
        return None

    @staticmethod
    def _format_vtt_timestamp(seconds: float) -> str:
        total_ms = int(round(seconds * 1000))
        ms = total_ms % 1000
        total_sec = total_ms // 1000
        hrs = total_sec // 3600
        mins = (total_sec % 3600) // 60
        secs = total_sec % 60
        return f"{hrs:02d}:{mins:02d}:{secs:02d}.{ms:03d}"

    @staticmethod
    def _format_srt_timestamp(seconds: float) -> str:
        total_ms = int(round(seconds * 1000))
        ms = total_ms % 1000
        total_sec = total_ms // 1000
        hrs = total_sec // 3600
        mins = (total_sec % 3600) // 60
        secs = total_sec % 60
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


class SubtitleService:
    """Service wrapper for managing async subtitle jobs."""

    def __init__(self) -> None:
        self.engine = PodcastSubtitleEngine()
        self.jobs: Dict[str, SubtitleResponseDTO] = {}
        self._active_finishing_jobs: Set[str] = set()

    def _save_job_state(
        self, job_id: str, job_dto: SubtitleResponseDTO
    ) -> None:
        """Persists job state to memory cache, local /tmp, and Google Cloud Storage."""
        self.jobs[job_id] = job_dto

        # 1. Local disk cache
        try:
            local_jobs_dir = "/tmp/subtitles_jobs"
            os.makedirs(local_jobs_dir, exist_ok=True)
            local_file = os.path.join(local_jobs_dir, f"{job_id}.json")
            with open(local_file, "w", encoding="utf-8") as f:
                f.write(job_dto.model_dump_json())
        except Exception as e:
            logger.debug(f"Local job cache write failed: {e}")

        # 2. Google Cloud Storage persistence
        try:
            if self.engine.storage_client:
                bucket_name = (
                    getattr(config_service, "GENMEDIA_BUCKET", None)
                    or os.getenv("GENMEDIA_BUCKET")
                    or "creative-studio-delta-cs-development-bucket"
                )
                bucket = self.engine.storage_client.bucket(bucket_name)
                blob = bucket.blob(f"subtitles_jobs/{job_id}.json")
                blob.upload_from_string(
                    job_dto.model_dump_json(),
                    content_type="application/json",
                )
        except Exception as e:
            logger.debug(f"GCS job state write skipped/failed: {e}")

    def _read_job_from_gcs(self, job_id: str) -> Optional[SubtitleResponseDTO]:
        """Reads job state JSON directly from Cloud Storage."""
        try:
            if not self.engine.storage_client:
                return None
            bucket_name = (
                getattr(config_service, "GENMEDIA_BUCKET", None)
                or os.getenv("GENMEDIA_BUCKET")
                or "creative-studio-delta-cs-development-bucket"
            )
            bucket = self.engine.storage_client.bucket(bucket_name)
            blob = bucket.blob(f"subtitles_jobs/{job_id}.json")
            if blob.exists():
                content = blob.download_as_text()
                data = json.loads(content)
                return SubtitleResponseDTO(**data)
        except Exception as e:
            logger.debug(f"GCS job state read skipped/failed: {e}")
        return None

    def _load_job_state(self, job_id: str) -> Optional[SubtitleResponseDTO]:
        """Loads job state from memory, local disk, or GCS across Cloud Run instances."""
        # Check memory first
        if job_id in self.jobs:
            job = self.jobs[job_id]
            if job.status in ("completed", "failed"):
                return job
            # If still pending/processing, check if GCS has a completed/newer version
            gcs_job = self._read_job_from_gcs(job_id)
            if gcs_job:
                self.jobs[job_id] = gcs_job
                return gcs_job
            return job

        # Check local disk
        try:
            local_file = os.path.join("/tmp/subtitles_jobs", f"{job_id}.json")
            if os.path.exists(local_file):
                with open(local_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    dto = SubtitleResponseDTO(**data)
                    self.jobs[job_id] = dto
                    return dto
        except Exception as e:
            logger.debug(f"Local job cache read failed: {e}")

        # Check Cloud Storage
        gcs_job = self._read_job_from_gcs(job_id)
        if gcs_job:
            self.jobs[job_id] = gcs_job
            return gcs_job

        return None

    def create_job(self) -> str:
        """Create a new tracked subtitle job."""
        if len(self.jobs) >= 100:
            oldest_job = next(iter(self.jobs))
            del self.jobs[oldest_job]

        job_id = f"sub_{uuid.uuid4().hex[:12]}"
        dto = SubtitleResponseDTO(
            job_id=job_id,
            status="pending",
            step="idle",
            progress=0,
        )
        self._save_job_state(job_id, dto)
        return job_id

    def _finish_job_from_asr(
        self, job_id: str, job: SubtitleResponseDTO, raw_asr: Dict[str, Any]
    ) -> SubtitleResponseDTO:
        """Finishes downstream pipeline when LRO completes across instances."""
        try:
            job_dir = job.local_output_dir or self.resolve_output_dir(
                job_id=job_id
            )
            os.makedirs(job_dir, exist_ok=True)

            video_path = job.source_video_path or ""
            if video_path.startswith("gs://"):
                local_source = os.path.join(job_dir, "source_video.mp4")
                if not os.path.exists(local_source):
                    parts = video_path.replace("gs://", "").split("/", 1)
                    bucket_name = parts[0]
                    blob_name = (
                        parts[1] if len(parts) > 1 else "source_video.mp4"
                    )
                    if self.engine.storage_client:
                        blob = self.engine.storage_client.bucket(
                            bucket_name
                        ).blob(blob_name)
                        blob.download_to_filename(local_source)
                video_path = local_source
            elif not os.path.exists(video_path):
                resolved = self.get_artifact_file(job_id, "source_video")
                if resolved and os.path.exists(resolved):
                    video_path = resolved
                else:
                    raise FileNotFoundError(
                        f"Source video for job {job_id} could not be retrieved from GCS or local disk."
                    )

            def update_progress(step: str, prog: int) -> None:
                job.step = step
                job.progress = prog
                self._save_job_state(job_id, job)

            result = self.engine.finalize_downstream(
                raw_asr=raw_asr,
                video_path=video_path,
                job_dir=job_dir,
                generate_burned_in=bool(job.burn_subtitles),
                progress_callback=update_progress,
            )

            job.status = "completed"
            job.step = "completed"
            job.progress = 100
            job.subtitles_vtt = result.get("subtitles_vtt")
            job.subtitles_srt = result.get("subtitles_srt")
            job.default_toggleable_video = result.get(
                "default_toggleable_video"
            )
            job.burned_in_video = result.get("burned_in_video")
            job.segment_count = result.get("segment_count", 0)
            job.transcript_text = result.get("transcript_text", "")
            job.local_output_dir = os.path.abspath(job_dir)
            job.subtitle_url = result.get("subtitles_vtt")
            job.processed_video_url = (
                result.get("burned_in_video")
                if job.burn_subtitles
                else result.get("default_toggleable_video")
            )

            # Persist output files to GCS
            self._upload_artifact_to_gcs(job_id, job.subtitles_vtt)
            self._upload_artifact_to_gcs(job_id, job.subtitles_srt)
            self._upload_artifact_to_gcs(job_id, job.default_toggleable_video)
            self._upload_artifact_to_gcs(job_id, job.burned_in_video)
            self._upload_artifact_to_gcs(job_id, result.get("thumbnail_jpg"))

        except Exception as e:
            logger.error(
                "Failed to finalize job %s from ASR: %s",
                job_id,
                e,
                exc_info=True,
            )
            job.status = "failed"
            job.step = "failed"
            job.error_message = str(e)

        self._save_job_state(job_id, job)
        return job

    def _run_async_finish(
        self, job_id: str, job: SubtitleResponseDTO, raw_asr: Dict[str, Any]
    ) -> None:
        """Executes downstream formatting, burning, and packaging in a background thread."""
        try:
            self._finish_job_from_asr(job_id, job, raw_asr)
        except Exception as e:
            logger.error(
                "Background finish failed for job %s: %s",
                job_id,
                e,
                exc_info=True,
            )
            job.status = "failed"
            job.step = "failed"
            job.error_message = str(e)
            self._save_job_state(job_id, job)
        finally:
            self._active_finishing_jobs.discard(job_id)

    def get_job_status(self, job_id: str) -> Optional[SubtitleResponseDTO]:
        """Retrieve job status DTO, checking active LRO if transcribing."""
        job = self._load_job_state(job_id)
        if not job:
            return None

        # Check if active Speech-to-Text LRO has finished on GCP
        if (
            job.status == "processing"
            and job.step == "transcribing"
            and job.operation_name
        ):
            if self.engine.speech_client and getattr(
                self.engine.speech_client, "operations_client", None
            ):
                try:
                    op_proto = self.engine.speech_client.operations_client.get_operation(
                        name=job.operation_name
                    )
                    if op_proto.done:
                        if op_proto.HasField("error"):
                            job.status = "failed"
                            job.step = "failed"
                            job.error_message = f"Speech-to-Text v2 error: {op_proto.error.message}"
                            self._save_job_state(job_id, job)
                            return job

                        resp = cloud_speech.BatchRecognizeResponse()
                        op_proto.response.Unpack(resp)
                        raw_asr = self.engine.parse_speech_response(resp)

                        if job_id not in self._active_finishing_jobs:
                            self._active_finishing_jobs.add(job_id)
                            job.step = "formatting"
                            job.progress = 65
                            self._save_job_state(job_id, job)
                            thread = threading.Thread(
                                target=self._run_async_finish,
                                args=(job_id, job, raw_asr),
                                daemon=True,
                            )
                            thread.start()
                except Exception as e:
                    logger.debug("LRO check for %s skipped: %s", job_id, e)

        # Recovery for jobs that were interrupted or timed out at formatting/packaging
        elif (
            job.status == "processing"
            and job.step in ("formatting", "packaging")
            and job.operation_name
            and job_id not in self._active_finishing_jobs
        ):
            if self.engine.speech_client and getattr(
                self.engine.speech_client, "operations_client", None
            ):
                try:
                    op_proto = self.engine.speech_client.operations_client.get_operation(
                        name=job.operation_name
                    )
                    if op_proto.done and not op_proto.HasField("error"):
                        resp = cloud_speech.BatchRecognizeResponse()
                        op_proto.response.Unpack(resp)
                        raw_asr = self.engine.parse_speech_response(resp)
                        self._active_finishing_jobs.add(job_id)
                        thread = threading.Thread(
                            target=self._run_async_finish,
                            args=(job_id, job, raw_asr),
                            daemon=True,
                        )
                        thread.start()
                except Exception as e:
                    logger.debug("Recovery check for %s skipped: %s", job_id, e)

        return job

    def resolve_output_dir(
        self, package_name: Optional[str] = None, job_id: str = ""
    ) -> str:
        """Resolves target local workspace directory for storing deliverables."""
        configured_dir = getattr(
            config_service, "SUBTITLES_OUTPUT_DIR", None
        ) or os.getenv("SUBTITLES_OUTPUT_DIR")
        if configured_dir:
            base_dir = os.path.abspath(configured_dir)
        elif os.path.exists("/app"):
            base_dir = "/app/output_subtitles"
        else:
            curr = os.path.abspath(__file__)
            for _ in range(5):
                curr = os.path.dirname(curr)
                if (
                    os.path.exists(os.path.join(curr, ".git"))
                    or os.path.basename(curr)
                    == "diligent-podcast-transcription"
                ):
                    base_dir = os.path.join(curr, "output_subtitles")
                    break
            else:
                base_dir = os.path.abspath("./output_subtitles")

        if package_name and package_name.strip():
            clean_name = re.sub(r"[^a-zA-Z0-9_\- ]", "", package_name).strip()
            folder_name = clean_name or f"job_{job_id}"
        else:
            folder_name = f"job_{job_id}_{int(time.time())}"

        candidate_dir = os.path.join(base_dir, folder_name)
        if os.path.exists(candidate_dir) and any(
            os.path.isfile(os.path.join(candidate_dir, f))
            for f in os.listdir(candidate_dir)
        ):
            version = 2
            while True:
                versioned_dir = os.path.join(
                    base_dir, f"{folder_name}_v{version}"
                )
                if not os.path.exists(versioned_dir) or not any(
                    os.path.isfile(os.path.join(versioned_dir, f))
                    for f in os.listdir(versioned_dir)
                ):
                    candidate_dir = versioned_dir
                    break
                version += 1

        try:
            os.makedirs(candidate_dir, exist_ok=True)
            try:
                os.chmod(candidate_dir, 0o777)
            except Exception:
                pass
        except Exception:
            base_dir = "/tmp/output_subtitles"
            candidate_dir = os.path.join(base_dir, folder_name)
            os.makedirs(candidate_dir, exist_ok=True)

        return candidate_dir

    def generate_signed_upload_url(
        self,
        filename: str,
        content_type: str = "video/mp4",
        bucket_name: Optional[str] = None,
    ) -> tuple[str, str]:
        """Generates a secure GCS presigned upload URL for direct video uploads."""
        bucket = (
            bucket_name
            or getattr(config_service, "GENMEDIA_BUCKET", None)
            or os.getenv("GENMEDIA_BUCKET")
            or "creative-studio-delta-cs-development-bucket"
        )
        file_uuid = uuid.uuid4().hex[:12]
        safe_name = (
            re.sub(r"[^a-zA-Z0-9_\-\.]", "_", os.path.basename(filename))
            or "video.mp4"
        )
        destination_blob_name = f"subtitles_inputs/{file_uuid}/{safe_name}"
        gcs_uri = f"gs://{bucket}/{destination_blob_name}"

        try:
            from src.auth.iam_signer_credentials_service import (  # pylint: disable=import-outside-toplevel
                IamSignerCredentials,
            )

            signer = IamSignerCredentials()
            signed_url, returned_gcs_uri = signer.generate_v4_upload_signed_url(
                destination_blob_name=destination_blob_name,
                content_type=content_type,
                bucket_name=bucket,
                expiration_hours=2,
            )
            if signed_url:
                return signed_url, (returned_gcs_uri or gcs_uri)
        except Exception as e:
            logger.warning("IamSigner upload URL generation fallback: %s", e)

        # Direct Client fallback
        try:
            blob = self.engine.storage_client.bucket(bucket).blob(
                destination_blob_name
            )
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=2),
                method="PUT",
                content_type=content_type,
            )
            return signed_url, gcs_uri
        except Exception as exc:
            logger.error("Failed to generate direct GCS upload URL: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not generate Cloud Storage upload URL: {str(exc)}",
            ) from exc

    def _upload_artifact_to_gcs(
        self,
        job_id: str,
        local_path: Optional[str],
        target_filename: Optional[str] = None,
    ) -> Optional[str]:
        """Uploads a generated output file to Cloud Storage for persistent multi-instance availability."""
        if not local_path or not os.path.exists(local_path):
            return None
        try:
            if not self.engine.storage_client:
                return None
            bucket_name = (
                getattr(config_service, "GENMEDIA_BUCKET", None)
                or os.getenv("GENMEDIA_BUCKET")
                or "creative-studio-delta-cs-development-bucket"
            )
            bucket = self.engine.storage_client.bucket(bucket_name)
            filename = target_filename or os.path.basename(local_path)
            blob_name = f"subtitles_outputs/{job_id}/{filename}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(local_path)
            return f"gs://{bucket_name}/{blob_name}"
        except Exception as e:
            logger.debug(f"Failed to upload artifact {local_path} to GCS: {e}")
            return None

    def get_artifact_file(self, job_id: str, file_type: str) -> Optional[str]:
        """Resolves local path for an artifact, downloading from GCS if on another instance."""
        status_dto = self.get_job_status(job_id)
        if not status_dto:
            return None

        file_path = None
        if file_type == "vtt":
            file_path = status_dto.subtitles_vtt
        elif file_type == "srt":
            file_path = status_dto.subtitles_srt
        elif file_type in ("toggleable_video", "toggleable"):
            file_path = status_dto.default_toggleable_video
        elif file_type in ("burned_in_video", "burned"):
            file_path = status_dto.burned_in_video
        elif file_type in ("source_video", "source"):
            file_path = status_dto.source_video_path

        if file_path and os.path.exists(file_path):
            return file_path

        # Attempt to retrieve from GCS
        try:
            if not self.engine.storage_client:
                return None
            bucket_name = (
                getattr(config_service, "GENMEDIA_BUCKET", None)
                or os.getenv("GENMEDIA_BUCKET")
                or self.engine.gcs_bucket_name
            )
            bucket = self.engine.storage_client.bucket(bucket_name)
            blobs = list(
                bucket.list_blobs(prefix=f"subtitles_outputs/{job_id}/")
            )
            if not blobs:
                blobs = list(
                    bucket.list_blobs(prefix=f"subtitles_packages/{job_id}/")
                )
            for blob in blobs:
                filename = os.path.basename(blob.name)
                matched = False
                if file_type == "vtt" and filename.endswith(".vtt"):
                    matched = True
                elif file_type == "srt" and filename.endswith(".srt"):
                    matched = True
                elif (
                    file_type in ("burned_in_video", "burned")
                    and ("burned" in filename or "subtitled" in filename)
                    and filename.endswith(".mp4")
                ):
                    matched = True
                elif (
                    file_type in ("toggleable_video", "toggleable")
                    and ("toggleable" in filename or "default" in filename)
                    and filename.endswith(".mp4")
                ):
                    matched = True
                elif (
                    file_type in ("source_video", "source")
                    and ("source" in filename or filename == "source_video.mp4")
                    and filename.endswith(".mp4")
                ):
                    matched = True
                elif file_type in ("video", "any_video") and filename.endswith(
                    ".mp4"
                ):
                    matched = True
                elif file_type in ("thumbnail", "thumbnail_jpg") and (
                    filename.endswith(".jpg") or filename.endswith(".png")
                ):
                    matched = True

                if matched:
                    dest_dir = f"/tmp/subtitles_outputs/{job_id}"
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, filename)
                    if not os.path.exists(dest_path):
                        blob.download_to_filename(dest_path)
                    return dest_path
        except Exception as e:
            logger.warning(f"Failed to retrieve artifact from GCS: {e}")

        return None

    def process_job(
        self,
        job_id: str,
        video_path: str,
        burn_subtitles: bool = False,
        output_format: str = "vtt",
        language_code: str = "en-US",
        package_name: Optional[str] = None,
        job_dir: Optional[str] = None,
    ) -> SubtitleResponseDTO:
        """Process a subtitle job and update tracking state."""
        job = self._load_job_state(job_id)
        if not job:
            job = SubtitleResponseDTO(
                job_id=job_id, status="pending", step="idle", progress=0
            )

        # Stage local source video to GCS immediately for multi-instance durability
        if not video_path.startswith("gs://") and os.path.exists(video_path):
            staged_gcs = self._upload_artifact_to_gcs(
                job_id, video_path, target_filename="source_video.mp4"
            )
            job.source_video_path = staged_gcs or video_path
        else:
            job.source_video_path = video_path

        job.status = "processing"
        job.step = "extracting"
        job.progress = 10
        job.burn_subtitles = burn_subtitles
        job.language_code = language_code
        self._save_job_state(job_id, job)

        if not job_dir:
            job_dir = self.resolve_output_dir(
                package_name=package_name, job_id=job_id
            )

        def update_progress(step: str, prog: int) -> None:
            job.step = step
            job.progress = prog
            self._save_job_state(job_id, job)

        def on_op_started(op_name: str) -> None:
            job.operation_name = op_name
            job.step = "transcribing"
            job.progress = 35
            self._save_job_state(job_id, job)

        try:
            result = self.engine.process_video(
                video_path=video_path,
                job_dir=job_dir,
                generate_burned_in=burn_subtitles,
                language_code=language_code,
                progress_callback=update_progress,
                on_operation_started=on_op_started,
            )

            job.status = "completed"
            job.step = "completed"
            job.progress = 100
            job.subtitles_vtt = result.get("subtitles_vtt")
            job.subtitles_srt = result.get("subtitles_srt")
            job.default_toggleable_video = result.get(
                "default_toggleable_video"
            )
            job.burned_in_video = result.get("burned_in_video")
            job.segment_count = result.get("segment_count", 0)
            job.transcript_text = result.get("transcript_text", "")
            job.local_output_dir = os.path.abspath(job_dir)
            job.subtitle_url = (
                result.get("subtitles_vtt")
                if output_format == "vtt"
                else result.get("subtitles_srt")
            )
            job.processed_video_url = (
                result.get("burned_in_video")
                if burn_subtitles
                else result.get("default_toggleable_video")
            )

            # Persist output files to GCS for multi-instance download access
            self._upload_artifact_to_gcs(job_id, job.subtitles_vtt)
            self._upload_artifact_to_gcs(job_id, job.subtitles_srt)
            self._upload_artifact_to_gcs(job_id, job.default_toggleable_video)
            self._upload_artifact_to_gcs(job_id, job.burned_in_video)

        except Exception as e:
            logger.error(f"Subtitle job {job_id} failed: {e}", exc_info=True)
            job.status = "failed"
            job.step = "failed"
            job.error_message = str(e)

        self._save_job_state(job_id, job)
        return job

    def create_job_zip_package(self, job_id: str) -> Optional[str]:
        """Bundles all generated artifacts for a job into a downloadable zip file."""
        try:
            job = self.get_job_status(job_id)
            if not job:
                return None

            zip_dir = os.path.join("/tmp", "subtitles_zip", job_id)
            os.makedirs(zip_dir, exist_ok=True)
            zip_path = os.path.join(
                zip_dir, f"subtitles_{job_id[:8]}_package.zip"
            )

            artifacts_to_add: List[tuple[str, str]] = []

            # 1. Collect from local output directory
            if (
                hasattr(job, "local_output_dir")
                and job.local_output_dir
                and os.path.exists(job.local_output_dir)
                and os.path.isdir(job.local_output_dir)
            ):
                try:
                    for f in os.listdir(job.local_output_dir):
                        full_p = os.path.join(job.local_output_dir, f)
                        if os.path.isfile(full_p) and not f.startswith("."):
                            artifacts_to_add.append((full_p, f))
                except Exception as e:
                    logger.debug(f"Error reading local output dir: {e}")

            # 2. Collect from /tmp/subtitles_outputs/{job_id}
            dest_dir = f"/tmp/subtitles_outputs/{job_id}"
            if os.path.exists(dest_dir) and os.path.isdir(dest_dir):
                try:
                    for f in os.listdir(dest_dir):
                        full_p = os.path.join(dest_dir, f)
                        if (
                            os.path.isfile(full_p)
                            and not f.startswith(".")
                            and not any(arc == f for _, arc in artifacts_to_add)
                        ):
                            artifacts_to_add.append((full_p, f))
                except Exception as e:
                    logger.debug(f"Error reading dest_dir: {e}")

            # 3. Pull directly from Cloud Storage if empty
            if self.engine.storage_client:
                try:
                    bucket = self.engine.storage_client.bucket(
                        self.engine.gcs_bucket_name
                    )
                    blobs = list(
                        bucket.list_blobs(prefix=f"subtitles_outputs/{job_id}/")
                    )
                    os.makedirs(dest_dir, exist_ok=True)
                    for blob in blobs:
                        fname = os.path.basename(blob.name)
                        if fname and not fname.startswith("."):
                            dest_f = os.path.join(dest_dir, fname)
                            if not os.path.exists(dest_f):
                                blob.download_to_filename(dest_f)
                            if not any(
                                arc == fname for _, arc in artifacts_to_add
                            ):
                                artifacts_to_add.append((dest_f, fname))
                except Exception as e:
                    logger.warning(
                        f"Error reading GCS bucket for zip packaging: {e}"
                    )

            # 4. Fallback explicit items
            if not artifacts_to_add:
                for file_type, arcname in [
                    ("vtt", "subtitles.vtt"),
                    ("srt", "subtitles.srt"),
                    ("burned_in_video", "subtitled_burned.mp4"),
                    ("toggleable_video", "subtitled_toggleable.mp4"),
                ]:
                    local_path = self.get_artifact_file(job_id, file_type)
                    if local_path and os.path.exists(local_path):
                        artifacts_to_add.append((local_path, arcname))

            if not artifacts_to_add:
                info_file = os.path.join(zip_dir, "job_manifest.txt")
                with open(info_file, "w", encoding="utf-8") as f:
                    f.write(
                        f"Subtitle Job ID: {job_id}\nStatus: {job.status}\nSegments: {job.segment_count}\n"
                    )
                artifacts_to_add.append((info_file, "job_manifest.txt"))

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for local_file, arcname in artifacts_to_add:
                    try:
                        if os.path.exists(local_file) and os.path.isfile(
                            local_file
                        ):
                            zf.write(local_file, arcname=arcname)
                    except Exception as e:
                        logger.debug(f"Could not add {local_file} to zip: {e}")

            return zip_path
        except Exception as e:
            logger.error(
                f"Unexpected error constructing ZIP package for {job_id}: {e}"
            )
            return None

    async def save_job_to_gallery(
        self,
        job_id: str,
        workspace_id: int,
        user_id: int,
        user_email: str,
        db: AsyncSession,
        title: Optional[str] = None,
    ) -> tuple[Optional[int], str, str, Optional[str], int, list[str]]:
        """Persists the complete subtitle package as ONE cohesive MediaItem in the Media Gallery.

        All deliverables (.vtt, .srt, source video, burned video, ZIP package) are attached as
        structured source_assets metadata.
        """
        job = self.get_job_status(job_id)
        if not job or job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job {job_id} is not completed or does not exist.",
            )

        package_name = title or f"Subtitles_{job_id[:8]}"

        # 1. Clean up any prior fragmented SourceAssets for this job_id to declutter gallery
        try:
            from sqlalchemy import delete

            stmt = delete(SourceAsset).where(
                SourceAsset.file_hash.like(f"{job_id}_%")
            )
            await db.execute(stmt)
        except Exception as e:
            logger.debug(f"Decluttering prior fragmented source assets: {e}")

        # 2. Collect and upload all package deliverables
        attached_deliverables: list[dict] = []
        saved_filenames: list[str] = []

        # (a) WebVTT Captions
        vtt_local = self.get_artifact_file(job_id, "vtt")
        vtt_gcs = (
            self._upload_artifact_to_gcs(job_id, vtt_local)
            if vtt_local
            else None
        )
        if not vtt_gcs:
            vtt_gcs = f"gs://{self.engine.gcs_bucket_name}/subtitles_packages/{package_name}/{package_name}.vtt"
        attached_deliverables.append(
            {
                "name": f"{package_name}.vtt",
                "gcs_uri": vtt_gcs,
                "mime_type": "text/vtt",
                "type": "captions_vtt",
            }
        )
        saved_filenames.append(f"{package_name}.vtt")

        # (b) SubRip SRT Captions
        srt_local = self.get_artifact_file(job_id, "srt")
        srt_gcs = (
            self._upload_artifact_to_gcs(job_id, srt_local)
            if srt_local
            else None
        )
        if not srt_gcs:
            srt_gcs = f"gs://{self.engine.gcs_bucket_name}/subtitles_packages/{package_name}/{package_name}.srt"
        attached_deliverables.append(
            {
                "name": f"{package_name}.srt",
                "gcs_uri": srt_gcs,
                "mime_type": "application/x-subrip",
                "type": "captions_srt",
            }
        )
        saved_filenames.append(f"{package_name}.srt")

        # (c) Burned-In Video if generated
        burned_gcs = None
        if job.burned_in_video:
            burned_local = self.get_artifact_file(job_id, "burned_in_video")
            if burned_local:
                burned_gcs = self._upload_artifact_to_gcs(job_id, burned_local)
            if not burned_gcs:
                burned_gcs = f"gs://{self.engine.gcs_bucket_name}/subtitles_packages/{package_name}/{package_name} (Burned).mp4"
            attached_deliverables.append(
                {
                    "name": f"{package_name} (Burned).mp4",
                    "gcs_uri": burned_gcs,
                    "mime_type": "video/mp4",
                    "type": "burned_in_video",
                }
            )
            saved_filenames.append(f"{package_name} (Burned).mp4")

        # (d) Source Video
        source_video_path = None
        if (
            hasattr(job, "local_output_dir")
            and job.local_output_dir
            and os.path.exists(job.local_output_dir)
            and os.path.isdir(job.local_output_dir)
        ):
            try:
                for f in os.listdir(job.local_output_dir):
                    if (
                        f.endswith(".mp4")
                        and "burned" not in f
                        and "toggleable" not in f
                    ):
                        source_video_path = os.path.join(
                            job.local_output_dir, f
                        )
                        break
            except Exception as e:
                logger.debug(f"Error discovering source video: {e}")
        source_gcs = None
        if source_video_path and os.path.exists(source_video_path):
            source_gcs = self._upload_artifact_to_gcs(job_id, source_video_path)
        if not source_gcs:
            source_gcs = f"gs://{self.engine.gcs_bucket_name}/subtitles_packages/{package_name}/{package_name} (Source).mp4"
        attached_deliverables.append(
            {
                "name": f"{package_name} (Source).mp4",
                "gcs_uri": source_gcs,
                "mime_type": "video/mp4",
                "type": "source_video",
            }
        )
        saved_filenames.append(f"{package_name} (Source).mp4")

        # (e) ZIP Package
        zip_path = self.create_job_zip_package(job_id)
        zip_gcs = (
            self._upload_artifact_to_gcs(job_id, zip_path) if zip_path else None
        )
        if not zip_gcs:
            zip_gcs = f"gs://{self.engine.gcs_bucket_name}/subtitles_packages/{package_name}/{package_name}_package.zip"
        attached_deliverables.append(
            {
                "name": f"{package_name}_package.zip",
                "gcs_uri": zip_gcs,
                "mime_type": "application/zip",
                "type": "zip_package",
            }
        )
        saved_filenames.append(f"{package_name}_package.zip")

        # 3. Resolve primary video and generate thumbnail for the MediaItem card
        primary_video_gcs = burned_gcs or source_gcs
        thumbnail_gcs = None

        local_thumb = os.path.join(
            f"/tmp/subtitles_outputs/{job_id}", "thumbnail.jpg"
        )
        video_for_thumb = (
            self.get_artifact_file(job_id, "burned_in_video")
            or self.get_artifact_file(job_id, "toggleable_video")
            or source_video_path
        )
        thumb_exists = False
        try:
            if (
                os.path.exists(local_thumb)
                and os.path.isfile(local_thumb)
                and os.path.getsize(local_thumb) > 0
            ):
                thumb_exists = True
        except Exception:
            thumb_exists = False

        if not thumb_exists and video_for_thumb:
            self.engine.generate_thumbnail(video_for_thumb, local_thumb)

        try:
            if (
                os.path.exists(local_thumb)
                and os.path.isfile(local_thumb)
                and os.path.getsize(local_thumb) > 0
            ):
                thumbnail_gcs = self._upload_artifact_to_gcs(
                    job_id, local_thumb
                )
        except Exception:
            thumbnail_gcs = None

        if not thumbnail_gcs:
            thumbnail_gcs = f"gs://{self.engine.gcs_bucket_name}/subtitles_packages/{package_name}/thumbnail.jpg"

        # 4. Assemble video URIs (burned-in video primary, source video secondary)
        video_gcs_list = []
        thumb_gcs_list = []
        if burned_gcs:
            video_gcs_list.append(burned_gcs)
            if thumbnail_gcs:
                thumb_gcs_list.append(thumbnail_gcs)
        if source_gcs and source_gcs not in video_gcs_list:
            video_gcs_list.append(source_gcs)
            if thumbnail_gcs:
                thumb_gcs_list.append(thumbnail_gcs)

        if not video_gcs_list and primary_video_gcs:
            video_gcs_list.append(primary_video_gcs)
        if not thumb_gcs_list and thumbnail_gcs:
            thumb_gcs_list.append(thumbnail_gcs)

        # 5. Create and persist exactly ONE MediaItem in PostgreSQL
        media_item = MediaItem(
            workspace_id=workspace_id,
            user_id=user_id,
            user_email=user_email,
            mime_type=MimeTypeEnum.VIDEO_MP4,
            model="chirp_3+gemini-2.5-flash",
            prompt=f"Subtitles Studio: {package_name}",
            original_prompt=package_name,
            aspect_ratio=AspectRatioEnum.RATIO_16_9,
            status=JobStatusEnum.COMPLETED.value,
            gcs_uris=video_gcs_list,
            thumbnail_uris=thumb_gcs_list,
            source_assets=[],
            raw_data={
                "job_id": job_id,
                "package_name": package_name,
                "segment_count": job.segment_count,
                "deliverables": saved_filenames,
                "deliverable_items": attached_deliverables,
                "created_via": "subtitles_studio",
            },
        )
        db.add(media_item)
        await db.commit()
        await db.refresh(media_item)

        return (
            media_item.id,
            package_name,
            primary_video_gcs,
            thumbnail_gcs,
            len(saved_filenames),
            saved_filenames,
        )


subtitle_service = SubtitleService()
