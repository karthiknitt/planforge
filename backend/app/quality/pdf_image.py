"""Render a PDF page to PNG bytes — reference images for AI renders and
dev-time visual checks. pymupdf only; no API calls."""

from __future__ import annotations

import fitz  # pymupdf


def pdf_page_png(pdf_bytes: bytes, page_idx: int = 0, scale: float = 1.5) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[min(page_idx, len(doc) - 1)]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB)
        return pix.tobytes("png")
    finally:
        doc.close()
