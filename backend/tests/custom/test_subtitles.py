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

"""Unit tests for the custom subtitle processing service and API endpoints."""

import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from fastapi import HTTPException
from src.custom.subtitles.subtitle_dto import (
    SubtitleRequestDTO,
    SubtitleResponseDTO,
)
from src.custom.subtitles.subtitle_service import (
    PodcastSubtitleEngine,
    SubtitleService,
)


@pytest.fixture(autouse=True)
def isolate_test_subtitles_output_dir(tmp_path, monkeypatch):
    """Isolates SUBTITLES_OUTPUT_DIR to a temporary pytest directory to avoid polluting workspace."""
    test_out = tmp_path / "test_subtitles_out"
    test_out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SUBTITLES_OUTPUT_DIR", str(test_out))


def test_subtitle_dto_instantiation():
    """Tests instantiation and field defaults of Subtitle DTOs."""
    req = SubtitleRequestDTO(video_url="gs://test-bucket/video.mp4")
    assert req.video_url == "gs://test-bucket/video.mp4"
    assert req.language_code == "en-US"
    assert req.output_format == "vtt"
    assert req.burn_subtitles is False

    res = SubtitleResponseDTO(job_id="sub_123", status="completed")
    assert res.job_id == "sub_123"
    assert res.status == "completed"
    assert res.segment_count == 0


def test_timestamp_formatting():
    """Tests VTT and SRT timestamp formatters in PodcastSubtitleEngine."""
    engine = PodcastSubtitleEngine()
    vtt_ts = engine._format_vtt_timestamp(65.432)
    assert vtt_ts == "00:01:05.432"

    srt_ts = engine._format_srt_timestamp(3665.123)
    assert srt_ts == "01:01:05,123"


def test_max_char_limit_enforcement():
    """Tests character limit enforcement to ensure <= 42 chars per line."""
    engine = PodcastSubtitleEngine()
    long_segment = [
        {
            "speaker": "Speaker 1",
            "start_time": 0.0,
            "end_time": 10.0,
            "text": "This is a very long subtitle sentence that exceeds forty two characters and must be split into multiple sub-segments deterministically.",
        }
    ]
    refined = engine._enforce_max_char_limit(long_segment, max_chars=42)
    assert len(refined) > 1
    for seg in refined:
        assert len(seg["text"]) <= 42


def test_export_vtt_srt():
    """Tests sidecar file export for WebVTT and SubRip SRT formats."""
    engine = PodcastSubtitleEngine()
    subtitle_data = [
        {
            "speaker": "Speaker 1",
            "start_time": 1.0,
            "end_time": 3.0,
            "text": "Hello world",
        },
        {
            "speaker": "Speaker 2",
            "start_time": 3.5,
            "end_time": 5.0,
            "text": "Welcome to podcast",
        },
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        vtt_path = os.path.join(tmpdir, "test.vtt")
        srt_path = os.path.join(tmpdir, "test.srt")
        paths = engine.export_vtt_srt(subtitle_data, vtt_path, srt_path)

        assert os.path.exists(paths["vtt"])
        assert os.path.exists(paths["srt"])

        with open(paths["vtt"], "r", encoding="utf-8") as f:
            vtt_content = f.read()
            assert "WEBVTT" in vtt_content
            assert "Hello world" in vtt_content

        with open(paths["srt"], "r", encoding="utf-8") as f:
            srt_content = f.read()
            assert "1\n00:00:01,000 --> 00:00:03,000" in srt_content


def test_rule_based_fallback_segmenter():
    """Tests fallback segmentation when LLM refinement is unavailable."""
    engine = PodcastSubtitleEngine()
    words_data = [
        {
            "word": "Welcome",
            "start_time": 0.0,
            "end_time": 0.5,
            "speaker": "Speaker 1",
        },
        {
            "word": "everyone",
            "start_time": 0.5,
            "end_time": 1.0,
            "speaker": "Speaker 1",
        },
    ]
    segs = engine._fallback_rule_based_segmenter(words_data, max_chars=42)
    assert len(segs) == 1
    assert segs[0]["text"] == "Welcome everyone"


def test_download_youtube_audio():
    """Tests YouTube audio downloader with mocked subprocess."""
    engine = PodcastSubtitleEngine()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_file = os.path.join(tmpdir, "yt_download.mp3")
        with open(fake_file, "w") as f:
            f.write("dummy audio")

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0)
            res = engine.download_youtube_audio(
                "https://youtube.com/watch?v=123", tmpdir
            )
            assert res == fake_file

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(
                returncode=1, stderr="Error downloading"
            )
            with pytest.raises(RuntimeError):
                engine.download_youtube_audio(
                    "https://youtube.com/watch?v=123", tmpdir
                )


def test_transcribe_chirp3_local_file():
    """Tests STT v2 transcription with local file and GCS upload mock."""
    engine = PodcastSubtitleEngine()
    engine.speech_client = MagicMock()
    engine.storage_client = MagicMock()

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_file:
        tmp_path = tmp_file.name

        mock_op = MagicMock()
        mock_op.result.return_value = MagicMock(
            results={
                "uri1": MagicMock(
                    transcript=MagicMock(
                        results=[
                            MagicMock(
                                alternatives=[
                                    MagicMock(
                                        transcript="hello podcast",
                                        words=[
                                            MagicMock(
                                                word="hello",
                                                start_offset=MagicMock(
                                                    total_seconds=lambda: 0.0
                                                ),
                                                end_offset=MagicMock(
                                                    total_seconds=lambda: 0.5
                                                ),
                                                speaker_label="1",
                                            ),
                                            MagicMock(
                                                word="podcast",
                                                start_offset=MagicMock(
                                                    total_seconds=lambda: 0.5
                                                ),
                                                end_offset=MagicMock(
                                                    total_seconds=lambda: 1.0
                                                ),
                                                speaker_label="1",
                                            ),
                                        ],
                                    )
                                ]
                            )
                        ]
                    )
                )
            }
        )
        engine.speech_client.batch_recognize.return_value = mock_op

        with patch("subprocess.run") as mock_ffmpeg:
            mock_ffmpeg.return_value = MagicMock(returncode=0)
            result = engine.transcribe_chirp3(tmp_path)
            assert "hello podcast" in result["full_text"]
            assert len(result["words"]) == 2


def test_refine_gemini36_success():
    """Tests Gemini subtitle refinement with mocked GenAI response."""
    engine = PodcastSubtitleEngine()
    engine.genai_client = MagicMock()

    mock_res = MagicMock()
    mock_res.text = '[{"speaker": "Speaker 1", "start_time": 0.0, "end_time": 1.0, "text": "Hello podcast"}]'
    engine.genai_client.models.generate_content.return_value = mock_res

    words_data = {
        "words": [
            {
                "word": "Hello",
                "start_time": 0.0,
                "end_time": 0.5,
                "speaker": "Speaker 1",
            }
        ]
    }
    refined = engine.refine_gemini36(words_data)
    assert len(refined) == 1
    assert refined[0]["text"] == "Hello podcast"


