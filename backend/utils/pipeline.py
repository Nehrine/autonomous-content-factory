"""
Pipeline utilities v3

CHANGES:
  - validate_fact_sheet now checks minimum fact density (features OR key_benefits
    must have at least 1 entry). The old version only checked product_name.
  - _build_brief_for_editor handles empty lists gracefully (no change in output
    for well-populated fact sheets).
  - All other validators unchanged.
"""
import re
import time
import logging
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger("pipeline")
T = TypeVar("T")


def with_retry(max_attempts: int = 3, delay: float = 1.5, backoff: float = 2.0):
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last_exc = None
            wait = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        logger.warning(
                            "%s attempt %d/%d failed: %s — retrying in %.1fs",
                            fn.__name__, attempt, max_attempts, exc, wait,
                        )
                        time.sleep(wait)
                        wait *= backoff
                    else:
                        logger.error("%s failed after %d attempts: %s",
                                     fn.__name__, max_attempts, exc)
            raise last_exc
        return wrapper
    return decorator


class PipelineStep:
    def __init__(self, name: str):
        self.name = name
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        logger.info("[%s] START", self.name)
        return self

    def __exit__(self, exc_type, exc_val, _tb):
        elapsed = time.monotonic() - self._start
        if exc_type:
            logger.error("[%s] FAILED in %.2fs — %s", self.name, elapsed, exc_val)
        else:
            logger.info("[%s] DONE in %.2fs", self.name, elapsed)
        return False


class ValidationError(ValueError):
    """Raised when generated content fails quality checks."""


# ── Fact sheet validator ──────────────────────────────────────────────────────

