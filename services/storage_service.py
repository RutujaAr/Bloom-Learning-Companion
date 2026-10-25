import os
import re
import hashlib
from pathlib import Path

# Private upload directory inside workspace
BASE_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
UPLOAD_BASE_DIR = BASE_UPLOAD_DIR
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


class StoredPdfPath(str):
    """String subclass that also allows dict-like access for backwards compatibility."""
    def __new__(cls, path_str, metadata=None):
        instance = super().__new__(cls, path_str)
        instance.metadata = metadata or {}
        return instance

    def __getitem__(self, key):
        if isinstance(key, str) and key in self.metadata:
            return self.metadata[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        return self.metadata.get(key, default)


def get_student_upload_dir(student_id: int) -> Path:
    """Return the private, owner-scoped upload directory for a student."""
    p = BASE_UPLOAD_DIR / f"student_{student_id}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_filename(name: str) -> str:
    """Sanitize filename to prevent directory traversal and invalid characters."""
    clean = re.sub(r"[^\w\.-]", "_", Path(name).name)
    return clean[:100] or "document.pdf"


def validate_pdf_bytes(file_bytes: bytes, filename: str = None) -> tuple[bool, str]:
    """Validate uploaded file size and PDF magic bytes."""
    if not file_bytes:
        return False, "Uploaded file is empty (0 bytes)."
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return False, f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
    if not file_bytes.startswith(b"%PDF"):
        return False, "File is not a valid PDF document (missing %PDF signature)."
    return True, ""


def save_uploaded_pdf(student_id: int, arg2, arg3=None) -> StoredPdfPath:
    """
    Safely store a PDF in private student-scoped storage.
    Accepts (student_id, bytes, filename) or (student_id, filename, bytes).
    """
    if isinstance(arg2, (bytes, bytearray)):
        file_bytes = bytes(arg2)
        original_filename = str(arg3 or "document.pdf")
    else:
        original_filename = str(arg2 or "document.pdf")
        file_bytes = bytes(arg3 or b"")

    valid, err_msg = validate_pdf_bytes(file_bytes, original_filename)
    if not valid:
        raise ValueError(err_msg)

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    safe_name = sanitize_filename(original_filename)
    target_dir = get_student_upload_dir(student_id)
    target_path = target_dir / f"{file_hash[:12]}_{safe_name}"

    # Write file atomically if not already present
    if not target_path.exists():
        target_path.write_bytes(file_bytes)

    meta = {
        "file_path": str(target_path),
        "file_hash": file_hash,
        "file_size": len(file_bytes),
        "safe_name": safe_name
    }
    return StoredPdfPath(str(target_path), meta)


def delete_stored_pdf(arg1, arg2) -> bool:
    """
    Safely delete a stored PDF if it belongs to the authenticated student's directory.
    Accepts (student_id, file_path) or (file_path, student_id).
    """
    if isinstance(arg1, int) or (isinstance(arg1, str) and arg1.isdigit()):
        student_id = int(arg1)
        file_path = str(arg2 or "")
    else:
        file_path = str(arg1 or "")
        student_id = int(arg2 or 0)

    if not file_path:
        return False
    try:
        p = Path(file_path).resolve()
        student_dir = get_student_upload_dir(student_id).resolve()
        if (student_dir in p.parents or p.parent == student_dir) and p.exists() and p.is_file():
            p.unlink()
            return True
    except Exception:
        pass
    return False