def test_ffmpeg_burning_and_embedding():
    """Tests FFmpeg hardburn and soft subtitle embedding with mocked subprocess."""
    engine = PodcastSubtitleEngine()
    with (
        tempfile.NamedTemporaryFile(suffix=".mp4") as video_file,
        tempfile.NamedTemporaryFile(suffix=".vtt") as sub_file,
    ):
        out_video = video_file.name + ".out.mp4"

        with (
            patch("subprocess.run") as mock_sub,
            patch("os.replace") as mock_rep,
        ):
            mock_sub.return_value = MagicMock(returncode=0)
            res_burn = engine.burn_subtitles_ffmpeg(
                video_file.name, sub_file.name, out_video
            )
            assert res_burn == out_video

            res_embed = engine.embed_soft_subtitles_ffmpeg(
                video_file.name, sub_file.name, out_video
            )
            assert res_embed == out_video

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(
                returncode=1, stderr="FFmpeg filter error"
            )
            with pytest.raises(RuntimeError):
                engine.burn_subtitles_ffmpeg(
                    video_file.name, sub_file.name, out_video
                )
            with pytest.raises(RuntimeError):
                engine.embed_soft_subtitles_ffmpeg(
                    video_file.name, sub_file.name, out_video
                )

        if os.path.exists(out_video):
            os.remove(out_video)


def test_process_video_pipeline():
    """Tests end-to-end process_video pipeline execution with mocks."""
    engine = PodcastSubtitleEngine()
    with (
        tempfile.NamedTemporaryFile(suffix=".mp4") as video_file,
        tempfile.TemporaryDirectory() as job_dir,
    ):
        with (
            patch.object(engine, "transcribe_chirp3") as mock_stt,
            patch.object(engine, "refine_gemini36") as mock_gemini,
            patch.object(engine, "embed_soft_subtitles_ffmpeg") as mock_embed,
            patch.object(engine, "burn_subtitles_ffmpeg") as mock_burn,
        ):

            mock_stt.return_value = {"full_text": "Sample text", "words": []}
            mock_gemini.return_value = [
                {
                    "speaker": "Speaker 1",
                    "start_time": 0.0,
                    "end_time": 1.0,
                    "text": "Sample text",
                }
            ]

            res = engine.process_video(
                video_file.name, job_dir=job_dir, generate_burned_in=True
            )
            assert res["segment_count"] == 1
            assert os.path.exists(res["subtitles_vtt"])
            assert os.path.exists(res["subtitles_srt"])


def test_subtitle_service_job_lifecycle():
    """Tests SubtitleService job tracking lifecycle."""
    service = SubtitleService()
    job_id = service.create_job()
    assert job_id.startswith("sub_")

    status = service.get_job_status(job_id)
    assert status is not None
    assert status.status == "pending"

    with patch.object(service.engine, "process_video") as mock_process:
        mock_process.return_value = {
            "job_dir": "/tmp/job",
            "source_video": "/tmp/job/video.mp4",
            "default_toggleable_video": "/tmp/job/output_toggleable.mp4",
            "burned_in_video": None,
            "subtitles_vtt": "/tmp/job/subtitles.vtt",
            "subtitles_srt": "/tmp/job/subtitles.srt",
            "segment_count": 2,
            "transcript_text": "Welcome everyone",
        }
        updated_job = service.process_job(
            job_id=job_id,
            video_path="/tmp/job/video.mp4",
            burn_subtitles=False,
            output_format="vtt",
        )
        assert updated_job.status == "completed"
        assert updated_job.segment_count == 2
        assert updated_job.subtitles_vtt == "/tmp/job/subtitles.vtt"
        assert updated_job.local_output_dir is not None

    with patch.object(
        service.engine, "process_video", side_effect=ValueError("Invalid video")
    ):
        failed_job = service.process_job(
            job_id="sub_failed_1",
            video_path="/tmp/invalid.mp4",
        )
        assert failed_job.status == "failed"
        assert "Invalid video" in failed_job.error_message


def test_resolve_output_dir():
    """Tests resolve_output_dir helper with custom package name, auto-versioning, and fallback."""
    service = SubtitleService()
    custom_dir = service.resolve_output_dir("Sundar Pichai Clip!", "123")
    assert "Sundar Pichai Clip" in custom_dir
    assert os.path.exists(custom_dir)

    # Place a dummy file in the directory to simulate an existing completed package
    dummy_file = os.path.join(custom_dir, "subtitles.vtt")
    with open(dummy_file, "w") as f:
        f.write("WEBVTT")

    # Resolving with the same name should now auto-version to _v2
    versioned_dir = service.resolve_output_dir("Sundar Pichai Clip!", "123")
    assert versioned_dir.endswith("_v2")
    assert os.path.exists(versioned_dir)

    fallback_dir = service.resolve_output_dir("", "456")
    assert "job_456" in fallback_dir
    assert os.path.exists(fallback_dir)


def test_controller_generate_endpoint_json(api_client):
    """Tests POST /api/v1/custom/subtitles/generate endpoint with JSON request."""
    with patch(
        "src.custom.subtitles.subtitle_controller.subtitle_service.process_job"
    ) as mock_pj:
        mock_pj.return_value = SubtitleResponseDTO(
            job_id="sub_test123",
            status="completed",
            subtitles_vtt="/tmp/subtitles.vtt",
            default_toggleable_video="/tmp/toggleable.mp4",
            segment_count=5,
        )

        # Sync mode test
        response_sync = api_client.post(
            "/api/v1/custom/subtitles/generate?sync=true",
            json={
                "video_url": "gs://test-bucket/test_video.mp4",
                "output_format": "vtt",
                "burn_subtitles": False,
            },
        )
        assert response_sync.status_code == 200
        data_sync = response_sync.json()
        assert data_sync["job_id"] == "sub_test123"
        assert data_sync["status"] == "completed"

        # Async background mode test
        response_async = api_client.post(
            "/api/v1/custom/subtitles/generate",
            json={
                "video_url": "gs://test-bucket/test_video.mp4",
                "output_format": "vtt",
                "burn_subtitles": False,
            },
        )
        assert response_async.status_code == 200
        data_async = response_async.json()
        assert data_async["status"] == "processing"


def test_controller_generate_youtube(api_client):
    """Tests POST /api/v1/custom/subtitles/generate with YouTube URL."""
    with (
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.engine.download_youtube_audio"
        ) as mock_yt,
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.process_job"
        ) as mock_pj,
    ):
        mock_yt.return_value = "/tmp/yt_audio.mp3"
        mock_pj.return_value = SubtitleResponseDTO(
            job_id="sub_yt1", status="completed"
        )

        response = api_client.post(
            "/api/v1/custom/subtitles/generate?sync=true",
            json={"video_url": "https://www.youtube.com/watch?v=test"},
        )
        assert response.status_code == 200


def test_controller_generate_missing_input(api_client):
    """Tests POST /api/v1/custom/subtitles/generate with no input."""
    response = api_client.post(
        "/api/v1/custom/subtitles/generate",
        json={},
    )
    assert response.status_code == 400


