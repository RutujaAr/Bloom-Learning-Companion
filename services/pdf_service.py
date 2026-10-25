import re
import pymupdf as fitz

# Single configurable content limit for textbook documents & pasted text
MAX_TEXTBOOK_WORDS = 8000

def count_words(text: str) -> int:
    """Return count of whitespace-delimited words."""
    if not text:
        return 0
    return len(text.split())

def enforce_word_limit(text: str, max_words: int = MAX_TEXTBOOK_WORDS):
    """
    Accept only the first max_words words of a text.
    Returns:
    - accepted_text: str
    - total_words: int
    - is_truncated: bool
    """
    if not text:
        return "", 0, False
    words = text.split()
    total_words = len(words)
    if total_words <= max_words:
        return text, total_words, False
    accepted_text = " ".join(words[:max_words])
    return accepted_text, total_words, True

def extract_pdf_text(file_bytes):
    """
    Extract text from PDF file bytes with error handling for empty,
    damaged, or image-only documents.
    """
    if not file_bytes:
        return "", "Empty file. Please provide a valid PDF document with text."
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            if len(doc) == 0:
                return "", "The PDF document contains 0 pages."
            pages = []
            for i, page in enumerate(doc):
                text = page.get_text("text")
                if text.strip():
                    pages.append(f"[Page {i+1}]\n{text}")
            if not pages:
                return "", f"The document has {len(doc)} page(s), but contains no selectable text. It may be a scanned image document without OCR."
            extracted = "\n\n".join(pages)
            info = f"{len(doc)} page(s), {len(extracted):,} characters extracted"
            return extracted, info
    except Exception:
        return "", "The PDF could not be read. It may be corrupted, unsupported, or password-protected."

def find_relevant_context(full_text, question="", max_chars=18000):
    """Select relevant pages matching query keywords; fallback to start."""
    if not full_text:
        return ""
    if len(full_text) <= max_chars:
        return full_text

    pages = full_text.split("\n\n[Page ")
    if len(pages) <= 1:
        return full_text[:max_chars]

    formatted_pages = []
    for idx, p in enumerate(pages):
        page_str = p if idx == 0 else f"[Page {p}"
        formatted_pages.append(page_str)

    words = [w.lower() for w in re.findall(r"\b[A-Za-z0-9_-]{3,}\b", question) if len(w) > 3]
    if not words:
        return full_text[:max_chars]

    scored = []
    for page in formatted_pages:
        score = sum(1 for w in words if w in page.lower())
        scored.append((score, page))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = []
    total_len = 0
    for score, page in scored:
        if total_len + len(page) > max_chars and selected:
            break
        selected.append(page)
        total_len += len(page)

    return "\n\n".join(selected)

def search_text_by_keywords(text: str, query: str, max_results: int = 5):
    """
    Non-AI keyword search mode:
    Extracts the most relevant paragraphs matching terms in the student's query.
    Returns list of dicts with 'excerpt', 'matches', and 'score'.
    """
    if not text or not query:
        return []

    stop_words = {
        "what", "when", "where", "which", "who", "whom", "whose", "why",
        "how", "is", "are", "was", "were", "the", "a", "an", "and", "or",
        "in", "on", "at", "to", "for", "from", "by", "with", "about",
        "does", "did", "can", "could", "would", "should", "explain", "describe"
    }

    raw_terms = re.findall(r"\b[A-Za-z0-9_-]{3,}\b", query.lower())
    terms = [t for t in raw_terms if t not in stop_words]
    if not terms:
        terms = raw_terms if raw_terms else [query.lower().strip()]

    # Break text into paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
    if len(paragraphs) < 3:
        paragraphs = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 30]

    scored = []
    for p in paragraphs:
        p_lower = p.lower()
        matched = [t for t in terms if t in p_lower]
        if matched:
            score = sum(p_lower.count(t) for t in matched)
            scored.append({
                "excerpt": p,
                "matches": matched,
                "score": score
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:max_results]
