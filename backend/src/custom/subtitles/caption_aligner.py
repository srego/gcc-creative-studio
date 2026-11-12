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

"""Clean 4-stage acoustic + Viterbi broadcast subtitle alignment and segmentation."""

from __future__ import annotations

import array
import math
import os
import re
import subprocess
import wave
from typing import Any, Dict, List, Optional, Tuple


CHIRP_LANGUAGE_TOKENS = frozenset(
    {
        "english",
        "spanish",
        "french",
        "german",
        "japanese",
        "portuguese",
        "italian",
        "chinese",
        "mandarin",
        "korean",
        "hindi",
        "arabic",
        "russian",
        "dutch",
        "polish",
        "turkish",
        "vietnamese",
        "thai",
        "indonesian",
    }
)

# Function words that should not dangle at the end of a cue or top line when avoidable
WEAK_BREAK_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "to",
        "for",
        "with",
        "on",
        "at",
        "from",
        "by",
        "into",
        "onto",
        "through",
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "that",
        "which",
        "who",
        "whom",
        "whose",
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "might",
        "must",
        "my",
        "your",
        "his",
        "her",
        "its",
        "our",
        "their",
        "this",
        "these",
        "those",
        "i",
        "we",
        "he",
        "she",
        "they",
    }
)


def norm_token(word: str) -> str:
    """Lowercases and strips non-alphanumeric characters for token matching."""
    return re.sub(r"[^a-z0-9]", "", (word or "").lower())


def est_word_duration(word: str) -> float:
    """Estimates typical spoken duration (seconds) for a word."""
    clean = re.sub(
        r"[^a-zA-Z0-9\u00C0-\u024F\u3040-\u30FF\u4E00-\u9FFF]",
        "",
        word or "",
    )
    n = max(1, len(clean))
    return min(0.65, max(0.18, 0.065 * n + 0.12))


def max_word_duration(word: str) -> float:
    """Returns upper bound on single-word spoken duration before silence is inferred."""
    clean = re.sub(
        r"[^a-zA-Z0-9\u00C0-\u024F\u3040-\u30FF\u4E00-\u9FFF]",
        "",
        word or "",
    )
    n = max(1, len(clean))
    return min(1.35, max(0.55, 0.11 * n + 0.25))


