"""Abstract base for all output adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from tlmend.models import Chapter


class OutputAdapter(ABC):
    @abstractmethod
    def write(self, chapters: list[Chapter], dest: Path) -> None:
        """Write *chapters* to *dest*."""
