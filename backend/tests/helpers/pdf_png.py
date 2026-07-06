"""PDF inspection helpers for drawing-quality tests (pymupdf-based)."""

import colorsys

import fitz


def pdf_pages(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


def pdf_page_text(pdf_bytes: bytes, page: int) -> str:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc[page].get_text()


def render_page_png(pdf_bytes: bytes, page: int, zoom: float = 1.5) -> bytes:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        pix = doc[page].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")


def mean_saturation(png_bytes: bytes) -> float:
    # Decode via pymupdf to avoid a PIL dependency; sample every 8th pixel.
    pix = fitz.Pixmap(png_bytes)
    if pix.alpha:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    stride, n = pix.stride, pix.n
    samples = pix.samples
    total = 0.0
    count = 0
    for y in range(0, pix.height, 8):
        row = y * stride
        for x in range(0, pix.width, 8):
            o = row + x * n
            r, g, b = samples[o] / 255, samples[o + 1] / 255, samples[o + 2] / 255
            total += colorsys.rgb_to_hsv(r, g, b)[1]
            count += 1
    return total / count if count else 0.0