def detect_acoustic_speech_islands(
    wav_path: str, frame_ms: int = 20
) -> Tuple[float, List[Tuple[float, float]]]:
    """Detects speech activity intervals from a 16kHz mono PCM WAV file.

    Uses pre-emphasized vocal-band RMS energy (attenuating low-frequency bass/music
    rumble while emphasizing speech formants and consonants), adaptive noise-floor
    thresholding, hangover smoothing, and plosive lead-in padding.
    """
    if not wav_path or not os.path.exists(wav_path):
        return 0.0, []

    try:
        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            if sampwidth != 2 or sample_rate <= 0 or n_frames <= 0:
                return 0.0, []
            duration_sec = n_frames / float(sample_rate)
            raw_bytes = wf.readframes(n_frames)
    except Exception:
        return 0.0, []

    samples = array.array("h")
    samples.frombytes(raw_bytes)
    if n_channels > 1:
        samples = samples[::n_channels]

    total_samples = len(samples)
    frame_len = max(1, int(sample_rate * frame_ms / 1000))
    if total_samples < frame_len:
        return duration_sec, [(0.0, round(duration_sec, 3))] if duration_sec > 0 else []

    energies: List[float] = []
    for offset in range(0, total_samples - frame_len + 1, frame_len):
        # First-order high-pass pre-emphasis (y[n] = x[n] - 0.95*x[n-1])
        acc = 0.0
        prev = float(samples[offset])
        for k in range(offset + 1, offset + frame_len):
            curr = float(samples[k])
            d = curr - 0.95 * prev
            acc += d * d
            prev = curr
        energies.append(math.sqrt(acc / max(1, frame_len - 1)))

    if not energies:
        return duration_sec, []

    sorted_e = sorted(energies)
    p20 = sorted_e[int(0.20 * (len(sorted_e) - 1))]
    p90 = sorted_e[int(0.90 * (len(sorted_e) - 1))]

    # If the entire clip is near-silent, return empty speech islands
    if p90 < 80.0:
        return round(duration_sec, 3), []

    threshold = max(140.0, p20 * 2.4, p20 + 0.14 * (p90 - p20))
    hangover_frames = max(1, int(140 / frame_ms))  # ~140ms trailing hangover

    active_flags = [False] * len(energies)
    hang = 0
    for idx, e in enumerate(energies):
        if e >= threshold:
            active_flags[idx] = True
            hang = hangover_frames
        elif hang > 0:
            active_flags[idx] = True
            hang -= 1

    frame_sec = frame_ms / 1000.0
    raw_islands: List[Tuple[float, float]] = []
    in_speech = False
    start_idx = 0
    for idx, is_speech in enumerate(active_flags):
        if is_speech and not in_speech:
            in_speech = True
            start_idx = idx
        elif not is_speech and in_speech:
            in_speech = False
            raw_islands.append((start_idx * frame_sec, idx * frame_sec))
    if in_speech:
        raw_islands.append((start_idx * frame_sec, len(active_flags) * frame_sec))

    # Merge intra-phrase stop-consonant micro-gaps (< 220ms) and drop < 100ms clicks
    merged: List[Tuple[float, float]] = []
    for s, e in raw_islands:
        if merged and (s - merged[-1][1]) < 0.22:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    final_islands: List[Tuple[float, float]] = []
    for s, e in merged:
        if (e - s) < 0.10:
            continue
        padded_start = round(max(0.0, s - 0.04), 3)
        padded_end = round(min(duration_sec, e + 0.04), 3)
        if final_islands and padded_start <= final_islands[-1][1]:
            final_islands[-1] = (
                final_islands[-1][0],
                max(final_islands[-1][1], padded_end),
            )
        else:
            final_islands.append((padded_start, padded_end))

    return round(duration_sec, 3), final_islands


def plan_asr_audio_chunks(
    duration_sec: float,
    speech_islands: List[Tuple[float, float]],
    max_chunk_sec: float = 840.0,
) -> List[Tuple[float, float]]:
    """Splits long audio (>14 min) at silence midpoints so Chirp 3 never hits its 20m limit."""
    if duration_sec <= 0.0:
        return [(0.0, 0.0)]
    if duration_sec <= max_chunk_sec:
        return [(0.0, round(duration_sec, 3))]

    chunks: List[Tuple[float, float]] = []
    cursor = 0.0
    min_step = max_chunk_sec * 0.5

    while cursor < duration_sec - 0.05:
        remaining = duration_sec - cursor
        if remaining <= max_chunk_sec:
            chunks.append((round(cursor, 3), round(duration_sec, 3)))
            break

        window_low = cursor + min_step
        window_high = cursor + max_chunk_sec

        # Find the widest silence gap inside [window_low, window_high]
        best_split: Optional[float] = None
        best_gap = -1.0
        for idx in range(len(speech_islands) - 1):
            gap_start = speech_islands[idx][1]
            gap_end = speech_islands[idx + 1][0]
            mid = 0.5 * (gap_start + gap_end)
            if window_low <= mid <= window_high and (gap_end - gap_start) > best_gap:
                best_gap = gap_end - gap_start
                best_split = mid

        split_at = round(best_split if best_split is not None else window_high, 3)
        chunks.append((round(cursor, 3), split_at))
        cursor = split_at

    return chunks


