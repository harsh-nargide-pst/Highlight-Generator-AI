# HighlightsAI — Video Highlight Generation (Gemini API)

Generate a **3–4 minute highlight video** from a **30–40 minute source video** using the Google Gemini API. The pipeline chunks the video, asks Gemini for highlight-worthy moments, then cuts and concatenates those segments with smooth transitions.

---

## Requirements

- **Python 3.10+**
- **FFmpeg** — `apt install ffmpeg` (Linux) or `brew install ffmpeg` (macOS)
- **Gemini API key** — [Create one](https://aistudio.google.com/apikey)

---

## Setup

### Option A: Poetry (recommended)

```bash
cd HighlightsAI
poetry install
```

If Poetry is not installed: `pip install poetry` or see [poetry.org](https://python-poetry.org/docs/#installation).

### Option B: pip

```bash
cd HighlightsAI
pip install -r requirements.txt
```

---

## Run

1. **Set your API key**

   ```bash
   export GEMINI_API_KEY=your_api_key_here
   ```

2. **Generate highlights**

   ```bash
   poetry run highlight /path/to/your_video.mp4
   ```

   With pip (and no Poetry):

   ```bash
   python run_highlight.py /path/to/your_video.mp4
   ```

3. **Output**

   - **Final highlight:** `output/highlights.mp4` (or `--output-dir` / `--output`).
   - **Chunk videos:** All small chunks are saved under `output/chunks/<output_basename>/` (e.g. `output/chunks/highlights/chunk_0000_00m00s_01m30s.mp4`). The full video is chunked so every part (all rounds/iterations) is analyzed; nothing is skipped.
   - **Logs:** Progress is logged (chunk ranges, Gemini output per chunk, merge/cap steps). Each chunk’s raw Gemini response is printed so you can see what was selected.
   - A short summary of selected segments and timestamps is printed at the end (unless `--quiet`).

### Example

```bash
export GEMINI_API_KEY=your_key
poetry run highlight ~/Videos/game.mp4 --output-dir ./out --output my_highlights
```

### Command-line options

| Option | Default | Description |
|--------|---------|-------------|
| `--output-dir`, `-o` | `output` | Output directory |
| `--output` | `highlights` | Output filename (no extension) |
| `--chunk-duration` | 90 | Chunk length (seconds) |
| `--chunk-overlap` | 8 | Overlap between chunks (seconds) |
| `--max-highlight-duration` | 240 | Max highlight length (seconds, 4 min) |
| `--crossfade` | 0.5 | Fade duration (seconds) |
| `--model` | gemini-2.5-flash | Gemini model |
| `--api-key` | (env) | API key (or set `GEMINI_API_KEY`) |
| `--quiet` | — | Only print output path |

---

## Pipeline overview

1. **Chunk** — Split the **entire** source into overlapping segments (e.g. 90 s with 8 s overlap). All chunks are written to `output/chunks/<basename>/` so no part of the video (e.g. multiple rounds/iterations) is missed.
2. **Analyze** — Upload each chunk to Gemini; get highlight moments (start/end + label) per chunk. Logs show each chunk’s time range and Gemini’s raw output.
3. **Normalize** — Map chunk timestamps to original video; merge nearby segments; cap total duration.
4. **Build** — Extract selected segments from the original video, concatenate with fades, write the final highlight to `output/<basename>.mp4`.

---

## Processing details

All of the following use the **defaults**; you can override them via CLI (see [Command-line options](#command-line-options)) or in code via `HighlightConfig`.

### Model

| Setting | Default | Description |
|--------|---------|-------------|
| **Gemini model** | `gemini-2.5-flash` | Model used for analyzing each video chunk (vision + text). |

### Chunking (source video → small clips)

| Setting | Default | Unit | Description |
|--------|---------|------|-------------|
| **Chunk duration** | 90 | seconds (1 min 30 s) | Length of each small clip sent to Gemini. |
| **Chunk overlap** | 8 | seconds | Overlap between two consecutive chunks. |

**How overlapping works:**

- **Step size** = chunk duration − overlap = 90 − 8 = **82 seconds**.
- Chunk 0: 0:00–1:30 (0–90 s)  
- Chunk 1: 1:22–2:52 (82–172 s)  
- Chunk 2: 2:44–4:14 (164–254 s)  
- …and so on to the end of the video.
- So each chunk is **90 s long**, and the next chunk starts **82 s** after the previous one (8 s of overlap). This keeps context at boundaries and avoids missing moments between chunks.

**Chunk files:** Each clip is extracted with FFmpeg (re-encode: `libx264` video, `aac` audio), saved as `chunk_0000_00m00s_01m30s.mp4`, etc., under `output/chunks/<basename>/`.

### Gemini analysis (per chunk)

- Each chunk is **uploaded** via the Gemini Files API.
- The pipeline **waits** until the file state is **ACTIVE** (required before use): polls every **5 s**, up to **5 minutes** per chunk. If still not ACTIVE, that chunk fails with a timeout.
- The **prompt** asks the model for highlight-worthy moments in that clip, with **start time (seconds)** and **end time (seconds)** *within the chunk* and a short label (e.g. “goal scored”).
- **Output format** expected: one line per moment, `MOMENT: start_sec end_sec reason`. If none, the model may reply `NONE`.

### Timestamp normalization

- Gemini returns times **relative to the chunk** (0 = start of that chunk).
- For each moment: **original_video_time** = **chunk_original_start_time** + **chunk_relative_time**.
- Segments from all chunks are merged: any two segments that **overlap** or are within **2 seconds** of each other are merged into one (so we don’t cut in the middle of an event).
- Total highlight duration is **capped** at the max duration (default 4 min); segments are trimmed/dropped from the end as needed.

### Highlight duration & transitions

| Setting | Default | Description |
|--------|---------|-------------|
| **Max highlight duration** | 240 s (4 min) | Hard cap on final highlight length. |
| **Crossfade / fade duration** | 0.5 s | Fade-in at the start and fade-out at the end of the final video (smooth transitions). |

### Output paths

| Output | Path |
|--------|------|
| **Chunk videos** | `output/chunks/<output_basename>/` (e.g. `output/chunks/highlights/`) |
| **Final highlight** | `output/<output_basename>.mp4` (e.g. `output/highlights.mp4`) |

### Summary of defaults (quick reference)

- **Model:** `gemini-2.5-flash`
- **Chunk:** 90 s (1.5 min) per clip, 8 s overlap → step 82 s.
- **Merge gap:** 2 s (merge segments within 2 s).
- **Highlight cap:** 240 s (4 min); fade 0.5 s.
- **File wait:** poll every 5 s, timeout 300 s (5 min) per chunk.

---

## Using the package in code

```python
from highlights_ai.config import HighlightConfig
from highlights_ai.pipeline import run_pipeline, print_summary

config = HighlightConfig(
    video_path="/path/to/video.mp4",
    output_dir="output",
    output_basename="highlights",
)
result = run_pipeline(config)
print_summary(result)
```

---

## Project layout

```
HighlightsAI/
├── README.md           # This file (setup & run)
├── pyproject.toml      # Poetry / project config
├── requirements.txt    # Pip dependencies
├── run_highlight.py    # CLI entry (wrapper)
└── highlights_ai/      # Main package
    ├── config.py
    ├── chunking.py
    ├── gemini_analysis.py
    ├── timestamps.py
    ├── highlight_build.py
    ├── pipeline.py
    └── run_highlight.py
```

After a run, under your output directory:

```
output/
├── chunks/
│   └── highlights/                    # All chunk videos (full coverage)
│       ├── chunk_0000_00m00s_01m30s.mp4
│       ├── chunk_0001_01m22s_02m52s.mp4
│       └── ...
└── highlights.mp4                    # Final highlight video
```

---

## Notes

- **Runtime:** For a 30–40 min video, expect roughly **1–2 hours** (upload + Gemini processing per chunk).
- **File state:** Uploaded chunks are polled until Gemini marks them ACTIVE before analysis.
- Output is written to the path you choose (default: `output/highlights.mp4`).
