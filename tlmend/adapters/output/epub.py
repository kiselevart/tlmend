"""EPUB output adapter — patches the original EPUB with corrected paragraph text.

Strategy: copy every file from the template EPUB verbatim; for spine XHTML
files that have a corrected Chapter, replace only the <p> text content.
Everything else (CSS, fonts, images, metadata, NCX, cover) is preserved exactly.
"""

from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from tlmend.adapters.input.epub import _find_opf, _spine_hrefs
from tlmend.adapters.output.base import OutputAdapter
from tlmend.models import Chapter

_XHTML = "http://www.w3.org/1999/xhtml"

# Suppress "ns0:" prefixes so serialized XHTML stays readable.
ET.register_namespace("", _XHTML)
ET.register_namespace("epub", "http://www.idpf.org/2007/epub")


class EpubOutputAdapter(OutputAdapter):
    """Write corrected chapters back into the template EPUB structure."""

    def __init__(self, template_path: Path) -> None:
        self._template = template_path

    def write(self, chapters: list[Chapter], dest: Path) -> None:
        chapter_map: dict[str, Chapter] = {ch.id: ch for ch in chapters}

        with zipfile.ZipFile(self._template) as src:
            opf_path = _find_opf(src)
            spine_hrefs = _spine_hrefs(src, opf_path)
            opf_dir = Path(opf_path).parent

            # Map zip-internal path → chapter id (mirrors EpubAdapter's indexing)
            path_to_id: dict[str, str] = {
                str(opf_dir / href): str(i)
                for i, href in enumerate(spine_hrefs)
            }

            dest.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as dst:
                # mimetype must be the first entry and stored uncompressed.
                if "mimetype" in src.namelist():
                    dst.writestr(
                        zipfile.ZipInfo("mimetype"),
                        src.read("mimetype"),
                        compress_type=zipfile.ZIP_STORED,
                    )

                for info in src.infolist():
                    if info.filename == "mimetype":
                        continue
                    data = src.read(info.filename)
                    cid = path_to_id.get(info.filename)
                    if cid is not None and cid in chapter_map:
                        data = _patch_xhtml(data, chapter_map[cid])
                    dst.writestr(info, data)


def _patch_xhtml(data: bytes, chapter: Chapter) -> bytes:
    """Replace paragraph text in an XHTML document with corrected text."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data

    para_iter = iter(chapter.paragraphs)
    for p in root.iter(f"{{{_XHTML}}}p"):
        text = "".join(p.itertext()).strip()
        if not text:
            continue
        # Mirror the skip logic in EpubAdapter._extract_paragraphs
        children = list(p)
        if (
            len(children) == 1
            and children[0].tag == f"{{{_XHTML}}}strong"
            and text.startswith("Chapter")
        ):
            continue

        try:
            corrected = next(para_iter)
        except StopIteration:
            break

        if corrected.text != text:
            for child in list(p):
                p.remove(child)
            p.text = corrected.text

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
