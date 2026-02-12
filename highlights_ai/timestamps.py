"""Timestamp normalization and merging of highlight segments."""

from dataclasses import dataclass

from .chunking import ChunkMapping
from .gemini_analysis import HighlightMoment


@dataclass
class GlobalSegment:
    """A highlight segment in original video time, with optional label."""

    start_sec: float
    end_sec: float
    reason: str = ""


def normalize_to_original_time(
    mapping: ChunkMapping,
    moments: list[HighlightMoment],
) -> list[GlobalSegment]:
    """Convert chunk-relative moments to original video timestamps."""
    segments: list[GlobalSegment] = []
    orig_start = mapping.original_video_start_time
    chunk_end = mapping.chunk_end_time
    for m in moments:
        # Clamp to chunk bounds
        local_start = max(0.0, min(m.start_sec, chunk_end))
        local_end = max(local_start, min(m.end_sec, chunk_end))
        if local_end <= local_start:
            continue
        segments.append(
            GlobalSegment(
                start_sec=orig_start + local_start,
                end_sec=orig_start + local_end,
                reason=m.reason,
            )
        )
    return segments


def merge_overlapping_or_adjacent(
    segments: list[GlobalSegment],
    gap_sec: float = 2.0,
) -> list[GlobalSegment]:
    """
    Merge segments that overlap or are within gap_sec of each other.
    Preserves chronological order. For merged segments, reason is from the first.
    """
    if not segments:
        return []
    sorted_segs = sorted(segments, key=lambda s: (s.start_sec, s.end_sec))
    merged: list[GlobalSegment] = [sorted_segs[0]]
    for s in sorted_segs[1:]:
        last = merged[-1]
        if s.start_sec <= last.end_sec + gap_sec:
            # Overlap or adjacent: extend last
            merged[-1] = GlobalSegment(
                start_sec=last.start_sec,
                end_sec=max(last.end_sec, s.end_sec),
                reason=last.reason,
            )
        else:
            merged.append(s)
    return merged


def cap_total_duration(
    segments: list[GlobalSegment],
    max_duration_sec: float,
) -> list[GlobalSegment]:
    """
    Trim or drop segments so total duration does not exceed max_duration_sec.
    Keeps segments in order; may shorten the last included segment.
    """
    total = 0.0
    result: list[GlobalSegment] = []
    for s in segments:
        seg_dur = s.end_sec - s.start_sec
        if total + seg_dur <= max_duration_sec:
            result.append(s)
            total += seg_dur
        else:
            remaining = max_duration_sec - total
            if remaining > 1.0:  # include at least 1 second
                result.append(
                    GlobalSegment(
                        start_sec=s.start_sec,
                        end_sec=s.start_sec + remaining,
                        reason=s.reason,
                    )
                )
            break
    return result