def slice_wav_segment(
    src_wav_path: str, dst_wav_path: str, start_sec: float, end_sec: float
) -> str:
    """Slices a [start_sec, end_sec] segment from a WAV file using FFmpeg stream copy."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-to",
        f"{end_sec:.3f}",
        "-i",
        src_wav_path,
        "-c",
        "copy",
        dst_wav_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=120)
    return dst_wav_path


def strip_chirp_prompt_leaks(
    words_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Strips Chirp 3 system/diarization prompt leaks emitted during non-speech audio."""
    if not words_data:
        return []

    filtered = [
        dict(w)
        for w in words_data
        if str(w.get("word", "")).strip() not in ("[BACKGROUND]", "{}")
    ]
    if not filtered:
        return []

    norms = [norm_token(str(w.get("word", ""))) for w in filtered]
    n = len(filtered)
    remove_mask = [False] * n
    reset_start_indices: set[int] = set()

    diarization_fewshot = ["hello", "good", "morning", "how", "are", "you"]
    diarization_intro = [
        "an",
        "example",
        "transcript",
        "with",
        "speaker",
        "annotation",
        "is",
        "as",
        "follows",
    ]

    i = 0
    while i < n:
        if norms[i : i + 5] == [
            "respond",
            "in",
            "the",
            "original",
            "language",
        ]:
            rm_start = i
            rm_end = i + 5

            for k in range(len(diarization_fewshot), 1, -1):
                if (
                    rm_start >= k
                    and norms[rm_start - k : rm_start]
                    == diarization_fewshot[-k:]
                ):
                    rm_start -= k
                    break

            if (
                rm_start >= len(diarization_intro)
                and norms[rm_start - len(diarization_intro) : rm_start]
                == diarization_intro
            ):
                rm_start -= len(diarization_intro)

            if norms[rm_end : rm_end + 3] == ["of", "the", "speech"]:
                speech_raw = str(filtered[rm_end + 2].get("word", "")).strip()
                rm_end += 3
                if rm_end < n and (
                    norms[rm_end] in CHIRP_LANGUAGE_TOKENS
                    or speech_raw.endswith(",")
                ):
                    rm_end += 1

            if norms[rm_end : rm_end + 8] == [
                "please",
                "directly",
                "output",
                "the",
                "final",
                "answer",
                "in",
                "json",
            ]:
                rm_end += 8

            for idx in range(rm_start, min(rm_end, n)):
                remove_mask[idx] = True
            if rm_end < n:
                reset_start_indices.add(rm_end)
            i = rm_end
            continue

        if norms[i : i + 5] == [
            "transcribe",
            "the",
            "following",
            "speech",
            "segment",
        ]:
            for idx in range(i, min(i + 5, n)):
                remove_mask[idx] = True
            if i + 5 < n:
                reset_start_indices.add(i + 5)
            i += 5
            continue

        i += 1

    cleaned: List[Dict[str, Any]] = []
    for idx, item in enumerate(filtered):
        if remove_mask[idx]:
            continue
        if idx in reset_start_indices:
            item["_reset_start"] = True
        cleaned.append(item)
    return cleaned


def _find_island_for_end_time(
    end_sec: float, speech_islands: List[Tuple[float, float]]
) -> Optional[Tuple[float, float]]:
    """Finds the acoustic speech island containing (or nearest within 0.35s of) end_sec."""
    for s, e in speech_islands:
        if (s - 0.12) <= end_sec <= (e + 0.25):
            return (s, e)
    best: Optional[Tuple[float, float]] = None
    best_dist = 0.35
    for s, e in speech_islands:
        dist = min(abs(end_sec - s), abs(end_sec - e))
        if dist < best_dist:
            best_dist = dist
            best = (s, e)
    return best


