"""Abstract base for all input adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from tlmend.models import Chapter


class InputAdapter(ABC):
    """Parse a source file/directory into canonical chapters."""

    @abstractmethod
    def load(self, path: Path) -> list[Chapter]:
        """Return ordered chapters from *path*."""
