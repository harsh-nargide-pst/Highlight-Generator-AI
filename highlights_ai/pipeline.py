"""End-to-end pipeline: source video → highlight video via Gemini."""

import logging
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from .chunking import build_chunk_mappings
from .config import HighlightConfig
from .gemini_analysis import get_chunk_highlights
from .highlight_build import build_highlight_video
from .timestamps import (
    GlobalSegment,
    cap_total_duration,
    merge_overlapping_or_adjacent,
    normalize_to_original_time,
)

logger = logging.getLogger(__name__)


def sec_to_mmss(sec: float) -> str:
    return str(timedelta(seconds=int(sec)))


def run_pipeline(config: HighlightConfig) -> dict:
    """
    Run full pipeline and return summary with paths and segment info.
    Chunk videos are stored in output_dir/chunks/<output_basename>/.
    Final highlight is written to output_dir/<output_basename>.mp4.
    """
    if not config.video_path or not Path(config.video_path).is_file():
        raise FileNotFoundError(f"Video file not found: {config.video_path}")
    if not (config.gemini_api_key or os.environ.get("GEMINI_API_KEY")):
        raise ValueError("Set GEMINI_API_KEY in environment or pass --api-key")

    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Persistent folder for all chunk videos (so no round/iteration is missed)
    chunks_dir = out_dir / "chunks" / config.output_basename
    chunks_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Chunks will be saved to: %s", chunks_dir.resolve())

    all_global_segments: list[GlobalSegment] = []

    # --- Step 1: Chunking (entire video; every part covered with overlap) ---
    logger.info("=" * 60)
    logger.info("STEP 1: Chunking source video (full video, overlapping chunks)")
    logger.info("  Source: %s", config.video_path)
    logger.info("  Chunk duration: %.0fs, Overlap: %.0fs", config.chunk_duration_sec, config.chunk_overlap_sec)

    mappings, total_duration = build_chunk_mappings(
        config.video_path,
        str(chunks_dir),
        config.chunk_duration_sec,
        config.chunk_overlap_sec,
    )

    logger.info("  Total duration: %s (%.1fs)", sec_to_mmss(total_duration), total_duration)
    logger.info("  Number of chunks: %d (covers full video, no rounds missed)", len(mappings))
    for m in mappings:
        logger.info("    Chunk %d: %s - %s -> %s", m.chunk_index, sec_to_mmss(m.original_video_start_time), sec_to_mmss(m.original_video_end_time), Path(m.chunk_file_path).name)

    # --- Step 2 & 3: Gemini per chunk + normalize to original time ---
    logger.info("=" * 60)
    logger.info("STEP 2: Analyzing each chunk with Gemini (model: %s)", config.gemini_model)

    for i, m in enumerate(mappings):
        chunk_range = f"{sec_to_mmss(m.original_video_start_time)} - {sec_to_mmss(m.original_video_end_time)}"
        logger.info("--- Chunk %d/%d [%s] ---", i + 1, len(mappings), chunk_range)
        logger.info("  File: %s", Path(m.chunk_file_path).name)

        moments, raw_output = get_chunk_highlights(m, config.gemini_model, config.gemini_api_key)

        logger.info("  Gemini output:\n%s", raw_output.strip() or "(empty)")
        logger.info("  Parsed moments: %d", len(moments))
        for mo in moments:
            logger.info("    [chunk time] %.1fs - %.1fs: %s", mo.start_sec, mo.end_sec, mo.reason)

        segments = normalize_to_original_time(m, moments)
        all_global_segments.extend(segments)

    # --- Step 4: Merge and cap ---
    logger.info("=" * 60)
    logger.info("STEP 3: Normalizing timestamps and merging segments")
    logger.info("  Total segments from all chunks: %d", len(all_global_segments))

    merged = merge_overlapping_or_adjacent(all_global_segments)
    logger.info("  After merging overlapping/adjacent: %d segments", len(merged))

    capped = cap_total_duration(merged, config.highlight_max_duration_sec)
    total_highlight_dur = sum(s.end_sec - s.start_sec for s in capped)
    logger.info("  After capping to %.0fs: %d segments, total %.1fs", config.highlight_max_duration_sec, len(capped), total_highlight_dur)

    # --- Step 5: Build highlight video (use temp dir for segment clips only) ---
    highlight_path = str(out_dir / f"{config.output_basename}.mp4")
    logger.info("=" * 60)
    logger.info("STEP 4: Building highlight video")
    logger.info("  Output path: %s", highlight_path)

    with tempfile.TemporaryDirectory(prefix="highlight_segments_") as seg_work_dir:
        logger.info("  Extracting segments from original video and concatenating...")
        build_highlight_video(
            config.video_path,
            capped,
            highlight_path,
            seg_work_dir,
            config.crossfade_duration_sec,
        )

    logger.info("  Done. Highlight written to: %s", highlight_path)
    logger.info("=" * 60)

    return {
        "source_video": config.video_path,
        "source_duration_sec": total_duration,
        "chunks_dir": str(chunks_dir.resolve()),
        "highlight_video_path": highlight_path,
        "highlight_duration_sec": total_highlight_dur,
        "segments": [
            {
                "start_sec": s.start_sec,
                "end_sec": s.end_sec,
                "start_time": sec_to_mmss(s.start_sec),
                "end_time": sec_to_mmss(s.end_sec),
                "reason": s.reason,
            }
            for s in capped
        ],
        "num_chunks": len(mappings),
    }


def print_summary(result: dict) -> None:
    """Print optional summary of selected timestamps and duration."""
    print("=" * 60)
    print("HIGHLIGHT GENERATION COMPLETE")
    print("=" * 60)
    print(f"Source:        {result['source_video']}")
    print(f"Source length: {sec_to_mmss(result['source_duration_sec'])}")
    print(f"Chunks saved:   {result.get('chunks_dir', 'N/A')}")
    print(f"Highlight:     {result['highlight_video_path']}")
    print(f"Highlight len: {sec_to_mmss(result['highlight_duration_sec'])} ({result['highlight_duration_sec']:.1f}s)")
    print(f"Chunks analyzed: {result['num_chunks']}")
    print("\nSelected segments:")
    for seg in result["segments"]:
        print(f"  {seg['start_time']} - {seg['end_time']}  {seg['reason']}")
    print()
