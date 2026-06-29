"""Diff and classify hunks between original and edited paragraphs.

Pure difflib — no LLM. Given the same inputs the output is deterministic.
"""

from __future__ import annotations

import difflib
import re

from tlmend.models import Chapter, Hunk, HunkClass, Paragraph

# Changes touching only these patterns are mechanical.
_MECHANICAL_RE = re.compile(
    r"^[\s​ ,\.;:!?\"\'\(\)\[\]\-–—]+$",
    re.UNICODE,
)

# Threshold: if proposed shrinks by more than this fraction → substantive
SHRINK_THRESHOLD = 0.15


def diff_chapter(original: Chapter, edited_paragraphs: list[str]) -> list[Hunk]:
    """Return hunks for paragraphs that changed between *original* and *edited_paragraphs*."""
    orig_texts = [p.text for p in original.paragraphs]

    if len(edited_paragraphs) != len(orig_texts):
        raise ValueError(
            f"Paragraph count mismatch: original={len(orig_texts)}, "
            f"edited={len(edited_paragraphs)}"
        )

    hunks: list[Hunk] = []
    for i, (orig, edited) in enumerate(zip(orig_texts, edited_paragraphs)):
        if orig == edited:
            continue
        hunks.append(Hunk(
            index=i,
            original=orig,
            proposed=edited,
            classification=_classify(orig, edited),
        ))
    return hunks


def _classify(original: str, proposed: str) -> HunkClass:
    """Return MECHANICAL if only whitespace/punctuation changed, else SUBSTANTIVE."""
    if _is_mass_shrink(original, proposed):
        return HunkClass.SUBSTANTIVE

    matcher = difflib.SequenceMatcher(None, original, proposed, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_orig = original[i1:i2]
        changed_new = proposed[j1:j2]
        combined = changed_orig + changed_new
        if not _MECHANICAL_RE.fullmatch(combined):
            return HunkClass.SUBSTANTIVE

    return HunkClass.MECHANICAL


def _is_mass_shrink(original: str, proposed: str) -> bool:
    if not original:
        return False
    shrink = 1.0 - len(proposed) / len(original)
    return shrink > SHRINK_THRESHOLD


def apply_resolutions(chapter: Chapter, finals: dict[int, str]) -> Chapter:
    """Return a new Chapter with resolved texts applied.

    *finals* maps paragraph index → final text; unchanged paragraphs are kept as-is.
    """
    new_paragraphs = [
        Paragraph(index=p.index, text=finals.get(p.index, p.text))
        for p in chapter.paragraphs
    ]
    return Chapter(id=chapter.id, title=chapter.title, paragraphs=new_paragraphs)
