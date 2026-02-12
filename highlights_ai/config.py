"""Configuration for video highlight generation using Gemini API."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HighlightConfig:
    """Configuration for the highlight pipeline."""

    # Input
    video_path: str = ""
    output_dir: str = "output"
    output_basename: str = "highlights"

    # Chunking (Step 2)
    chunk_duration_sec: float = 90.0  # 60–120 seconds per chunk
    chunk_overlap_sec: float = 8.0  # 5–10 seconds overlap

    # Target highlight duration (Step 5)
    highlight_max_duration_sec: float = 240.0  # 4 minutes
    highlight_min_duration_sec: float = 180.0  # 3 minutes (soft target)

    # Transitions
    crossfade_duration_sec: float = 0.5  # crossfade between segments

    # Gemini
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))

    def __post_init__(self) -> None:
        self.video_path = str(Path(self.video_path).resolve()) if self.video_path else ""
        self.output_dir = str(Path(self.output_dir).resolve())
