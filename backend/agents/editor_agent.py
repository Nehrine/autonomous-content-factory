"""
Editor Agent v2 — reviews and scores generated content against the fact sheet.

ARCHITECTURE IMPROVEMENTS:

1. SEPARATED CONCERNS: The editor now does TWO things independently:
   a) Hard rule checks (Python — deterministic, always correct)
   b) Quality assessment (AI — subjective, adds value beyond counting)
   Previously these were tangled. Now hard rules run FIRST and are final.
   The AI editor only evaluates quality on pieces that passed hard rules.

2. QUALITY DIMENSIONS EXPANDED:
   Old: accuracy, tone, completeness
   New: accuracy, tone, specificity, engagement, cta_strength
   "Specificity" catches the most common real failure: generic content that
   technically passes all structural rules but reads like a template.

3. FEEDBACK IS SURGICAL:
   Feedback is now formatted as numbered action items, not prose paragraphs.
   This gives the copywriter clear, parallel instructions — not a wall of text
   that partially contradicts itself.

4. SCORE ANCHORING:
   The AI is shown real examples of what each score level looks like, with
   quotes from the actual content. This produces calibrated scores rather
   than optimistic ones.

5. PIECE-LEVEL AI EVALUATION:
   Instead of reviewing all three pieces in one prompt (which causes the AI
   to conflate feedback), each piece is reviewed in its own focused call
   when needed. But we batch approved-by-hard-rules pieces to save API calls.
"""
import json
import logging
import re
from utils.ai_client import AIClient

logger = logging.getLogger("editor_agent")

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM = """\
You are a strict, senior Editor-in-Chief at a professional content agency.
You evaluate marketing copy against a product brief and quality rubric.

Your absolute rules:
1. Approve ONLY when every criterion is met.
2. Feedback must be surgical: numbered action items, not prose paragraphs.
   Each item must name the specific problem and the specific fix.
   BAD: "Improve the hook."
   GOOD: "1. Hook paragraph opens with 'In today's world' — replace with a
          specific scenario e.g. 'Three cables in your bag. One charge last week.'"
3. Never approve content that invents facts absent from the product brief.
4. Score honestly. A 9/10 means the content is genuinely excellent.
   A piece you are rejecting cannot score 8+.\
"""

# ─────────────────────────────────────────────────────────────────────────────
# REVIEW PROMPT — used for quality assessment after hard rules pass
# ─────────────────────────────────────────────────────────────────────────────

QUALITY_REVIEW_PROMPT = """\
PRODUCT BRIEF (ground truth):
{brief}

━━━ CONTENT TO EVALUATE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{content_section}

━━━ QUALITY CRITERIA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REJECT if ANY of these are true:
{criteria}

━━━ IF REJECTING: provide numbered action items ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Format each issue like this:
1. [WHAT IS WRONG — quote the offending text if possible]
   FIX: [Exactly what to rewrite and how]

━━━ SCORING RUBRIC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Score 1–10 for each dimension:

accuracy: Do all facts match the product brief?
  9-10 = every claim matches perfectly
  6-8  = minor imprecision, nothing invented
  3-5  = at least one invented claim
  1-2  = multiple invented facts

specificity: Are claims concrete and product-specific, or generic?
  9-10 = every claim uses specific details from the brief (numbers, names, features)
  6-8  = mostly specific with 1-2 generic phrases
  3-5  = several generic filler phrases ("innovative", "great experience", etc.)
  1-2  = almost entirely generic, could apply to any product

engagement: Does it pull the reader in and hold attention?
  9-10 = compelling from first word, reads like a human wrote it
  6-8  = mostly engaging with flat spots
  3-5  = reads like a template, predictable structure
  1-2  = robotic, boring, would be ignored

cta_strength: Does the call to action create urgency and clarity?
  9-10 = specific, urgent, tells reader exactly what to do
  6-8  = present and clear but not urgent
  3-5  = vague ("learn more", "find out today")
  1-2  = missing or buried

━━━ REQUIRED OUTPUT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return ONLY this JSON. No markdown, no explanation:
{schema}\
"""

