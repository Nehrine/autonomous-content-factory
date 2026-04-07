"""
SocialAssembler — post-processing engine for social thread generation.

PURPOSE:
  The LLM is asked to generate 5 posts. Sometimes it returns 3. Sometimes it
  returns prose instead of JSON. This module's job is to guarantee that no matter
  what the LLM produces, the output is always exactly 5 valid posts — or raises
  with a specific, actionable error that the caller can use for a targeted retry.

DESIGN PRINCIPLES:
  1. Never invent content. Every repair strategy uses LLM-generated text,
     just restructured — not placeholder strings.
  2. Fail loudly with specifics. "Post 3 is 312 chars — truncate after word 40"
     is more useful than "validation failed".
  3. Extraction before rejection. Try every parsing strategy before giving up.
  4. Surgical repair. If 4 posts are fine and 1 is over the char limit, only
     truncate that 1 — don't regenerate all 5.

EXTRACTION STRATEGIES (in order):
  1. JSON array parse (clean output)
  2. JSON array parse after fence stripping
  3. Numbered list extraction (1. text or Post 1: text)
  4. Quoted string extraction
  5. Paragraph splitting (blank-line separated)
  6. Sentence chunking (split prose into post-sized pieces)

POST-PROCESSING AFTER EXTRACTION:
  - Label stripping: removes "Post 1:", "1/5", "Hook:" prefixes
  - Character truncation: hard truncates at word boundary to fit 265 chars
  - Empty post filtering: removes blank entries
  - Count enforcement: if >5 extracted, take best 5; if <5, raise with details

WHAT IS NOT DONE HERE:
  - Content generation (the LLM does that)
  - Quality evaluation (the editor does that)
  - Retry logic (the caller does that)
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("social_assembler")

# Hard limits
MAX_POST_CHARS = 265
MIN_POST_CHARS = 8
REQUIRED_POSTS = 5

# Label patterns to strip from post text
LABEL_PATTERNS = [
    r"^Post\s*\d+\s*[\(\[]?[A-Za-z]*[\)\]]?\s*:?\s*",   # "Post 1:", "Post 1 (Hook):"
    r"^\d+\s*/\s*5\s*",                                   # "1/5"
    r"^\d+\.\s*",                                         # "1."
    r"^(Hook|Problem|Feature|Benefit|CTA)\s*:\s*",         # "Hook:", "CTA:" — colon required
    r"^[-•*]\s*",                                         # bullet points
]
LABEL_RE = re.compile(
    "|".join(LABEL_PATTERNS),
    re.IGNORECASE,
)


@dataclass
class AssemblyResult:
    posts: list          # final list of post strings
    strategy_used: str   # which extraction strategy succeeded
    repairs_applied: list  # list of repair actions taken (for logging)
    warnings: list       # non-fatal issues found


class AssemblyError(ValueError):
    """Raised when assembly cannot produce 5 valid posts from the input."""
    pass


class SocialAssembler:
    """
    Extracts and repairs social posts from raw LLM output.
    Call assemble(raw) — returns AssemblyResult or raises AssemblyError.
    """

    def assemble(self, raw: str) -> AssemblyResult:
        """
        Main entry point. Tries all extraction strategies in order,
        then applies repairs to reach exactly 5 valid posts.
        """
        raw = raw.strip()
        if not raw:
            raise AssemblyError("LLM returned empty output.")

        # ── Step 1: Extract posts using all available strategies ──────────
        candidates, strategy = self._extract(raw)
        logger.debug("Extraction strategy '%s' yielded %d candidates", strategy, len(candidates))

        # ── Step 2: Clean each candidate ──────────────────────────────────
        cleaned, repairs = self._clean_all(candidates)

        # ── Step 3: Filter empty ──────────────────────────────────────────
        cleaned = [p for p in cleaned if len(p) >= MIN_POST_CHARS]

        # ── Step 4: Count enforcement ─────────────────────────────────────
        warnings = []
        if len(cleaned) > REQUIRED_POSTS:
            # Take the first 5 — they follow the arc order
            logger.info("Trimming %d posts → 5", len(cleaned))
            repairs.append(f"Trimmed {len(cleaned)} posts to 5")
            cleaned = cleaned[:REQUIRED_POSTS]

        if len(cleaned) < REQUIRED_POSTS:
            raise AssemblyError(
                f"Extraction produced {len(cleaned)} usable post(s) from strategy '{strategy}'. "
                f"Need {REQUIRED_POSTS}. Raw output length: {len(raw)} chars. "
                f"First 200 chars of raw: {raw[:200]!r}"
            )

        # ── Step 5: Character limit enforcement ───────────────────────────
        final_posts = []
        for i, post in enumerate(cleaned):
            if len(post) > MAX_POST_CHARS:
                truncated = self._truncate_to_limit(post, MAX_POST_CHARS)
                repairs.append(
                    f"Post {i+1}: truncated {len(post)} → {len(truncated)} chars"
                )
                if len(truncated) < MIN_POST_CHARS:
                    raise AssemblyError(
                        f"Post {i+1} could not be truncated to a meaningful length. "
                        f"Original: {post!r}"
                    )
                final_posts.append(truncated)
            else:
                final_posts.append(post)

        if repairs:
            logger.info("SocialAssembler repairs: %s", repairs)

        return AssemblyResult(
            posts=final_posts,
            strategy_used=strategy,
            repairs_applied=repairs,
            warnings=warnings,
        )

    # ── Extraction strategies ─────────────────────────────────────────────────

    def _extract(self, raw: str) -> tuple[list, str]:
        """
        Try all extraction strategies in order.
        Returns (candidates, strategy_name).
        """
        strategies = [
            ("json_array_direct",   self._extract_json_array),
            ("json_array_fenced",   self._extract_json_array_fenced),
            ("numbered_list",       self._extract_numbered_list),
            ("quoted_strings",      self._extract_quoted_strings),
            ("paragraph_split",     self._extract_paragraphs),
            ("sentence_chunk",      self._extract_sentence_chunks),
        ]

        for name, fn in strategies:
            try:
                result = fn(raw)
                if result and len(result) >= 2:  # need at least 2 to be worth considering
                    logger.debug("Strategy '%s' extracted %d items", name, len(result))
                    return result, name
            except Exception as e:
                logger.debug("Strategy '%s' failed: %s", name, e)

        raise AssemblyError(
            f"All {len(strategies)} extraction strategies failed on output of {len(raw)} chars."
        )

    def _extract_json_array(self, raw: str) -> Optional[list]:
        """Strategy 1: direct JSON array parse."""
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return None
        parsed = json.loads(match.group(0))
        if isinstance(parsed, list):
            return [str(p) for p in parsed if str(p).strip()]
        return None

    def _extract_json_array_fenced(self, raw: str) -> Optional[list]:
        """Strategy 2: strip markdown fences then JSON array parse."""
        cleaned = re.sub(r"```json\s*", "", raw)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()
        return self._extract_json_array(cleaned)

    def _extract_numbered_list(self, raw: str) -> Optional[list]:
        """
        Strategy 3: extract numbered or labeled lines.
        Handles: '1. text', 'Post 1: text', '1/5 text', 'Hook: text'
        """
        patterns = [
            r"(?:^|\n)\s*(?:Post\s*)?\d+\s*(?:/\s*5)?\s*[\.\):\-]?\s*(.+?)(?=\n\s*(?:Post\s*)?\d|$)",
            r"(?:^|\n)\s*(?:Hook|Problem|Feature|Benefit|CTA)\s*:\s*(.+?)(?=\n\s*(?:Hook|Problem|Feature|Benefit|CTA)|$)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, raw, re.DOTALL | re.IGNORECASE)
            if matches:
                items = [m.strip().replace("\n", " ") for m in matches if m.strip()]
                if len(items) >= 2:
                    return items
        return None

    def _extract_quoted_strings(self, raw: str) -> Optional[list]:
        """
        Strategy 4: extract all quoted strings of reasonable length.
        Handles: 'post text' or "post text"
        """
        # Match strings between quotes that are long enough to be posts
        matches = re.findall(r'"([^"]{15,300})"', raw)
        if not matches:
            matches = re.findall(r"'([^']{15,300})'", raw)
        if matches and len(matches) >= 2:
            return matches
        return None

    def _extract_paragraphs(self, raw: str) -> Optional[list]:
        """
        Strategy 5: split on blank lines.
        Works when the model returns prose paragraphs instead of JSON.
        """
        # Strip any JSON brackets first
        cleaned = re.sub(r"^\s*\[|\]\s*$", "", raw.strip())
        paras = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
        long_enough = [p for p in paras if len(p) >= MIN_POST_CHARS]
        if len(long_enough) >= 2:
            return long_enough
        return None

    def _extract_sentence_chunks(self, raw: str) -> Optional[list]:
        """
        Strategy 6 (last resort): split into sentences, then group into 5 chunks.
        Used when the model writes all 5 posts as one continuous paragraph.
        """
        # Remove JSON artifacts
        cleaned = re.sub(r'[\[\]"{}]', "", raw)
        cleaned = re.sub(r",\s*\n", "\n", cleaned).strip()

        # Split into sentences
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]

        if len(sentences) < REQUIRED_POSTS:
            return None

        # Group into 5 roughly equal chunks
        chunk_size = max(1, len(sentences) // REQUIRED_POSTS)
        chunks = []
        for i in range(REQUIRED_POSTS):
            start = i * chunk_size
            end = start + chunk_size if i < REQUIRED_POSTS - 1 else len(sentences)
            chunk = " ".join(sentences[start:end]).strip()
            if chunk:
                chunks.append(chunk)

        if len(chunks) == REQUIRED_POSTS:
            return chunks
        return None

    # ── Cleaning ──────────────────────────────────────────────────────────────

    def _clean_all(self, candidates: list) -> tuple[list, list]:
        """Clean all candidates and return (cleaned_list, repairs_applied)."""
        cleaned = []
        repairs = []
        for i, post in enumerate(candidates):
            original = post
            post = self._strip_label(post)
            post = self._normalize_whitespace(post)
            if post != original:
                repairs.append(f"Post {i+1}: stripped label/whitespace")
            cleaned.append(post)
        return cleaned, repairs

    def _strip_label(self, text: str) -> str:
        """Remove structural labels from the beginning of a post."""
        return LABEL_RE.sub("", text).strip()

    def _normalize_whitespace(self, text: str) -> str:
        """Collapse internal whitespace, normalize line breaks."""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _truncate_to_limit(self, text: str, limit: int) -> str:
        """
        Truncate text to fit within limit characters, cutting at a word boundary.
        Avoids cutting mid-sentence where possible.
        """
        if len(text) <= limit:
            return text

        # Try to cut at a sentence boundary first
        truncated = text[:limit]
        last_sentence = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
        )
        if last_sentence > limit * 0.6:
            return text[:last_sentence + 1].strip()

        # Fall back to word boundary
        last_space = truncated.rfind(" ")
        if last_space > limit * 0.6:
            return text[:last_space].strip()

        # Hard cut
        return truncated.strip()


# ── Module-level convenience function ────────────────────────────────────────

_assembler = SocialAssembler()

def assemble_social_posts(raw: str) -> list:
    """
    Public convenience function.
    Returns a list of exactly 5 post strings, or raises AssemblyError.
    """
    result = _assembler.assemble(raw)
    if result.repairs_applied:
        logger.info(
            "Social posts assembled via '%s' with repairs: %s",
            result.strategy_used, result.repairs_applied,
        )
    return result.posts
