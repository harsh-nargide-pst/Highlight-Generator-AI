"""Build highlight video from selected segments with smooth transitions."""

import subprocess
from pathlib import Path

from .timestamps import GlobalSegment


def extract_segment(
    source_video: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
) -> None:
    """Extract one segment from source video (re-encode for accurate cuts)."""
    duration = end_sec - start_sec
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_sec),
            "-i",
            source_video,
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


def build_concat_list_with_crossfade(
    segment_paths: list[str],
    crossfade_duration_sec: float,
    work_dir: str,
) -> str:
    """
    Build FFmpeg filter_complex for concat with crossfade between segments.
    Returns path to the output file (we'll create it in the same step).
    """
    if not segment_paths:
        raise ValueError("No segment paths")
    if len(segment_paths) == 1:
        return segment_paths[0]

    concat_file = Path(work_dir) / "concat_list.txt"
    with open(concat_file, "w") as f:
        for p in segment_paths:
            f.write(f"file '{Path(p).resolve()}'\n")
    return str(concat_file)


def build_highlight_video(
    source_video: str,
    segments: list[GlobalSegment],
    output_path: str,
    work_dir: str,
    crossfade_duration_sec: float = 0.5,
) -> None:
    """
    Extract each segment, concatenate with optional fades, write final highlight video.
    Uses concat demuxer; applies fade_in at start and fade_out at end of the whole highlight.
    """
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    segment_files: list[str] = []
    for i, seg in enumerate(segments):
        seg_path = str(Path(work_dir) / f"seg_{i:04d}.mp4")
        extract_segment(source_video, seg.start_sec, seg.end_sec, seg_path)
        segment_files.append(seg_path)

    if not segment_files:
        raise ValueError("No segments to concatenate")

    output_path = str(Path(output_path).resolve())
    if len(segment_files) == 1:
        # Single segment: just add brief fade in/out for smoothness
        seg_path = segment_files[0]
        dur = segments[0].end_sec - segments[0].start_sec
        fade_dur = min(crossfade_duration_sec, dur / 4)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                seg_path,
                "-vf",
                f"fade=t=in:st=0:d={fade_dur},fade=t=out:st={dur - fade_dur}:d={fade_dur}",
                "-af",
                f"afade=t=in:st=0:d={fade_dur},afade=t=out:st={dur - fade_dur}:d={fade_dur}",
                "-c:a",
                "aac",
                output_path,
            ],
            capture_output=True,
            check=True,
        )
        return

    # Multiple segments: concat demuxer then global fade in/out
    concat_list = Path(work_dir) / "concat_list.txt"
    with open(concat_list, "w") as f:
        for p in segment_files:
            f.write(f"file '{Path(p).resolve()}'\n")

    temp_concat = str(Path(work_dir) / "temp_concat.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            temp_concat,
        ],
        capture_output=True,
        check=True,
    )

    # Get duration of concatenated file for fade out
    out_probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            temp_concat,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    total_dur = float(out_probe.stdout.strip())
    fade_dur = min(crossfade_duration_sec, total_dur / 4)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            temp_concat,
            "-vf",
            f"fade=t=in:st=0:d={fade_dur},fade=t=out:st={total_dur - fade_dur}:d={fade_dur}",
            "-af",
            f"afade=t=in:st=0:d={fade_dur},afade=t=out:st={total_dur - fade_dur}:d={fade_dur}",
            "-c:a",
            "aac",
            output_path,
        ],
        capture_output=True,
        check=True,
    )