def align_words_to_acoustics(
    words_data: List[Dict[str, Any]],
    speech_islands: Optional[List[Tuple[float, float]]] = None,
) -> List[Dict[str, Any]]:
    """Snaps Chirp 3 word timestamps to acoustic speech islands and clamps pause stretches."""
    cleaned = strip_chirp_prompt_leaks(words_data)
    if not cleaned:
        return []

    islands = speech_islands or []
    aligned: List[Dict[str, Any]] = []
    prev_end = 0.0
    n = len(cleaned)
    i = 0

    while i < n:
        # Group consecutive words where intermediate end_time == 0.0
        j = i
        while j < n - 1 and float(cleaned[j].get("end_time", 0.0)) <= 0.0:
            j += 1

        group = [dict(w) for w in cleaned[i : j + 1]]
        reset_start = any(bool(w.pop("_reset_start", False)) for w in group)
        raw_start = float(group[0].get("start_time", 0.0))
        group_end = float(group[-1].get("end_time", 0.0))

        est_durs = [est_word_duration(str(w.get("word", ""))) for w in group]
        max_durs = [max_word_duration(str(w.get("word", ""))) for w in group]
        sum_est = sum(est_durs)
        sum_max = sum(max_durs)

        if group_end <= 0.0 or group_end < prev_end:
            group_start = prev_end
            group_end = prev_end + sum_est
        else:
            effective_start = max(raw_start, prev_end)

            # 1. Check measured acoustic speech island onset first
            matched_island = (
                _find_island_for_end_time(group_end, islands)
                if islands
                else None
            )
            if (
                matched_island is not None
                and matched_island[0] > effective_start + 0.22
                and matched_island[0] < group_end
            ):
                # Chirp 3 stretched start_offset backward across a real acoustic silence gap!
                effective_start = max(effective_start, matched_island[0])

            # 2. Defense-in-depth duration clamp (e.g. if background music bridged a pause)
            if (
                reset_start
                or raw_start > group_end
                or (group_end - effective_start) > sum_max
            ):
                acoustic_floor = (
                    matched_island[0]
                    if (
                        matched_island is not None
                        and prev_end <= matched_island[0] < group_end
                    )
                    else prev_end
                )
                group_start = max(acoustic_floor, group_end - sum_est)
            else:
                group_start = effective_start

            if group_end <= group_start:
                group_end = group_start + max(0.12 * len(group), sum_est)

        total_span = max(0.05, group_end - group_start)
        curr_t = group_start
        for k, w_item in enumerate(group):
            frac = est_durs[k] / sum_est if sum_est > 0 else 1.0 / len(group)
            w_end = (
                group_end
                if k == len(group) - 1
                else curr_t + total_span * frac
            )
            w_item["start_time"] = round(curr_t, 3)
            w_item["end_time"] = round(w_end, 3)
            aligned.append(w_item)
            curr_t = w_end

        prev_end = round(group_end, 3)
        i = j + 1

    return aligned


def format_balanced_lines(
    words_slice: List[str], max_line_chars: int = 42
) -> Optional[Tuple[str, float]]:
    """Formats a sequence of words into 1 or 2 balanced lines (<= max_line_chars each).

    Returns (formatted_text, line_layout_cost), or None if words cannot fit in 2 lines.
    """
    if not words_slice:
        return None

    joined = " ".join(words_slice).strip()
    if len(joined) <= max_line_chars:
        return joined, 0.0

    # Try every 2-line split point k (words[0:k] on line 1, words[k:] on line 2)
    if len(words_slice) < 2:
        return None

    best_text: Optional[str] = None
    best_cost = float("inf")

    for k in range(1, len(words_slice)):
        line1 = " ".join(words_slice[:k])
        line2 = " ".join(words_slice[k:])
        if len(line1) > max_line_chars or len(line2) > max_line_chars:
            continue

        # Prefer balanced lines with slight preference for bottom-heavy pyramid (len2 >= len1)
        diff = abs(len(line2) - len(line1))
        top_heavy_penalty = 6.0 if len(line1) > len(line2) + 4 else 0.0

        last_w1 = words_slice[k - 1]
        clean_w1 = norm_token(last_w1)
        punct_bonus = (
            -10.0
            if last_w1.endswith((",", ";", ":", "—", "-", ".", "?", "!"))
            else 0.0
        )
        weak_word_penalty = (
            28.0
            if clean_w1 in WEAK_BREAK_WORDS and not last_w1.endswith((",", ";", "."))
            else 0.0
        )

        cost = 8.0 + diff * 1.1 + top_heavy_penalty + punct_bonus + weak_word_penalty
        if cost < best_cost:
            best_cost = cost
            best_text = f"{line1}\n{line2}"

    if best_text is None:
        return None
    return best_text, max(0.0, best_cost)


