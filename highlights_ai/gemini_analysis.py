"""Gemini-based video analysis: identify highlight-worthy segments per chunk."""

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .chunking import ChunkMapping

logger = logging.getLogger(__name__)

# Poll until file is ACTIVE (video processing can take a while)
FILE_ACTIVE_WAIT_TIMEOUT_SEC = 300  # 5 minutes per chunk
FILE_ACTIVE_POLL_INTERVAL_SEC = 5

# Prompt for Gemini: chunk-relative timestamps, one segment per line
PROMPT = """You are analyzing a short video clip that is part of a longer video.

Identify the most important, engaging, or highlight-worthy moments in this clip.
For each such moment, give:
- start time in seconds (within this clip, 0 = start of clip)
- end time in seconds (within this clip)
- a short reason or label (e.g. "goal scored", "key save", "celebration")

Output format: exactly one line per moment:
MOMENT: start_sec end_sec reason_or_label

Use decimal seconds if needed (e.g. 12.5 18.0). If there are no clear highlight moments in this clip, reply with exactly:
NONE

Do not include any other text or headers. Only lines in the form "MOMENT: start_sec end_sec description" or the word NONE."""


@dataclass
class HighlightMoment:
    """A single highlight segment in chunk-relative time."""

    start_sec: float
    end_sec: float
    reason: str


def parse_moments(text: str) -> list[HighlightMoment]:
    """Parse Gemini response into list of (start_sec, end_sec, reason) in chunk-local time."""
    moments: list[HighlightMoment] = []
    if not text or "NONE" in text.upper():
        return moments
    for line in text.strip().split("\n"):
        line = line.strip()
        m = re.match(r"MOMENT:\s*([\d.]+)\s+([\d.]+)\s+(.+)", line, re.I)
        if m:
            start = float(m.group(1))
            end = float(m.group(2))
            reason = m.group(3).strip()
            if end > start and start >= 0:
                moments.append(HighlightMoment(start_sec=start, end_sec=end, reason=reason))
    return moments


def _wait_for_file_active(client, file_name: str) -> None:
    """Poll until the file is in ACTIVE state; raise if FAILED or timeout."""
    from google.genai import types

    active_val = getattr(types.FileState, "ACTIVE", "ACTIVE")
    failed_val = getattr(types.FileState, "FAILED", "FAILED")

    def _state_str(s):
        if s is None:
            return None
        return getattr(s, "value", s) if hasattr(s, "value") else str(s)

    deadline = time.monotonic() + FILE_ACTIVE_WAIT_TIMEOUT_SEC
    file_resource = None
    while time.monotonic() < deadline:
        file_resource = client.files.get(name=file_name)
        state = _state_str(getattr(file_resource, "state", None))
        if state == active_val or state == "ACTIVE":
            return
        if state == failed_val or state == "FAILED":
            err = getattr(file_resource, "error", None)
            msg = str(err) if err else "File processing failed"
            raise RuntimeError(f"Gemini file processing failed: {msg}")
        time.sleep(FILE_ACTIVE_POLL_INTERVAL_SEC)
    last = _state_str(getattr(file_resource, "state", None)) if file_resource else "unknown"
    raise TimeoutError(
        f"File did not become ACTIVE within {FILE_ACTIVE_WAIT_TIMEOUT_SEC}s (last state: {last})"
    )


def analyze_chunk_with_gemini(
    chunk_file_path: str,
    model: str,
    api_key: str,
) -> str:
    """
    Send one chunk video to Gemini and return raw text response.
    Uses Files API for upload (handles >20MB / longer clips).
    Waits for file to reach ACTIVE state before calling generate_content.
    """
    from google import genai

    client = genai.Client(api_key=api_key or None)  # None => use env GEMINI_API_KEY
    path = Path(chunk_file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Chunk file not found: {chunk_file_path}")

    # Upload file (Files API for reliability with larger chunks)
    logger.info("Uploading chunk to Gemini Files API: %s", path.name)
    uploaded = client.files.upload(file=str(path))
    file_name = getattr(uploaded, "name", None)
    if not file_name:
        raise RuntimeError("Upload did not return a file name")
    # Wait until file is ACTIVE (required before generate_content)
    logger.info("Waiting for file to reach ACTIVE state (polling every %ss)...", FILE_ACTIVE_POLL_INTERVAL_SEC)
    _wait_for_file_active(client, file_name)
    logger.info("File is ACTIVE, calling Gemini for analysis.")

    response = client.models.generate_content(
        model=model,
        contents=[uploaded, PROMPT],
    )
    if not response or not response.text:
        return "NONE"
    return response.text


def get_chunk_highlights(
    mapping: ChunkMapping,
    model: str,
    api_key: str,
) -> tuple[list[HighlightMoment], str]:
    """Run Gemini on one chunk; return (parsed moments, raw response text)."""
    raw = analyze_chunk_with_gemini(mapping.chunk_file_path, model, api_key)
    moments = parse_moments(raw)
    return moments, raw