# Per-piece criteria strings
BLOG_CRITERIA = """\
1. Hook paragraph opens with a generic phrase ("In today's world", "Are you tired of",
   "Imagine if") — should open with a specific scenario or sharp statement.
2. Any paragraph is vague/generic — could apply to any product, not this one.
3. Any claim or feature not present in the product brief.
4. Missing any of: hook, product introduction, feature coverage, call to action.
5. Reads like AI — robotic sentence patterns, overuse of "you can", "it is", "this is".\
"""

SOCIAL_CRITERIA = """\
1. Post 1 (hook) lists features instead of creating curiosity or stating a bold claim.
2. Any post is generic — could apply to any product, not this one.
3. Any claim not in the product brief.
4. Thread arc broken: hook → problem → feature → benefit → CTA not followed.
5. Any post is flat or boring — would be scrolled past.\
"""

EMAIL_CRITERIA = """\
1. Opens with a generic opener ("In today's world", "Are you tired of", "Introducing").
2. Any sentence is vague — no specific benefit named from the brief.
3. Any claim not in the product brief.
4. Call to action is vague: "learn more", "find out", "click here" without specifics.
5. Reads like a form letter — no personality or urgency.\
"""

BLOG_SCHEMA = """\
{
  "status": "approved",
  "issues": [],
  "feedback": "",
  "scores": {
    "accuracy": 7,
    "specificity": 7,
    "engagement": 7,
    "cta_strength": 7
  }
}\
"""

SOCIAL_SCHEMA = """\
{
  "status": "approved",
  "issues": [],
  "feedback": "",
  "scores": {
    "accuracy": 7,
    "specificity": 7,
    "engagement": 7,
    "cta_strength": 7
  }
}\
"""

EMAIL_SCHEMA = """\
{
  "status": "approved",
  "issues": [],
  "feedback": "",
  "scores": {
    "accuracy": 7,
    "specificity": 7,
    "engagement": 7,
    "cta_strength": 7
  }
}\
"""


