"""Assembly stage — reconstruct a Chapter from resolutions and write output."""

from __future__ import annotations

from tlmend.models import Chapter, Resolution
from tlmend.pipeline.diff_classify import apply_resolutions


def assemble_chapter(original: Chapter, resolutions: list[Resolution]) -> Chapter:
    """Apply resolutions to *original* and return the final Chapter."""
    finals = {r.hunk.index: r.final_text for r in resolutions}
    return apply_resolutions(original, finals)
