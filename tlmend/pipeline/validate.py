"""Validation gates — pure code, no LLM.

All four invariants must pass before a chapter can advance to ASSEMBLED.
"""

from __future__ import annotations

from dataclasses import dataclass

from tlmend.models import Chapter


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]


def validate(
    original: Chapter,
    resolved: Chapter,
    glossary_terms: list[str],
) -> ValidationResult:
    errors: list[str] = []

    _check_paragraph_count(original, resolved, errors)
    _check_no_empty_paragraphs(resolved, errors)
    _check_glossary(original, resolved, glossary_terms, errors)

    return ValidationResult(ok=len(errors) == 0, errors=errors)


def _check_paragraph_count(original: Chapter, resolved: Chapter, errors: list[str]) -> None:
    if len(original.paragraphs) != len(resolved.paragraphs):
        errors.append(
            f"Paragraph count mismatch: original={len(original.paragraphs)}, "
            f"resolved={len(resolved.paragraphs)}"
        )


def _check_no_empty_paragraphs(chapter: Chapter, errors: list[str]) -> None:
    for p in chapter.paragraphs:
        if not p.text.strip():
            errors.append(f"Paragraph {p.index} is empty after resolution")


def _check_glossary(
    original: Chapter, resolved: Chapter, terms: list[str], errors: list[str]
) -> None:
    orig_text = " ".join(p.text for p in original.paragraphs)
    resolved_text = " ".join(p.text for p in resolved.paragraphs)
    for term in terms:
        if term.lower() in orig_text.lower() and term.lower() not in resolved_text.lower():
            errors.append(f"Glossary term missing from output: '{term}'")
