#!/usr/bin/env python3
"""
Video Highlight Generation Using Gemini API

Generate a 3–4 minute highlight video from a 30–40 minute source video by:
  - Chunking with overlapping timestamps
  - Analyzing each chunk with Gemini
  - Normalizing and merging segments
  - Building the highlight with smooth transitions

Usage:
  export GEMINI_API_KEY=your_key
  poetry run highlight /path/to/source_video.mp4 [--output-dir DIR] [--output NAME]
"""

import argparse
import logging
import os
from pathlib import Path

from .config import HighlightConfig
from .pipeline import run_pipeline, print_summary


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Reduce noise from third-party loggers
    logging.getLogger("google").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description="Generate highlight video from a long source video using Gemini API."
    )
    parser.add_argument(
        "video_path",
        type=str,
        help="Absolute or relative path to the source video (30–40 min recommended).",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="output",
        help="Directory for the output highlight video (default: output).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="highlights",
        help="Base name for output file, without extension (default: highlights).",
    )
    parser.add_argument(
        "--chunk-duration",
        type=float,
        default=90,
        help="Chunk duration in seconds (default: 90).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=float,
        default=8,
        help="Overlap between adjacent chunks in seconds (default: 8).",
    )
    parser.add_argument(
        "--max-highlight-duration",
        type=float,
        default=240,
        help="Maximum highlight duration in seconds (default: 240 = 4 min).",
    )
    parser.add_argument(
        "--crossfade",
        type=float,
        default=0.5,
        help="Crossfade/fade duration in seconds (default: 0.5).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash",
        help="Gemini model name (default: gemini-2.5-flash).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default="",
        help="Gemini API key (or set GEMINI_API_KEY).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print segment summary.",
    )
    args = parser.parse_args()

    video_path = str(Path(args.video_path).resolve())
    if not Path(video_path).is_file():
        raise SystemExit(f"Video file not found: {video_path}")

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "")
    config = HighlightConfig(
        video_path=video_path,
        output_dir=args.output_dir,
        output_basename=args.output,
        chunk_duration_sec=args.chunk_duration,
        chunk_overlap_sec=args.chunk_overlap,
        highlight_max_duration_sec=args.max_highlight_duration,
        crossfade_duration_sec=args.crossfade,
        gemini_model=args.model,
        gemini_api_key=api_key,
    )

    result = run_pipeline(config)
    if not args.quiet:
        print_summary(result)
    print(result["highlight_video_path"])


if __name__ == "__main__":
    main()