def _segment_utterance_dp(
    utterance: List[Dict[str, Any]], max_line_chars: int = 42
) -> List[Dict[str, Any]]:
    """Finds minimum-cost broadcast cues within a pause-bounded utterance via Viterbi DP."""
    m = len(utterance)
    if m == 0:
        return []

    word_strs = [str(w.get("word", "")).strip() for w in utterance]
    speaker = str(utterance[0].get("speaker", "Speaker 1"))

    dp = [float("inf")] * (m + 1)
    back: List[Tuple[int, str]] = [(-1, "")] * (m + 1)
    dp[0] = 0.0

    max_words_per_cue = 22
    target_chars = 52.0
    target_cps = 16.0

    for i in range(m):
        if dp[i] == float("inf"):
            continue
        for j in range(i + 1, min(m, i + max_words_per_cue) + 1):
            w_slice = word_strs[i:j]
            formatted = format_balanced_lines(w_slice, max_line_chars=max_line_chars)
            if formatted is None:
                # Handle pathological single token > max_line_chars
                if j == i + 1 and len(w_slice[0]) > max_line_chars:
                    formatted = (w_slice[0][:max_line_chars], 50.0)
                else:
                    continue

            cue_text, layout_cost = formatted
            char_count = len(cue_text.replace("\n", " "))
            start_t = float(utterance[i].get("start_time", 0.0))
            end_t = float(utterance[j - 1].get("end_time", start_t + 0.5))
            dur = max(0.15, end_t - start_t)
            cps = char_count / dur

            # 1. Cadence & duration penalties
            dur_cost = 0.0
            if dur < 1.0 and j < m:
                dur_cost += (1.0 - dur) * 45.0
            if dur > 5.2:
                dur_cost += (dur - 5.2) * 55.0
            if cps > 20.0:
                dur_cost += (cps - 20.0) * 14.0
            elif cps > target_cps:
                dur_cost += (cps - target_cps) * 3.0

            # 2. Length fullness (avoid tiny 1-2 word micro-cues unless utterance ends)
            len_cost = 0.0
            if j < m and char_count < 22:
                len_cost += (22 - char_count) * 2.4
            else:
                len_cost += abs(char_count - target_chars) * 0.25

            # 3. Syntactic & prosodic break quality at word j-1
            break_cost = 0.0
            if j < m:
                last_word = word_strs[j - 1]
                clean_last = norm_token(last_word)
                gap_after = max(
                    0.0,
                    float(utterance[j].get("start_time", end_t)) - end_t,
                )

                if last_word.endswith((".", "?", "!", '."', '?"', '!"')):
                    break_cost += 0.0
                elif last_word.endswith((",", ";", ":", "—", "-")):
                    break_cost += 12.0
                elif clean_last in WEAK_BREAK_WORDS:
                    break_cost += 95.0
                else:
                    break_cost += 34.0

                # Reward breaking at natural micro-pauses (150ms-450ms)
                if gap_after >= 0.15:
                    break_cost -= min(24.0, gap_after * 60.0)

                # Discourage wrapping across two separate sentences inside one cue
                internal_sentence_breaks = sum(
                    1
                    for w in w_slice[:-1]
                    if w.endswith((".", "?", "!", '."', '?"', '!"'))
                )
                break_cost += internal_sentence_breaks * 18.0

            total_cost = dp[i] + 16.0 + layout_cost + dur_cost + len_cost + break_cost
            if total_cost < dp[j]:
                dp[j] = total_cost
                back[j] = (i, cue_text)

    # Reconstruct optimal cues
    cues: List[Dict[str, Any]] = []
    curr = m
    while curr > 0:
        prev_idx, cue_text = back[curr]
        if prev_idx < 0:
            break
        cues.append(
            {
                "speaker": speaker,
                "start_time": round(float(utterance[prev_idx]["start_time"]), 3),
                "end_time": round(float(utterance[curr - 1]["end_time"]), 3),
                "text": cue_text,
            }
        )
        curr = prev_idx

    cues.reverse()
    return cues


