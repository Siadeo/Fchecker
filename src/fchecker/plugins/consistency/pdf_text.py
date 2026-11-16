"""Extraction du texte visible d'un PDF.

pypdf (pur Python) et non pypdfium2 : deux copies natives de pdfium dans le même processus
(pypdfium2 + celle de QtPdf, utilisée par la visionneuse) provoquaient des crashs aléatoires.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)

_SPACES = str.maketrans({" ": " ", " ": " ", " ": " ", " ": " ", "−": "-"})


def extract_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # PDF exotique : on renvoie ce qu'on peut (vide → constat COH-10)
        log.warning("Extraction du texte PDF impossible : %s", exc)
        return ""
    return normalize("\n".join(parts))


def normalize(text: str) -> str:
    return text.translate(_SPACES).replace("\r\n", "\n").replace("\r", "\n")
