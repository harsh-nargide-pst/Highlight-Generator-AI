"""Video chunking with overlap and timestamp mapping for Gemini processing."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChunkMapping:
    """Timestamp mapping for one chunk."""

    original_video_start_time: float  # seconds in source video
    original_video_end_time: float
    chunk_start_time: float  # always 0 for the chunk's own timeline
    chunk_end_time: float  # duration of this chunk
    chunk_index: int
    chunk_file_path: str  # path to extracted chunk video file


def get_video_duration_sec(path: str) -> float:
    """Return duration of video in seconds using ffprobe."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def build_chunks_with_overlap(
    duration_sec: float,
    chunk_duration_sec: float,
    overlap_sec: float,
) -> list[tuple[float, float]]:
    """
    Build chunk intervals (start_sec, end_sec) with overlap.
    Step size = chunk_duration_sec - overlap_sec.
    """
    if overlap_sec >= chunk_duration_sec:
        raise ValueError("overlap_sec must be smaller than chunk_duration_sec")
    step = chunk_duration_sec - overlap_sec
    chunks: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_sec:
        end = min(start + chunk_duration_sec, duration_sec)
        chunks.append((start, end))
        if end >= duration_sec:
            break
        start += step
    return chunks


def extract_chunk_video(
    source_video_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
) -> None:
    """Extract a segment of the source video to a new file (re-encode for clean cuts)."""
    duration = end_sec - start_sec
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_sec),
            "-i",
            source_video_path,
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-avoid_negative_ts",
            "1",
            output_path,
        ],
        capture_output=True,
        check=True,
    )


def _time_label(sec: float) -> str:
    """Format seconds as 00m00s for use in filenames."""
    m = int(sec) // 60
    s = int(sec) % 60
    return f"{m:02d}m{s:02d}s"


def build_chunk_mappings(
    source_video_path: str,
    work_dir: str,
    chunk_duration_sec: float,
    overlap_sec: float,
) -> tuple[list[ChunkMapping], float]:
    """
    Get video duration, build overlapping chunks, and extract each chunk to a file.
    Returns list of ChunkMapping and total duration.
    Chunk files are named: chunk_0000_00m00s_01m30s.mp4 (index_start_end).
    """
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    duration_sec = get_video_duration_sec(source_video_path)
    intervals = build_chunks_with_overlap(duration_sec, chunk_duration_sec, overlap_sec)
    mappings: list[ChunkMapping] = []
    for i, (start, end) in enumerate(intervals):
        chunk_dur = end - start
        label = f"chunk_{i:04d}_{_time_label(start)}_{_time_label(end)}.mp4"
        out_path = str(Path(work_dir) / label)
        extract_chunk_video(source_video_path, start, end, out_path)
        mappings.append(
            ChunkMapping(
                original_video_start_time=start,
                original_video_end_time=end,
                chunk_start_time=0.0,
                chunk_end_time=chunk_dur,
                chunk_index=i,
                chunk_file_path=out_path,
            )
        )
    return mappings, duration_sec