def segment_cues_viterbi(
    words_data: List[Dict[str, Any]],
    max_line_chars: int = 42,
    pause_break_sec: float = 0.45,
) -> List[Dict[str, Any]]:
    """Segments aligned words into 2-line broadcast cues with min-hold and anti-flicker polish."""
    if not words_data:
        return []

    # 1. Partition into continuous utterances at real pauses (>= 0.45s) or speaker changes
    utterances: List[List[Dict[str, Any]]] = []
    curr_utt: List[Dict[str, Any]] = [words_data[0]]

    for item in words_data[1:]:
        prev = curr_utt[-1]
        gap = float(item.get("start_time", 0.0)) - float(
            prev.get("end_time", 0.0)
        )
        same_speaker = item.get("speaker", "Speaker 1") == prev.get(
            "speaker", "Speaker 1"
        )
        if gap >= pause_break_sec or not same_speaker:
            utterances.append(curr_utt)
            curr_utt = [item]
        else:
            curr_utt.append(item)
    if curr_utt:
        utterances.append(curr_utt)

    # 2. Run Viterbi DP inside each utterance
    raw_cues: List[Dict[str, Any]] = []
    for utt in utterances:
        raw_cues.extend(_segment_utterance_dp(utt, max_line_chars=max_line_chars))

    if not raw_cues:
        return []

    # 3. Broadcast timing polish: minimum reading hold into trailing silence + anti-flicker bridging
    polished: List[Dict[str, Any]] = []
    for idx, cue in enumerate(raw_cues):
        start_t = float(cue["start_time"])
        end_t = float(cue["end_time"])
        text = str(cue["text"]).strip()
        next_start = (
            float(raw_cues[idx + 1]["start_time"])
            if idx + 1 < len(raw_cues)
            else None
        )

        min_hold = max(0.85, min(1.35, len(text.replace("\n", " ")) * 0.055))
        if (end_t - start_t) < min_hold:
            desired_end = start_t + min_hold
            # Borrow up to 0.30s of trailing silence without colliding with next cue
            max_allowed = end_t + 0.30
            if next_start is not None:
                max_allowed = min(max_allowed, next_start - 0.06)
            end_t = max(end_t, min(desired_end, max_allowed))

        # Anti-flicker: bridge tiny breath gaps (<= 160ms) to a clean 40ms 1-frame step
        if next_start is not None:
            gap = next_start - end_t
            if 0.04 < gap <= 0.16:
                end_t = next_start - 0.04

        if end_t <= start_t:
            end_t = start_t + 0.35

        polished.append(
            {
                "speaker": cue.get("speaker", "Speaker 1"),
                "start_time": round(start_t, 3),
                "end_time": round(end_t, 3),
                "text": text,
            }
        )

    return polished


def parse_vtt_cues(vtt_content: str) -> List[Dict[str, Any]]:
    """Parses a WebVTT string into structured cue dicts [{index, start_time, end_time, text}]."""
    if not vtt_content:
        return []

    def _ts_to_sec(ts: str) -> float:
        clean = ts.strip().replace(",", ".")
        parts = clean.split(":")
        try:
            if len(parts) == 3:
                return (
                    float(parts[0]) * 3600.0
                    + float(parts[1]) * 60.0
                    + float(parts[2])
                )
            if len(parts) == 2:
                return float(parts[0]) * 60.0 + float(parts[1])
        except ValueError:
            return 0.0
        return 0.0

    blocks = re.split(r"\r?\n\s*\r?\n", vtt_content.strip())
    cues: List[Dict[str, Any]] = []
    cue_idx = 1
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines or lines[0].startswith("WEBVTT"):
            continue
        arrow_idx = next(
            (idx for idx, ln in enumerate(lines) if "-->" in ln), -1
        )
        if arrow_idx < 0:
            continue
        raw_start, raw_end_rest = lines[arrow_idx].split("-->", 1)
        raw_end = raw_end_rest.strip().split()[0] if raw_end_rest.strip() else ""
        start_sec = round(_ts_to_sec(raw_start), 3)
        end_sec = round(_ts_to_sec(raw_end), 3)
        text = "\n".join(lines[arrow_idx + 1 :]).strip()
        if text and end_sec >= start_sec:
            cues.append(
                {
                    "index": cue_idx,
                    "start_time": start_sec,
                    "end_time": end_sec,
                    "text": text,
                }
            )
            cue_idx += 1
    return cues
