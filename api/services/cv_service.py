import asyncio
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi import HTTPException, status
from pypdf import PdfReader

MAX_CV_BYTES = 5 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 200_000
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt"}
_executor = ProcessPoolExecutor(max_workers=2)


def _extract_text(data: bytes, suffix: str) -> str:
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".docx":
        document = Document(BytesIO(data))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    else:
        text = data.decode("utf-8", errors="replace")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())[
        :MAX_EXTRACTED_CHARACTERS
    ]


def _validate_magic(data: bytes, suffix: str) -> None:
    valid = (
        (suffix == ".pdf" and data.startswith(b"%PDF"))
        or (suffix == ".docx" and data.startswith(b"PK"))
        or (suffix == ".txt" and b"\x00" not in data[:1024])
    )
    if not valid:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "File content does not match type",
        )


async def extract_cv(filename: str | None, data: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Only PDF, DOCX and TXT are allowed",
        )
    if not data or len(data) > MAX_CV_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "CV must be between 1 byte and 5 MB",
        )
    _validate_magic(data, suffix)
    loop = asyncio.get_running_loop()
    try:
        text = await loop.run_in_executor(_executor, _extract_text, data, suffix)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Could not extract CV text",
        ) from exc
    if len(text) < 30:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "CV contains too little readable text",
        )
    return text
