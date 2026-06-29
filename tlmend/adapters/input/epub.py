"""EPUB input adapter — stdlib only (zipfile + xml.etree).

Reads the OPF spine for document order, then parses each XHTML chapter file
to extract title and paragraphs.
"""

from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from tlmend.adapters.input.base import InputAdapter
from tlmend.models import Chapter, Paragraph

_XHTML = "http://www.w3.org/1999/xhtml"
_OPF   = "http://www.idpf.org/2007/opf"
_CONT  = "urn:oasis:names:tc:opendocument:xmlns:container"


class EpubAdapter(InputAdapter):
    def load(self, path: Path) -> list[Chapter]:
        with zipfile.ZipFile(path) as zf:
            opf_path = _find_opf(zf)
            spine_hrefs = _spine_hrefs(zf, opf_path)

            chapters: list[Chapter] = []
            for chapter_index, href in enumerate(spine_hrefs):
                full = str(Path(opf_path).parent / href)
                if full not in zf.namelist():
                    continue
                ch = _parse_html(zf.read(full), str(chapter_index))
                if ch is not None:
                    chapters.append(ch)

        return chapters


def _find_opf(zf: zipfile.ZipFile) -> str:
    container = ET.fromstring(zf.read("META-INF/container.xml"))
    el = container.find(f".//{{{_CONT}}}rootfile")
    if el is None:
        raise ValueError("No rootfile in container.xml")
    return el.get("full-path", "")


def _spine_hrefs(zf: zipfile.ZipFile, opf_path: str) -> list[str]:
    opf = ET.fromstring(zf.read(opf_path))
    manifest: dict[str, str] = {
        item.get("id", ""): item.get("href", "")
        for item in opf.findall(f".//{{{_OPF}}}item")
    }
    return [
        manifest[ref.get("idref", "")]
        for ref in opf.findall(f".//{{{_OPF}}}itemref")
        if ref.get("idref", "") in manifest
    ]


def _parse_html(data: bytes, chapter_id: str) -> Chapter | None:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    title = _extract_title(root)
    paragraphs = _extract_paragraphs(root)

    if not paragraphs:
        return None

    return Chapter(id=chapter_id, title=title, paragraphs=paragraphs)


def _extract_title(root: ET.Element) -> str:
    for h2 in root.iter(f"{{{_XHTML}}}h2"):
        cls = h2.get("class", "")
        if "chapter-title" in cls:
            return "".join(h2.itertext()).strip()
    el = root.find(f".//{{{_XHTML}}}title")
    return "".join(el.itertext()).strip() if el is not None else ""


def _extract_paragraphs(root: ET.Element) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    idx = 0
    for p in root.iter(f"{{{_XHTML}}}p"):
        text = "".join(p.itertext()).strip()
        if not text:
            continue
        # skip the bold duplicate-title paragraph that some exporters inject
        children = list(p)
        if (
            len(children) == 1
            and children[0].tag == f"{{{_XHTML}}}strong"
            and text.startswith("Chapter")
        ):
            continue
        paragraphs.append(Paragraph(index=idx, text=text))
        idx += 1
    return paragraphs