def test_controller_generate_failure(api_client):
    """Tests POST /api/v1/custom/subtitles/generate when processing fails."""
    with patch(
        "src.custom.subtitles.subtitle_controller.subtitle_service.process_job"
    ) as mock_pj:
        mock_pj.return_value = SubtitleResponseDTO(
            job_id="sub_err1",
            status="failed",
            error_message="Processing error",
        )
        response = api_client.post(
            "/api/v1/custom/subtitles/generate?sync=true",
            json={"video_url": "gs://test/video.mp4"},
        )
        assert response.status_code == 500


def test_controller_get_status(api_client):
    """Tests GET /api/v1/custom/subtitles/status/{job_id} endpoint."""
    with patch(
        "src.custom.subtitles.subtitle_controller.subtitle_service.get_job_status"
    ) as mock_status:
        mock_status.return_value = SubtitleResponseDTO(
            job_id="sub_status_123",
            status="processing",
        )
        response = api_client.get(
            "/api/v1/custom/subtitles/status/sub_status_123"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "processing"

    response_404 = api_client.get(
        "/api/v1/custom/subtitles/status/sub_nonexistent"
    )
    assert response_404.status_code == 404


def test_controller_download_file_types(api_client):
    """Tests GET /api/v1/custom/subtitles/download/{job_id} for various file types."""
    with (
        tempfile.NamedTemporaryFile(suffix=".vtt", delete=False) as tmp_vtt,
        tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp_srt,
        tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_mp4,
    ):

        tmp_vtt.write(b"WEBVTT\n1\n00:00:00.000 --> 00:00:02.000\nHello")
        tmp_srt.write(b"1\n00:00:00,000 --> 00:00:02,000\nHello")
        tmp_mp4.write(b"fake mp4 header")

        tmp_vtt_path = tmp_vtt.name
        tmp_srt_path = tmp_srt.name
        tmp_mp4_path = tmp_mp4.name

    try:
        dto_success = SubtitleResponseDTO(
            job_id="sub_download_123",
            status="completed",
            subtitles_vtt=tmp_vtt_path,
            subtitles_srt=tmp_srt_path,
            default_toggleable_video=tmp_mp4_path,
            burned_in_video=tmp_mp4_path,
        )
        with patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.get_job_status"
        ) as mock_status:
            mock_status.side_effect = lambda jid: (
                dto_success if jid == "sub_download_123" else None
            )

            res_vtt = api_client.get(
                "/api/v1/custom/subtitles/download/sub_download_123?file_type=vtt"
            )
            assert res_vtt.status_code == 200

            res_srt = api_client.get(
                "/api/v1/custom/subtitles/download/sub_download_123?file_type=srt"
            )
            assert res_srt.status_code == 200

            res_video = api_client.get(
                "/api/v1/custom/subtitles/download/sub_download_123?file_type=toggleable_video"
            )
            assert res_video.status_code == 200

            res_burned = api_client.get(
                "/api/v1/custom/subtitles/download/sub_download_123?file_type=burned_in_video"
            )
            assert res_burned.status_code == 200

            res_404_job = api_client.get(
                "/api/v1/custom/subtitles/download/unknown_job"
            )
            assert res_404_job.status_code == 404

            res_invalid_type = api_client.get(
                "/api/v1/custom/subtitles/download/sub_download_123?file_type=invalid_type"
            )
            assert res_invalid_type.status_code == 404
    finally:
        for p in [tmp_vtt_path, tmp_srt_path, tmp_mp4_path]:
            if os.path.exists(p):
                os.remove(p)