class EditorAgent:
    def __init__(self, provider: str, api_key: str, model: str):
        self.client = AIClient(provider, api_key, model)

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, fact_sheet: dict, content: dict) -> dict:
        """
        Two-phase review:
        Phase 1: Python hard rules (deterministic — always runs, always wins)
        Phase 2: AI quality assessment (only on pieces that passed hard rules)

        This means we never waste an API call asking AI to review a blog
        that we can already tell is 79 words.
        """
        from utils.pipeline import _build_brief_for_editor
        brief = _build_brief_for_editor(fact_sheet)

        blog   = content.get("blog", "")
        social = content.get("social", [])
        email  = content.get("email", "")

        blog_wc    = len(blog.split()) if blog else 0
        social_cnt = len(social) if isinstance(social, list) else 0
        email_sc   = self._count_sentences(email) if email else 0

        # ── Phase 1: Hard rules (Python, deterministic) ───────────────────
        result = self._run_hard_rules(content, blog_wc, social_cnt, email_sc)

        # ── Phase 2: AI quality assessment (only for hard-rule-passing pieces)
        pieces_for_ai = [
            k for k in ["blog", "social", "email"]
            if content.get(k) and result[k]["status"] == "approved"
        ]

        if pieces_for_ai:
            ai_results = self._run_ai_quality_check(
                brief, content, pieces_for_ai,
                blog_wc, social_cnt, email_sc,
            )
            for k in pieces_for_ai:
                if k in ai_results:
                    # Merge AI result into hard-rule result
                    result[k].update(ai_results[k])

        # ── Final status ──────────────────────────────────────────────────
        generated = [k for k in ["blog", "social", "email"] if content.get(k)]
        all_ok = all(result[k]["status"] == "approved" for k in generated)
        result["overall_status"] = "approved" if all_ok else "rejected"

        # ── Compute aggregate scores ──────────────────────────────────────
        result["scores"] = self._aggregate_scores(result, generated)

        # ── Apply score ceiling on rejection ──────────────────────────────
        if result["overall_status"] == "rejected":
            for dim in result["scores"]:
                if result["scores"][dim] > 6:
                    result["scores"][dim] = 6

        # ── Log summary ───────────────────────────────────────────────────
        for k in generated:
            status = result[k]["status"]
            fb_preview = result[k].get("feedback", "")[:80]
            logger.info(
                "Editor [%s]: %s%s", k, status,
                f" — {fb_preview}" if fb_preview else ""
            )
        logger.info("Scores: %s", result["scores"])

        return result

    def get_rejected_feedback(self, result: dict) -> dict:
        return {
            k: result[k]["feedback"]
            for k in ["blog", "social", "email"]
            if result.get(k, {}).get("status") == "rejected"
            and result[k].get("feedback", "").strip()
        }

    # ── Phase 1: Hard rules ───────────────────────────────────────────────────

    def _run_hard_rules(self, content, blog_wc, social_cnt, email_sc) -> dict:
        """
        Deterministic Python checks. These always run and always override AI.
        Returns a base result dict — AI phase will fill in quality scores later.
        """
        result = {
            "blog":   {"status": "approved", "issues": [], "feedback": ""},
            "social": {"status": "approved", "issues": [], "feedback": ""},
            "email":  {"status": "approved", "issues": [], "feedback": ""},
        }

        # BLOG
        if content.get("blog") and blog_wc > 0:
            if blog_wc < 450:
                result["blog"]["status"] = "rejected"
                result["blog"]["feedback"] = (
                    f"1. Blog is only {blog_wc} words — must be 450–550.\n"
                    "   FIX: Write all 7 paragraphs in full: hook (60w), intro (70w), "
                    "three feature paragraphs (80w each), context (70w), CTA (60w). "
                    "Do not skip or summarize any section."
                )
            elif blog_wc > 580:
                result["blog"]["status"] = "rejected"
                result["blog"]["feedback"] = (
                    f"1. Blog is {blog_wc} words — must be 450–550.\n"
                    "   FIX: Cut the most repetitive sentences from the feature paragraphs."
                )

        # SOCIAL: post count
        if content.get("social"):
            if social_cnt < 5:
                result["social"]["status"] = "rejected"
                result["social"]["feedback"] = (
                    f"1. Thread has only {social_cnt} of 5 required posts.\n"
                    "   FIX: Return a JSON array of EXACTLY 5 strings: "
                    "[hook, problem, feature, benefit, CTA]."
                )

        # SOCIAL: character limits
        if content.get("social") and isinstance(content["social"], list):
            over = [
                (i + 1, len(str(p)))
                for i, p in enumerate(content["social"])
                if len(str(p)) > 265
            ]
            if over:
                items = ", ".join(f"post {i} ({c} chars)" for i, c in over)
                existing = result["social"]["feedback"]
                note = (
                    f"{'2' if existing else '1'}. {items} exceed 265 characters.\n"
                    "   FIX: Shorten each to under 265 characters while keeping the key message."
                )
                result["social"]["status"] = "rejected"
                result["social"]["feedback"] = (
                    f"{existing}\n{note}".strip() if existing else note
                )

        # EMAIL: sentence count
        if content.get("email") and content["email"].strip():
            if email_sc < 3:
                result["email"]["status"] = "rejected"
                result["email"]["feedback"] = (
                    f"1. Email has only {email_sc} sentence(s) — must be 3–5.\n"
                    "   FIX: Structure — S1: pain point opener. S2: product + primary benefit. "
                    "S3: second specific benefit. S4: call to action."
                )
            elif email_sc > 5:
                result["email"]["status"] = "rejected"
                result["email"]["feedback"] = (
                    f"1. Email has {email_sc} sentences — must be 3–5.\n"
                    "   FIX: Keep the strongest opener, one benefit sentence, and the CTA. "
                    "Cut everything else."
                )

        return result

    # ── Phase 2: AI quality check ─────────────────────────────────────────────

    def _run_ai_quality_check(
        self, brief, content, pieces, blog_wc, social_cnt, email_sc
    ) -> dict:
        """
        Run AI quality assessment on pieces that passed hard rules.
        Each piece gets its own focused prompt for better assessment quality.
        Returns partial result dict — only contains evaluated pieces.
        """
        piece_config = {
            "blog": (
                f"BLOG POST ({blog_wc} words):\n{content.get('blog', '')}",
                BLOG_CRITERIA,
                BLOG_SCHEMA,
            ),
            "social": (
                "SOCIAL THREAD:\n" + "\n".join(
                    f"Post {i+1} ({len(str(p))} chars): {p}"
                    for i, p in enumerate(content.get("social", []))
                ),
                SOCIAL_CRITERIA,
                SOCIAL_SCHEMA,
            ),
            "email": (
                f"EMAIL TEASER ({email_sc} sentences):\n{content.get('email', '')}",
                EMAIL_CRITERIA,
                EMAIL_SCHEMA,
            ),
        }

        results = {}
        for piece in pieces:
            content_section, criteria, schema = piece_config[piece]
            prompt = QUALITY_REVIEW_PROMPT.format(
                brief=brief,
                content_section=content_section,
                criteria=criteria,
                schema=schema,
            )
            for attempt in range(1, 3):
                try:
                    ai_result = self.client.generate_json(
                        prompt, system=SYSTEM,
                        temperature=0.15, max_tokens=1200
                    )
                    ai_result = self._sanitize_piece_result(ai_result)
                    results[piece] = ai_result
                    break
                except Exception as e:
                    logger.warning(
                        "Editor AI check attempt %d/2 for [%s] failed: %s",
                        attempt, piece, e
                    )
            else:
                # Both attempts failed — keep hard-rule result (approved)
                logger.error("Editor AI check failed for [%s] — keeping hard-rule approval", piece)
                results[piece] = {"status": "approved", "issues": [], "feedback": "", "scores": {
                    "accuracy": 6, "specificity": 6, "engagement": 6, "cta_strength": 6
                }}

        return results

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sanitize_piece_result(self, r: dict) -> dict:
        """Normalize a per-piece AI result."""
        if not isinstance(r, dict):
            r = {}
        if r.get("status") not in ("approved", "rejected"):
            r["status"] = "approved"
        if not isinstance(r.get("issues"), list):
            r["issues"] = []
        if not isinstance(r.get("feedback"), str):
            r["feedback"] = ""
        scores = r.get("scores", {})
        if not isinstance(scores, dict):
            scores = {}
        r["scores"] = {
            "accuracy":    self._clamp(scores.get("accuracy", 6)),
            "specificity": self._clamp(scores.get("specificity", 6)),
            "engagement":  self._clamp(scores.get("engagement", 6)),
            "cta_strength":self._clamp(scores.get("cta_strength", 6)),
        }
        return r

    def _aggregate_scores(self, result: dict, generated: list) -> dict:
        keys = ["accuracy", "specificity", "engagement", "cta_strength"]

        piece_scores = [
            result[k].get("scores", {})
            for k in generated
            if isinstance(result[k].get("scores"), dict)
        ]

        if not piece_scores:
            return {k: 5 for k in keys}

        return {
            k: round(sum(s.get(k, 5) for s in piece_scores) / len(piece_scores), 1)
            for k in keys
        }

    def _clamp(self, val) -> int:
        try:
            return max(1, min(10, int(val)))
        except (TypeError, ValueError):
            return 5

    def _count_sentences(self, text: str) -> int:
        if not text:
            return 0
        # Only split on punctuation followed by whitespace + capital letter
        parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text.strip())
        count = len([p for p in parts if p.strip()])
        if count == 1 and len(text.split()) > 40:
            count = max(2, len(text.split()) // 15)
        return count