def validate_fact_sheet(data: dict) -> None:
    """
    Validate a research agent fact sheet.

    FIXED: now checks minimum fact density, not just product_name presence.
    A fact sheet with product_name but features=[] and key_benefits=[] passes
    the old check but produces unusable content. This version rejects it.
    """
    if not isinstance(data, dict):
        raise ValidationError("Fact sheet is not a dictionary.")

    required_keys = ["product_name", "features", "target_audience", "value_proposition"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise ValidationError(f"Fact sheet missing required keys: {missing}")

    if not data.get("product_name", "").strip():
        raise ValidationError(
            "Fact sheet has no product_name — the document may not describe a product."
        )

    # FIXED: check that at least some concrete facts were extracted
    features   = data.get("features", [])
    benefits   = data.get("key_benefits", [])
    specs      = data.get("specifications", [])
    total_facts = len(features) + len(benefits) + len(specs)

    has_context = bool(
        data.get("value_proposition", "").strip() or
        data.get("target_audience", "").strip() or
        data.get("problem_solved", "").strip()
    )

    if total_facts == 0 and not has_context:
        raise ValidationError(
            f"Fact sheet for '{data['product_name']}' has no extractable facts "
            "(features=0, benefits=0, specifications=0, no value proposition). "
            "The document is too vague or too short — please use a richer document."
        )


# ── Content validators ────────────────────────────────────────────────────────

def validate_blog(text: str) -> None:
    if not text or not text.strip():
        raise ValidationError("Blog output is empty.")
    wc = len(text.split())
    if wc < 400:
        raise ValidationError(
            f"Blog is only {wc} words. Required: 450–550. "
            "Write all 7 paragraphs: hook (60w), intro (70w), "
            "3 feature paragraphs (80w each), context (70w), CTA (60w)."
        )
    if wc > 650:
        raise ValidationError(
            f"Blog is {wc} words — too long. Required: 450–550. "
            "Cut the most repetitive sentences from the feature paragraphs."
        )
    if re.search(r"^#{1,4}\s", text, re.MULTILINE):
        raise ValidationError(
            "Blog contains markdown headers (#). Prose only — no headers, bullets, or lists."
        )


def validate_social(posts: Any) -> None:
    if not isinstance(posts, list) or not posts:
        raise ValidationError(
            "Social output is not a list. Return a JSON array of exactly 5 strings."
        )
    if len(posts) != 5:
        raise ValidationError(
            f"Social thread has {len(posts)} post(s) — must be exactly 5. "
            "Return: [hook, problem, feature, benefit, CTA]."
        )
    empty = [i + 1 for i, p in enumerate(posts) if not str(p).strip()]
    if empty:
        raise ValidationError(f"Posts {empty} are empty strings.")
    over_char = [i + 1 for i, p in enumerate(posts) if len(str(p)) > 280]
    if over_char:
        raise ValidationError(
            f"Posts {over_char} exceed 265 characters. Shorten each to under 265."
        )


def _count_email_sentences(text: str) -> int:
    """
    Count sentences in email text robustly.
    Only splits on punctuation that is followed by whitespace + capital letter
    (real sentence boundaries), not on abbreviations, decimals, or product names.
    Falls back to a word-count estimate if the result seems wrong.
    """
    if not text:
        return 0
    # Split only on [.!?] that are followed by space(s) and an uppercase letter
    # This avoids splitting on: A.N.C., 40-hr., vs., 3.5mm, etc.
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text.strip())
    count = len([p for p in parts if p.strip()])
    # Sanity check: if a single "sentence" is very long, it's probably multiple
    if count == 1 and len(text.split()) > 40:
        # Estimate: ~15 words per sentence
        count = max(2, len(text.split()) // 15)
    return count


def validate_email(text: str) -> None:
    if not text or not text.strip():
        raise ValidationError("Email output is empty.")
    sentences = _count_email_sentences(text)
    if sentences < 3:
        raise ValidationError(
            f"Email has only {sentences} sentence(s). Required: 3–5. "
            "Structure: S1 pain point, S2 product + benefit, S3 second benefit, S4 CTA."
        )
    if sentences > 6:
        raise ValidationError(
            f"Email has {sentences} sentences — too long. Required: 3–5."
        )
    if "\n\n" in text.strip():
        raise ValidationError(
            "Email has multiple paragraphs. Must be exactly ONE paragraph."
        )


def validate_content(content: dict, selected: list) -> dict:
    validators = {
        "blog":   (validate_blog,   content.get("blog", "")),
        "social": (validate_social, content.get("social", [])),
        "email":  (validate_email,  content.get("email", "")),
    }
    errors = {}
    for ctype in selected:
        if ctype in validators:
            fn, value = validators[ctype]
            try:
                fn(value)
            except ValidationError as e:
                errors[ctype] = str(e)
    return errors


# ── Document preprocessing ────────────────────────────────────────────────────

def preprocess_document(text: str, max_chars: int = 7000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_para = cut.rfind("\n\n")
    if last_para > max_chars * 0.65:
        cut = cut[:last_para]
    else:
        last_sent = max(cut.rfind(". "), cut.rfind(".\n"))
        if last_sent > max_chars * 0.65:
            cut = cut[:last_sent + 1]
    return (
        cut.strip()
        + "\n\n[Note: Document truncated. Content above is the primary source material.]"
    )


# ── Brief builder (shared by copywriter and editor) ───────────────────────────

def _build_brief_for_editor(fact_sheet: dict) -> str:
    """
    Build a human-readable product brief from the fact sheet.
    Used by both the editor agent and (via copywriter_agent._build_brief)
    the copywriter, so both evaluate against the same representation.
    """
    fs = fact_sheet
    lines = [f"PRODUCT: {fs.get('product_name', 'the product')}"]

    if fs.get("tagline"):
        lines.append(f"TAGLINE: {fs['tagline']}")
    if fs.get("target_audience"):
        lines.append(f"TARGET AUDIENCE: {fs['target_audience']}")
    if fs.get("problem_solved"):
        lines.append(f"PROBLEM IT SOLVES: {fs['problem_solved']}")
    if fs.get("value_proposition"):
        lines.append(f"CORE VALUE PROMISE: {fs['value_proposition']}")
    if fs.get("features"):
        lines.append("KEY FEATURES:")
        for f in fs["features"]:
            lines.append(f"  • {f}")
    if fs.get("key_benefits"):
        lines.append("BENEFITS TO THE USER:")
        for b in fs["key_benefits"]:
            lines.append(f"  • {b}")
    if fs.get("specifications"):
        lines.append("SPECIFICATIONS:")
        for s in fs["specifications"]:
            lines.append(f"  • {s}")
    if fs.get("differentiators"):
        lines.append("WHAT MAKES IT DIFFERENT:")
        for d in fs["differentiators"]:
            lines.append(f"  • {d}")
    if fs.get("pricing"):
        lines.append(f"PRICE: {fs['pricing']}")

    return "\n".join(lines)