def test_controller_generate_multipart_form(api_client):
    """Tests POST /api/v1/custom/subtitles/generate with multipart form file upload."""
    with patch(
        "src.custom.subtitles.subtitle_controller.subtitle_service.process_job"
    ) as mock_pj:
        mock_pj.return_value = SubtitleResponseDTO(
            job_id="sub_form1",
            status="completed",
            subtitles_vtt="/tmp/subtitles.vtt",
            segment_count=3,
        )

        response = api_client.post(
            "/api/v1/custom/subtitles/generate?sync=true",
            data={
                "package_name": "My Form Podcast",
                "language_code": "en-US",
                "output_format": "vtt",
                "burn_subtitles": "true",
            },
            files={"file": ("test_audio.mp4", b"fake audio data", "video/mp4")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "sub_form1"
        assert data["status"] == "completed"


def test_refine_gemini_large_chunk_batching():
    """Tests refine_gemini36 with > 70 words to verify chunk batching logic."""
    engine = PodcastSubtitleEngine()
    words = [
        {
            "word": f"word_{i}",
            "start_time": float(i),
            "end_time": float(i + 0.5),
            "speaker": "Speaker 1",
        }
        for i in range(150)
    ]
    with patch.object(
        engine,
        "_refine_chunk_gemini",
        side_effect=lambda chunk: [
            {
                "speaker": "Speaker 1",
                "start_time": chunk[0]["start_time"],
                "end_time": chunk[-1]["end_time"],
                "text": " ".join(w["word"] for w in chunk),
            }
        ],
    ):
        result = engine.refine_gemini36({"words": words})
        assert len(result) >= 2


def test_timestamp_boundary_no_four_digits():
    """Verifies timestamps close to integer seconds never emit 4-digit milliseconds."""
    engine = PodcastSubtitleEngine()
    # 59.9998 should round to 00:01:00.000, NOT 00:00:59.1000
    vtt = engine._format_vtt_timestamp(59.9998)
    assert vtt == "00:01:00.000"
    assert len(vtt.split(".")[1]) == 3

    srt = engine._format_srt_timestamp(59.9998)
    assert srt == "00:01:00,000"
    assert len(srt.split(",")[1]) == 3


def test_subtitle_service_job_eviction():
    """Tests that SubtitleService caps its in-memory job cache to prevent memory leaks."""
    service = SubtitleService()
    first_job_id = service.create_job()
    assert first_job_id in service.jobs

    for _ in range(105):
        service.create_job()

    assert len(service.jobs) <= 100
    assert first_job_id not in service.jobs


def test_transcribe_chirp3_error_raised():
    """Tests that Speech-to-Text v2 error response raises RuntimeError."""
    engine = PodcastSubtitleEngine()
    engine.speech_client = MagicMock()
    mock_op = MagicMock()
    mock_res = MagicMock()
    mock_file_res = MagicMock()
    mock_file_res.error.code = 3
    mock_file_res.error.message = "Invalid audio content"
    mock_res.results = {"file1": mock_file_res}
    mock_op.result.return_value = mock_res
    engine.speech_client.batch_recognize.return_value = mock_op

    with pytest.raises(RuntimeError, match="Speech-to-Text v2 error"):
        engine.transcribe_chirp3(
            audio_path_or_gcs_uri="gs://bucket/test.wav",
            language_code="en-US",
        )


def test_generate_signed_upload_url():
    """Tests that SubtitleService generates signed upload URLs."""
    service = SubtitleService()
    with patch(
        "src.auth.iam_signer_credentials_service.IamSignerCredentials.generate_v4_upload_signed_url"
    ) as mock_signer:
        mock_signer.return_value = (
            "https://storage.googleapis.com/upload-signed-url",
            "gs://test-bucket/subtitles_inputs/123/video.mp4",
        )
        url, uri = service.generate_signed_upload_url(
            filename="podcast_clip.mp4",
            content_type="video/mp4",
            bucket_name="test-bucket",
        )
        assert url == "https://storage.googleapis.com/upload-signed-url"
        assert uri == "gs://test-bucket/subtitles_inputs/123/video.mp4"


def test_generate_signed_upload_url_fallback():
    """Tests fallback to direct storage client when IamSigner is unavailable."""
    service = SubtitleService()
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://signed.url/direct"
    service.engine.storage_client = MagicMock()
    service.engine.storage_client.bucket.return_value.blob.return_value = (
        mock_blob
    )

    with patch(
        "src.auth.iam_signer_credentials_service.IamSignerCredentials.generate_v4_upload_signed_url",
        side_effect=Exception("IamSigner not configured"),
    ):
        url, uri = service.generate_signed_upload_url(
            filename="clip.mp4",
            content_type="video/mp4",
            bucket_name="test-bucket",
        )
        assert url == "https://signed.url/direct"
        assert uri.startswith("gs://test-bucket/subtitles_inputs/")


def test_process_video_gcs_uri_download(tmp_path):
    """Tests that process_video downloads GCS video files to job directory before processing."""
    engine = PodcastSubtitleEngine()
    engine.storage_client = MagicMock()
    mock_blob = MagicMock()
    engine.storage_client.bucket.return_value.blob.return_value = mock_blob

    def mock_download(dest):
        with open(dest, "wb") as f:
            f.write(b"mock video data")

    mock_blob.download_to_filename.side_effect = mock_download

    with (
        patch.object(
            engine, "transcribe_chirp3", return_value={"segments": []}
        ),
        patch.object(engine, "refine_gemini36", return_value=[]),
        patch.object(engine, "export_vtt_srt"),
        patch.object(engine, "embed_soft_subtitles_ffmpeg"),
        patch.object(engine, "burn_subtitles_ffmpeg"),
    ):
        res = engine.process_video(
            video_path="gs://my-bucket/inputs/video.mp4",
            job_dir=str(tmp_path),
            generate_burned_in=True,
        )
        assert "subtitles_vtt" in res
        mock_blob.download_to_filename.assert_called_once()


def test_controller_generate_upload_url_endpoint(api_client):
    """Tests the POST /generate-upload-url controller endpoint."""
    from src.custom.subtitles.subtitle_service import subtitle_service

    with patch.object(
        subtitle_service,
        "generate_signed_upload_url",
        return_value=(
            "https://signed.upload.url",
            "gs://my-bucket/subtitles/video.mp4",
        ),
    ):
        response = api_client.post(
            "/api/v1/custom/subtitles/generate-upload-url",
            json={"filename": "test.mp4", "content_type": "video/mp4"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["upload_url"] == "https://signed.upload.url"
        assert data["gcs_uri"] == "gs://my-bucket/subtitles/video.mp4"


def test_job_state_gcs_persistence():
    """Tests saving and reading job state to/from GCS."""
    service = SubtitleService()
    service.engine.storage_client = MagicMock()
    mock_blob = MagicMock()
    service.engine.storage_client.bucket.return_value.blob.return_value = (
        mock_blob
    )
    mock_blob.exists.return_value = True
    mock_blob.download_as_text.return_value = (
        '{"job_id": "sub_gcs_1", "status": "completed", "progress": 100}'
    )

    dto = SubtitleResponseDTO(
        job_id="sub_gcs_1", status="completed", progress=100
    )
    service._save_job_state("sub_gcs_1", dto)
    mock_blob.upload_from_string.assert_called_once()

    # Clear memory to force GCS read
    service.jobs.clear()
    loaded = service.get_job_status("sub_gcs_1")
    assert loaded is not None
    assert loaded.job_id == "sub_gcs_1"
    assert loaded.status == "completed"


def test_job_state_local_disk_load(tmp_path, monkeypatch):
    """Tests reading job state from local disk when not in memory."""
    service = SubtitleService()
    service.engine.storage_client = None
    service.jobs.clear()

    local_dir = tmp_path / "subtitles_jobs"
    local_dir.mkdir(parents=True, exist_ok=True)
    job_file = local_dir / "sub_local_1.json"
    job_file.write_text(
        '{"job_id": "sub_local_1", "status": "completed", "progress": 100}'
    )

    with (
        patch(
            "os.path.exists",
            side_effect=lambda p: (
                True
                if str(p) == str(job_file)
                or "/tmp/subtitles_jobs/sub_local_1.json" in str(p)
                else os.path.exists(p)
            ),
        ),
        patch(
            "builtins.open",
            patch(
                "builtins.open",
                return_value=open(job_file, "r", encoding="utf-8"),
            ),
        ),
    ):
        dto = SubtitleResponseDTO(job_id="sub_local_1", status="completed")
        service._save_job_state("sub_local_1", dto)
        assert service.get_job_status("sub_local_1") is not None


def test_upload_artifact_and_get_artifact(tmp_path):
    """Tests artifact upload and download resolution from GCS."""
    service = SubtitleService()
    service.engine.storage_client = MagicMock()
    mock_blob = MagicMock()
    mock_blob.name = "subtitles_outputs/sub_art_1/test_output.vtt"
    service.engine.storage_client.bucket.return_value.blob.return_value = (
        mock_blob
    )
    service.engine.storage_client.bucket.return_value.list_blobs.return_value = [
        mock_blob
    ]

    dummy_file = tmp_path / "test.vtt"
    dummy_file.write_text("WEBVTT\n")

    uri = service._upload_artifact_to_gcs("sub_art_1", str(dummy_file))
    assert uri is not None
    assert "subtitles_outputs/sub_art_1" in uri

    # Test downloading artifact on another instance
    dto = SubtitleResponseDTO(
        job_id="sub_art_1",
        status="completed",
        subtitles_vtt="/non/existent/path.vtt",
    )
    service.jobs["sub_art_1"] = dto

    with patch.object(mock_blob, "download_to_filename") as mock_dl:

        def fake_download(dest):
            with open(dest, "w") as f:
                f.write("WEBVTT")

        mock_dl.side_effect = fake_download
        res = service.get_artifact_file("sub_art_1", "vtt")
        assert res is not None
        assert res.endswith("test_output.vtt")

        # Test non-existent job
        assert service.get_artifact_file("nonexistent_job", "vtt") is None

        # Test other file types
        mock_blob_srt = MagicMock()
        mock_blob_srt.name = "subtitles_outputs/sub_art_1/test_output.srt"
        service.engine.storage_client.bucket.return_value.list_blobs.return_value = [
            mock_blob_srt
        ]
        res_srt = service.get_artifact_file("sub_art_1", "srt")
        assert res_srt is not None

        # Test none returned on upload if path does not exist
        assert service._upload_artifact_to_gcs("sub_art_1", "/bad/path") is None


def test_create_job_zip_package(tmp_path):
    """Tests creating a zip bundle of job artifacts."""
    service = SubtitleService()
    dto = SubtitleResponseDTO(
        job_id="sub_zip_1",
        status="completed",
        subtitles_vtt=str(tmp_path / "test.vtt"),
        subtitles_srt=str(tmp_path / "test.srt"),
    )
    (tmp_path / "test.vtt").write_text("WEBVTT\n")
    (tmp_path / "test.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
    service.jobs["sub_zip_1"] = dto

    with patch.object(service, "get_artifact_file") as mock_get:
        mock_get.side_effect = lambda jid, ft: (
            str(tmp_path / "test.vtt") if ft == "vtt" else None
        )
        zip_path = service.create_job_zip_package("sub_zip_1")
        assert zip_path is not None
        assert os.path.exists(zip_path)


@pytest.mark.asyncio
async def test_save_job_to_gallery():
    """Tests saving a completed job to the Media Gallery as a SourceAsset."""
    service = SubtitleService()
    dto = SubtitleResponseDTO(
        job_id="sub_gal_1",
        status="completed",
        burned_in_video="/tmp/output.mp4",
    )
    service.jobs["sub_gal_1"] = dto

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.execute = AsyncMock()

    with (
        patch.object(
            service, "get_artifact_file", return_value="/tmp/output.mp4"
        ),
        patch.object(
            service,
            "_upload_artifact_to_gcs",
            return_value="gs://bucket/subtitles_outputs/sub_gal_1/output.mp4",
        ),
        patch.object(
            service,
            "create_job_zip_package",
            return_value="/tmp/package.zip",
        ),
        patch("os.path.exists", return_value=True),
    ):
        (
            primary_id,
            pkg_name,
            gcs_uri,
            thumb_uri,
            saved_count,
            saved_files,
        ) = await service.save_job_to_gallery(
            job_id="sub_gal_1",
            workspace_id=1,
            user_id=42,
            user_email="test@example.com",
            db=mock_db,
            title="Podcast Subtitled",
        )
        assert pkg_name == "Podcast Subtitled"
        assert saved_count >= 1
        assert len(saved_files) >= 1


def test_controller_save_to_gallery_endpoint(api_client):
    """Tests the POST /save-to-gallery controller endpoint."""
    from src.custom.subtitles.subtitle_service import subtitle_service

    with patch.object(
        subtitle_service,
        "save_job_to_gallery",
        return_value=(
            99,
            "My Saved Video",
            "gs://bucket/subtitles_packages/My_Saved_Video/video.mp4",
            "gs://bucket/subtitles_packages/My_Saved_Video/thumb.jpg",
            3,
            ["subtitles.vtt", "subtitles.srt", "output_burned.mp4"],
        ),
    ):
        response = api_client.post(
            "/api/v1/custom/subtitles/save-to-gallery",
            json={
                "job_id": "sub_gal_1",
                "workspace_id": 1,
                "title": "My Saved Video",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["saved_filenames"]) == 3


def test_generate_thumbnail_success_and_fallback():
    """Tests thumbnail generation via ffmpeg and fallback."""
    from src.custom.subtitles.subtitle_service import PodcastSubtitleEngine

    engine = PodcastSubtitleEngine()

    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.getsize", return_value=1024),
        patch("subprocess.run") as mock_sub,
    ):
        mock_sub.return_value = MagicMock(returncode=0)
        res = engine.generate_thumbnail("/tmp/video.mp4", "/tmp/thumb.jpg")
        assert res == "/tmp/thumb.jpg"

    # Test failure when file doesn't exist
    with patch("os.path.exists", return_value=False):
        res = engine.generate_thumbnail("/tmp/video.mp4", "/tmp/thumb.jpg")
        assert res is None


def test_save_job_to_gallery_uncompleted_error():
    """Tests that attempting to save an incomplete job raises 400."""
    from fastapi import HTTPException
    from src.custom.subtitles.subtitle_service import SubtitleService

    service = SubtitleService()
    dto = SubtitleResponseDTO(
        job_id="sub_pending",
        status="processing",
    )
    service.jobs["sub_pending"] = dto
    mock_db = MagicMock()

    import pytest

    with pytest.raises(HTTPException) as exc_info:
        import asyncio

        asyncio.run(
            service.save_job_to_gallery(
                job_id="sub_pending",
                workspace_id=1,
                user_id=1,
                user_email="a@b.com",
                db=mock_db,
            )
        )
    assert exc_info.value.status_code == 400


def test_get_artifact_file_gcs_matching():
    """Tests get_artifact_file GCS blob searching and downloading."""
    from src.custom.subtitles.subtitle_service import SubtitleService

    service = SubtitleService()
    dto = SubtitleResponseDTO(
        job_id="sub_art_gcs",
        status="completed",
    )
    service.jobs["sub_art_gcs"] = dto

    mock_blob = MagicMock()
    mock_blob.name = "subtitles_outputs/sub_art_gcs/subtitles.vtt"
    mock_blob.download_to_filename = MagicMock()

    mock_bucket = MagicMock()
    mock_bucket.list_blobs.return_value = [mock_blob]

    mock_storage = MagicMock()
    mock_storage.bucket.return_value = mock_bucket
    service.engine.storage_client = mock_storage

    with (
        patch("os.path.exists", return_value=False),
        patch("os.makedirs"),
    ):
        res = service.get_artifact_file("sub_art_gcs", "vtt")
        assert res is not None
        assert res.endswith("subtitles.vtt")


def test_create_job_zip_package_empty_manifest():
    """Tests create_job_zip_package creating a manifest if no artifacts exist."""
    from src.custom.subtitles.subtitle_service import SubtitleService

    service = SubtitleService()
    dto = SubtitleResponseDTO(
        job_id="sub_zip_empty",
        status="completed",
    )
    service.jobs["sub_zip_empty"] = dto
    service.engine.storage_client = None

    with (
        patch.object(service, "get_artifact_file", return_value=None),
        patch("os.path.exists", return_value=False),
        patch("os.makedirs"),
        patch("builtins.open", mock_open()),
        patch("zipfile.ZipFile") as mock_zip,
    ):
        res = service.create_job_zip_package("sub_zip_empty")
        assert res is not None
        assert "subtitles_sub_zip__package.zip" in res


def test_embed_soft_subtitles_ffmpeg_file_not_found():
    """Tests file not found checks in embed_soft_subtitles_ffmpeg."""
    from src.custom.subtitles.subtitle_service import PodcastSubtitleEngine

    engine = PodcastSubtitleEngine()
    with patch("os.path.exists", return_value=False):
        with pytest.raises(FileNotFoundError):
            engine.embed_soft_subtitles_ffmpeg(
                "/nonexistent/video.mp4", "/tmp/sub.vtt", "/tmp/out.mp4"
            )


def test_burn_subtitles_ffmpeg_file_not_found():
    """Tests file not found checks in burn_subtitles_ffmpeg."""
    from src.custom.subtitles.subtitle_service import PodcastSubtitleEngine

    engine = PodcastSubtitleEngine()
    with patch("os.path.exists", return_value=False):
        with pytest.raises(FileNotFoundError):
            engine.burn_subtitles_ffmpeg(
                "/nonexistent/video.mp4", "/tmp/sub.srt", "/tmp/out.mp4"
            )


def test_process_video_gcs_and_callbacks():
    """Tests process_video with progress callbacks and fallback branches."""
    from src.custom.subtitles.subtitle_service import PodcastSubtitleEngine

    engine = PodcastSubtitleEngine()
    progress_updates = []

    def callback(step, pct):
        progress_updates.append((step, pct))

    with (
        patch.object(
            engine,
            "transcribe_chirp3",
            return_value={
                "full_text": "Hello world.",
                "words": [
                    {
                        "word": "Hello",
                        "start_offset": 0.0,
                        "end_offset": 0.5,
                        "confidence": 0.99,
                    },
                    {
                        "word": "world",
                        "start_offset": 0.6,
                        "end_offset": 1.0,
                        "confidence": 0.99,
                    },
                ],
            },
        ),
        patch.object(
            engine,
            "refine_gemini36",
            return_value=[{"start": 0.0, "end": 1.0, "text": "Hello world."}],
        ),
        patch.object(
            engine,
            "export_vtt_srt",
            return_value={"vtt": "/tmp/test.vtt", "srt": "/tmp/test.srt"},
        ),
        patch.object(
            engine,
            "burn_subtitles_ffmpeg",
            return_value="/tmp/test_burned.mp4",
        ),
        patch.object(
            engine,
            "embed_soft_subtitles_ffmpeg",
            return_value="/tmp/test_soft.mp4",
        ),
        patch.object(
            engine, "generate_thumbnail", return_value="/tmp/thumb.jpg"
        ),
        patch("os.path.exists", return_value=True),
        patch("os.makedirs"),
    ):
        res = engine.process_video(
            video_path="/tmp/video.mp4",
            job_dir="/tmp/test_job",
            generate_burned_in=True,
            progress_callback=callback,
        )
        assert res is not None
        assert res["segment_count"] == 1
        assert len(progress_updates) >= 4


def test_media_item_model_source_assets_sanitization():
    """Tests that MediaItemModel filters out malformed/dict source_assets via field_validator."""
    from src.common.schema.media_item_model import MediaItemModel

    # 1. Test with invalid dicts lacking asset_id and role
    item_data = {
        "workspace_id": 1,
        "user_email": "test@example.com",
        "mime_type": "video/mp4",
        "model": "chirp_3+gemini-2.5-flash",
        "aspect_ratio": "16:9",
        "gcs_uris": ["gs://bucket/video.mp4"],
        "source_assets": [
            {"name": "subtitles.vtt", "gcs_uri": "gs://bucket/subtitles.vtt"}
        ],
        "raw_data": {"created_via": "subtitles_studio"},
    }
    model = MediaItemModel.model_validate(item_data)
    assert model.source_assets == []

    # 2. Test with valid dicts containing asset_id and role
    item_data_valid = {
        "workspace_id": 1,
        "user_email": "test@example.com",
        "mime_type": "video/mp4",
        "model": "chirp_3+gemini-2.5-flash",
        "aspect_ratio": "16:9",
        "gcs_uris": ["gs://bucket/video.mp4"],
        "source_assets": [{"asset_id": 123, "role": "input"}],
        "raw_data": {},
    }
    model_valid = MediaItemModel.model_validate(item_data_valid)
    assert len(model_valid.source_assets) == 1
    assert model_valid.source_assets[0].asset_id == 123


@pytest.mark.asyncio
async def test_gallery_service_defensive_enrichment():
    """Tests GalleryService._enrich_source_asset_link with malformed or missing assets."""
    from src.galleries.gallery_service import GalleryService

    service = GalleryService.__new__(GalleryService)
    service.source_asset_repo = MagicMock()
    service.source_asset_repo.get_by_id = AsyncMock(return_value=None)
    service.iam_signer_credentials = MagicMock()

    # Should safely return None on invalid inputs without throwing
    assert await service._enrich_source_asset_link(None) is None
    assert await service._enrich_source_asset_link({}) is None
    assert (
        await service._enrich_source_asset_link(
            {"name": "test.vtt", "gcs_uri": "gs://..."}
        )
        is None
    )


def test_parse_speech_response():
    """Tests parse_speech_response helper with mock cloud_speech types."""
    engine = PodcastSubtitleEngine()
    empty_res = engine.parse_speech_response(None)
    assert empty_res == {"full_text": "", "words": []}

    mock_resp = MagicMock()
    mock_file = MagicMock()
    mock_file.error.code = 0
    mock_alt = MagicMock()
    mock_alt.transcript = "Hello world"
    w1 = MagicMock()
    w1.word = "Hello"
    w1.start_offset.total_seconds.return_value = 0.0
    w1.end_offset.total_seconds.return_value = 0.5
    w1.speaker_label = "1"

    w2 = MagicMock()
    w2.word = "world"
    w2.start_offset.total_seconds.return_value = 0.5
    w2.end_offset.total_seconds.return_value = 1.0
    w2.speaker_label = "1"

    mock_alt.words = [w1, w2]
    mock_result = MagicMock()
    mock_result.alternatives = [mock_alt]
    mock_file.transcript.results = [mock_result]
    mock_resp.results = {"file1": mock_file}

    parsed = engine.parse_speech_response(mock_resp)
    assert parsed["full_text"] == "Hello world"
    assert len(parsed["words"]) == 2
    assert parsed["words"][0]["word"] == "Hello"


def test_get_job_status_lro_completion():
    """Tests get_job_status polling and completing an active GCP Speech LRO."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    job.status = "processing"
    job.step = "transcribing"
    job.operation_name = "projects/123/locations/us/operations/op456"
    job.source_video_path = "gs://bucket/test.mp4"
    job.burn_subtitles = True
    service._save_job_state(job_id, job)

    mock_op_proto = MagicMock()
    mock_op_proto.done = True
    mock_op_proto.HasField.return_value = False

    service.engine.speech_client = MagicMock()
    service.engine.speech_client.operations_client.get_operation.return_value = (
        mock_op_proto
    )

    def mock_finish(jid, j, asr):
        j.status = "completed"
        j.progress = 100
        j.subtitles_vtt = "/tmp/subtitles.vtt"
        service._save_job_state(jid, j)
        return j

    with (
        patch.object(
            service.engine,
            "parse_speech_response",
            return_value={
                "full_text": "LRO finished text",
                "words": [
                    {
                        "word": "LRO",
                        "start_time": 0.0,
                        "end_time": 1.0,
                        "speaker": "Speaker 1",
                    }
                ],
            },
        ),
        patch.object(
            service,
            "_finish_job_from_asr",
            side_effect=mock_finish,
        ),
    ):
        res = service.get_job_status(job_id)
        assert res is not None
        for _ in range(50):
            if res.status == "completed":
                break
            time.sleep(0.02)
            res = service.get_job_status(job_id)

        assert res.status == "completed"
        assert res.progress == 100
        assert res.subtitles_vtt == "/tmp/subtitles.vtt"


def test_get_job_status_lro_error():
    """Tests get_job_status handling an error in GCP Speech LRO."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    job.status = "processing"
    job.step = "transcribing"
    job.operation_name = "projects/123/locations/us/operations/op_err"
    service._save_job_state(job_id, job)

    mock_op_proto = MagicMock()
    mock_op_proto.done = True
    mock_op_proto.HasField.return_value = True
    mock_op_proto.error.message = "Chirp quota exceeded"

    service.engine.speech_client = MagicMock()
    service.engine.speech_client.operations_client.get_operation.return_value = (
        mock_op_proto
    )

    res = service.get_job_status(job_id)
    assert res is not None
    assert res.status == "failed"
    assert "Chirp quota exceeded" in (res.error_message or "")


def test_get_artifact_file_all_types():
    """Tests get_artifact_file GCS resolution for all media types."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    job.subtitles_vtt = "/nonexistent/path/sub.vtt"
    service._save_job_state(job_id, job)

    mock_storage = MagicMock()
    service.engine.storage_client = mock_storage
    mock_bucket = MagicMock()
    mock_storage.bucket.return_value = mock_bucket

    b_vtt = MagicMock()
    b_vtt.name = f"subtitles_outputs/{job_id}/test.vtt"
    b_srt = MagicMock()
    b_srt.name = f"subtitles_outputs/{job_id}/test.srt"
    b_burned = MagicMock()
    b_burned.name = f"subtitles_outputs/{job_id}/output_burned_in.mp4"
    b_toggle = MagicMock()
    b_toggle.name = f"subtitles_outputs/{job_id}/output_toggleable.mp4"
    b_source = MagicMock()
    b_source.name = f"subtitles_outputs/{job_id}/source_video.mp4"
    b_thumb = MagicMock()
    b_thumb.name = f"subtitles_outputs/{job_id}/thumbnail.jpg"

    mock_bucket.list_blobs.return_value = [
        b_vtt,
        b_srt,
        b_burned,
        b_toggle,
        b_source,
        b_thumb,
    ]

    with patch("os.path.exists", return_value=True):
        assert service.get_artifact_file(job_id, "vtt") is not None
        assert service.get_artifact_file(job_id, "srt") is not None
        assert service.get_artifact_file(job_id, "burned_in_video") is not None
        assert service.get_artifact_file(job_id, "toggleable_video") is not None
        assert service.get_artifact_file(job_id, "source_video") is not None
        assert service.get_artifact_file(job_id, "thumbnail") is not None


def test_finish_job_from_asr_direct(tmp_path):
    """Tests _finish_job_from_asr execution with mocked downstream results."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir(parents=True, exist_ok=True)
    video_file = job_dir / "fake_video.mp4"
    video_file.write_bytes(b"dummy")
    job.local_output_dir = str(job_dir)
    job.source_video_path = str(video_file)
    job.burn_subtitles = True
    service._save_job_state(job_id, job)

    with (
        patch.object(
            service.engine,
            "finalize_downstream",
            return_value={
                "subtitles_vtt": "/tmp/subtitles.vtt",
                "subtitles_srt": "/tmp/subtitles.srt",
                "default_toggleable_video": "/tmp/toggleable.mp4",
                "burned_in_video": "/tmp/burned.mp4",
                "segment_count": 2,
                "transcript_text": "Direct test",
                "thumbnail_jpg": "/tmp/thumb.jpg",
            },
        ),
        patch.object(
            service, "_upload_artifact_to_gcs", return_value="gs://bucket/out"
        ),
    ):
        finished = service._finish_job_from_asr(
            job_id, job, {"full_text": "Direct test", "words": []}
        )
        assert finished.status == "completed"
        assert finished.progress == 100
        assert finished.subtitles_vtt == "/tmp/subtitles.vtt"
        assert finished.burned_in_video == "/tmp/burned.mp4"


def test_get_job_status_recovery_branch():
    """Tests recovery branch in get_job_status when job was left in formatting step."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    job.status = "processing"
    job.step = "formatting"
    job.operation_name = "projects/123/locations/us/operations/op_recov"
    service._save_job_state(job_id, job)

    mock_op_proto = MagicMock()
    mock_op_proto.done = True
    mock_op_proto.HasField.return_value = False

    service.engine.speech_client = MagicMock()
    service.engine.speech_client.operations_client.get_operation.return_value = (
        mock_op_proto
    )

    with (
        patch.object(
            service.engine,
            "parse_speech_response",
            return_value={"full_text": "Recovery text", "words": []},
        ),
        patch.object(service, "_run_async_finish") as mock_raf,
    ):
        res = service.get_job_status(job_id)
        assert res is not None
        assert job_id in service._active_finishing_jobs
        service._active_finishing_jobs.discard(job_id)


def test_run_async_finish_error_handling():
    """Tests _run_async_finish handles exceptions and records failure."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    with patch.object(
        service,
        "_finish_job_from_asr",
        side_effect=RuntimeError("FFmpeg crashed"),
    ):
        service._run_async_finish(job_id, job, {"words": []})
        assert job.status == "failed"
        assert "FFmpeg crashed" in (job.error_message or "")
        assert job_id not in service._active_finishing_jobs


def test_get_artifact_gcs_uri_and_signed_url():
    """Tests resolving GCS URI and signed URL for job artifacts."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    job.burned_in_video = (
        "gs://bucket/subtitles_outputs/sub123/output_burned_in.mp4"
    )
    job.source_video_path = (
        "gs://bucket/subtitles_outputs/sub123/source_video.mp4"
    )
    job.subtitles_vtt = "gs://bucket/subtitles_outputs/sub123/subtitles.vtt"
    service._save_job_state(job_id, job)

    assert (
        service.get_artifact_gcs_uri(job_id, "burned_in_video")
        == job.burned_in_video
    )
    assert (
        service.get_artifact_gcs_uri(job_id, "source_video")
        == job.source_video_path
    )
    assert service.get_artifact_gcs_uri(job_id, "vtt") == job.subtitles_vtt

    with patch(
        "src.auth.iam_signer_credentials_service.IamSignerCredentials.generate_presigned_url",
        return_value="https://storage.googleapis.com/signed/sub.mp4",
    ):
        signed = service.get_artifact_signed_url(job_id, "burned_in_video")
        assert signed == "https://storage.googleapis.com/signed/sub.mp4"


def test_controller_download_redirect_to_signed_url(api_client):
    """Tests GET /download/{job_id} returns 307 Temporary Redirect when presigned URL is available."""
    dto = SubtitleResponseDTO(
        job_id="sub_redirect_123",
        status="completed",
        burned_in_video="gs://bucket/subtitles_outputs/sub_redirect_123/output_burned_in.mp4",
    )
    with (
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.get_job_status",
            return_value=dto,
        ),
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.get_artifact_signed_url",
            return_value="https://storage.googleapis.com/signed_video.mp4",
        ),
    ):
        res = api_client.get(
            "/api/v1/custom/subtitles/download/sub_redirect_123?file_type=burned_in_video",
            follow_redirects=False,
        )
        assert res.status_code == 307
        assert (
            res.headers["location"]
            == "https://storage.googleapis.com/signed_video.mp4"
        )


def test_get_artifact_signed_url_blob_fallback():
    """Tests get_artifact_signed_url falling back to direct storage client blob signing."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    job.burned_in_video = (
        "gs://test_bucket/subtitles_outputs/sub123/output_burned_in.mp4"
    )
    service._save_job_state(job_id, job)

    mock_storage = MagicMock()
    service.engine.storage_client = mock_storage
    mock_bucket = MagicMock()
    mock_storage.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_blob.generate_signed_url.return_value = (
        "https://storage.googleapis.com/blob_signed.mp4"
    )

    with patch(
        "src.auth.iam_signer_credentials_service.IamSignerCredentials.generate_presigned_url",
        side_effect=RuntimeError("IAM signing unavailable"),
    ):
        signed = service.get_artifact_signed_url(job_id, "burned_in_video")
        assert signed == "https://storage.googleapis.com/blob_signed.mp4"


def test_get_artifact_gcs_uri_all_predictions():
    """Tests default GCS URI predictions for various artifact file types."""
    service = SubtitleService()
    job_id = service.create_job()
    service.engine.storage_client = None

    uri_burned = service.get_artifact_gcs_uri(job_id, "burned_in_video")
    assert uri_burned and "output_burned_in.mp4" in uri_burned

    uri_toggle = service.get_artifact_gcs_uri(job_id, "toggleable_video")
    assert uri_toggle and "output_toggleable.mp4" in uri_toggle

    uri_source = service.get_artifact_gcs_uri(job_id, "source_video")
    assert uri_source and "source_video.mp4" in uri_source

    uri_vtt = service.get_artifact_gcs_uri(job_id, "vtt")
    assert uri_vtt and "subtitles.vtt" in uri_vtt

    uri_srt = service.get_artifact_gcs_uri(job_id, "srt")
    assert uri_srt and "subtitles.srt" in uri_srt


def test_controller_download_zip_redirect_and_source_file(api_client):
    """Tests download controller ZIP redirect and source_video fallback."""
    dto = SubtitleResponseDTO(
        job_id="sub_zip_123",
        status="completed",
    )
    with (
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.get_job_status",
            return_value=dto,
        ),
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.get_artifact_signed_url",
            return_value="https://storage.googleapis.com/signed_pkg.zip",
        ),
    ):
        res = api_client.get(
            "/api/v1/custom/subtitles/download/sub_zip_123?file_type=zip",
            follow_redirects=False,
        )
        assert res.status_code == 307
        assert (
            res.headers["location"]
            == "https://storage.googleapis.com/signed_pkg.zip"
        )


def test_get_job_status_completed_enrichment_toggleable():
    """Tests get_job_status populates signed URLs for toggleable video on completion."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    job.status = "completed"
    job.burn_subtitles = False
    service._save_job_state(job_id, job)

    with patch.object(
        service,
        "get_artifact_signed_url",
        return_value="https://signed.url/item",
    ):
        enriched = service.get_job_status(job_id)
        assert enriched.status == "completed"
        assert enriched.processed_video_url == "https://signed.url/item"
        assert enriched.default_toggleable_video == "https://signed.url/item"


def test_get_artifact_gcs_uri_bucket_listing_matching():
    """Tests get_artifact_gcs_uri finding matching blobs across all file types."""
    service = SubtitleService()
    job_id = service.create_job()
    job = service.get_job_status(job_id)
    service._save_job_state(job_id, job)

    mock_storage = MagicMock()
    service.engine.storage_client = mock_storage
    mock_bucket = MagicMock()
    mock_storage.bucket.return_value = mock_bucket

    b_vtt = MagicMock()
    b_vtt.name = f"subtitles_outputs/{job_id}/captions.vtt"
    b_srt = MagicMock()
    b_srt.name = f"subtitles_outputs/{job_id}/captions.srt"
    b_burned = MagicMock()
    b_burned.name = f"subtitles_outputs/{job_id}/output_burned_in.mp4"
    b_toggle = MagicMock()
    b_toggle.name = f"subtitles_outputs/{job_id}/output_toggleable.mp4"
    b_source = MagicMock()
    b_source.name = f"subtitles_outputs/{job_id}/source_video.mp4"
    b_thumb = MagicMock()
    b_thumb.name = f"subtitles_outputs/{job_id}/thumbnail.jpg"
    b_zip = MagicMock()
    b_zip.name = f"subtitles_outputs/{job_id}/package.zip"

    mock_bucket.list_blobs.return_value = [
        b_vtt,
        b_srt,
        b_burned,
        b_toggle,
        b_source,
        b_thumb,
        b_zip,
    ]

    assert "captions.vtt" in (service.get_artifact_gcs_uri(job_id, "vtt") or "")
    assert "captions.srt" in (service.get_artifact_gcs_uri(job_id, "srt") or "")
    assert "output_burned_in.mp4" in (
        service.get_artifact_gcs_uri(job_id, "burned_in_video") or ""
    )
    assert "output_toggleable.mp4" in (
        service.get_artifact_gcs_uri(job_id, "toggleable_video") or ""
    )
    assert "source_video.mp4" in (
        service.get_artifact_gcs_uri(job_id, "source_video") or ""
    )
    assert "thumbnail.jpg" in (
        service.get_artifact_gcs_uri(job_id, "thumbnail") or ""
    )
    assert "package.zip" in (service.get_artifact_gcs_uri(job_id, "zip") or "")


def test_controller_generate_youtube_failure_and_multipart(api_client):
    """Tests controller failure handling for YouTube download errors in JSON and multipart."""
    with patch(
        "src.custom.subtitles.subtitle_controller.subtitle_service.engine.download_youtube_audio",
        side_effect=RuntimeError("YouTube download blocked"),
    ):
        res_json = api_client.post(
            "/api/v1/custom/subtitles/generate",
            json={"video_url": "https://www.youtube.com/watch?v=err123"},
        )
        assert res_json.status_code == 400
        assert "YouTube" in res_json.json()["detail"]

        res_form = api_client.post(
            "/api/v1/custom/subtitles/generate",
            data={"video_url": "https://www.youtube.com/watch?v=err123"},
        )
        assert res_form.status_code == 400
        assert "YouTube" in res_form.json()["detail"]


def test_controller_download_zip_fallback(api_client, tmp_path):
    """Tests controller ZIP download fallback when signed URL is not present."""
    fake_zip = tmp_path / "fake.zip"
    fake_zip.write_bytes(b"PK00fake")
    dto = SubtitleResponseDTO(
        job_id="sub_zip_fallback",
        status="completed",
    )
    with (
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.get_job_status",
            return_value=dto,
        ),
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.get_artifact_signed_url",
            return_value=None,
        ),
        patch(
            "src.custom.subtitles.subtitle_controller.subtitle_service.create_job_zip_package",
            return_value=str(fake_zip),
        ),
    ):
        res = api_client.get(
            "/api/v1/custom/subtitles/download/sub_zip_fallback?file_type=zip",
            follow_redirects=False,
        )
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"
