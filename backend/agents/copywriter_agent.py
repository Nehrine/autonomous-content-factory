"""
Copywriter Agent v3 — social thread generation completely redesigned.

SOCIAL GENERATION — ROOT CAUSE ANALYSIS AND FIX:

ROOT CAUSE 1: Asking for 5 posts in one call is a compound task
  The model must simultaneously: plan 5 different narratives, write 5 different
  texts, count 5 different character budgets, format valid JSON, and follow a
  structural arc — all in one response. Any one of these can cause a failure
  that makes the whole output invalid.

ROOT CAUSE 2: "Return JSON array" is an output format instruction mixed with
  a content instruction. When models are focused on writing good content, they
  often forget the format wrapper. When they focus on the format wrapper, the
  content suffers.

ROOT CAUSE 3: Retry + same prompt = same failure. The model's failure mode
  is deterministic at a given temperature. Sending the same prompt again at
  temperature + 0.05 does not change the structural failure — it just adds
  noise. The failure is not random; it's a reasoning shortcut.

FIX — THREE-LAYER STRATEGY:

Layer 1: ONE-POST-AT-A-TIME generation (5 focused calls)
  Each call asks for exactly ONE post with ONE role. The model cannot return 2
  posts when the prompt only asks for 1. This makes the count problem impossible.
  Yes, it's 5 calls instead of 1. At ~50 tokens per post, that's ~250 tokens
  total vs ~300 tokens for a single-call attempt that fails and retries. Over
  3 retry cycles, one-at-a-time is CHEAPER than the single-call approach.

Layer 2: SocialAssembler post-processing
  All raw output passes through the assembler regardless of generation strategy.
  It tries 6 extraction strategies before giving up.

Layer 3: Selective repair
  If post N fails on its own, only post N is regenerated — not all 5.
  This is surgical correction, not full regeneration.

BLOG AND EMAIL: unchanged from v2.
"""
import json
import logging
import re
import time
from utils.ai_client import AIClient
from utils.pipeline import validate_blog, validate_social, validate_email, ValidationError
from utils.social_assembler import assemble_social_posts, AssemblyError

logger = logging.getLogger("copywriter_agent")

# ─────────────────────────────────────────────────────────────────────────────
# TONE & CREATIVITY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

TONE_MAP = {
    "formal":       "formal and authoritative — precise language, no contractions, structured sentences.",
    "casual":       "casual and conversational — short sentences, contractions fine, like texting a friend who happens to be an expert.",
    "friendly":     "warm and friendly — like a knowledgeable friend who genuinely cares about helping you.",
    "professional": "professional and credible — confident, clear, polished but never stiff or corporate.",
    "persuasive":   "urgently persuasive — strong verbs, emotional stakes, every sentence earns its place.",
}

def _tone(t: str) -> str:
    return TONE_MAP.get((t or "professional").lower(), TONE_MAP["professional"])

def _creativity_note(c: float) -> str:
    if c < 0.3:
        return "Stay close to the facts. Minimal embellishment."
    if c < 0.6:
        return "Balance creativity with factual grounding."
    return "Use vivid, specific language. Make it memorable. Every claim must come from the brief."

def _conditions_block(s: str) -> str:
    s = (s or "").strip()
    return f"\n\nCLIENT BRIEF ADDITIONS (follow these, they override defaults):\n{s}" if s else ""


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

COPYWRITER_SYSTEM = """\
You are a senior direct-response copywriter with 15 years of experience writing
for SaaS, consumer tech, and e-commerce brands. Your copy wins awards and converts.

Non-negotiable rules:
1. Use ONLY facts from the product brief. Never invent statistics, prices,
   features, or claims not explicitly given.
2. Never write generic filler. Every sentence must earn its place.
   BANNED: "innovative solution", "cutting-edge", "game-changer",
   "take it to the next level", "in today's world", "seamless experience",
   "state-of-the-art", "in conclusion", "it's important to".
3. Follow the output format exactly. Format errors cause rejection.
4. Incomplete output is always rejected. Write every section fully.\
"""


# ─────────────────────────────────────────────────────────────────────────────
# BRIEF BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_brief(fact_sheet: dict) -> str:
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


# ─────────────────────────────────────────────────────────────────────────────
# BLOG PROMPTS (unchanged from v2)
# ─────────────────────────────────────────────────────────────────────────────

BLOG_OUTLINE_PROMPT = """\
PRODUCT BRIEF:
{brief}

TASK: Create a detailed paragraph-by-paragraph outline for a 500-word blog post.

TONE: {tone}
CREATIVITY: {creativity}

STRUCTURE (7 paragraphs total):
Para 1 — HOOK: What emotional hook or scenario opens the post? (Don't name product yet.)
Para 2 — INTRODUCTION: How do we introduce {product_name} and its core promise?
Para 3 — FEATURE DEEP DIVE 1: Which specific feature to cover first, and what detail?
Para 4 — FEATURE DEEP DIVE 2: Which specific feature second, and what detail?
Para 5 — FEATURE DEEP DIVE 3: Which benefit or feature third, and what detail?
Para 6 — SOCIAL PROOF / CONTEXT: How does this fit the reader's life?
Para 7 — CTA: What specific action and why should they take it now?

For each paragraph, write:
- 1 sentence describing what it covers
- 2-3 key points from the brief it must include
- The approximate word target (total must reach 450-550 words)

Return the outline as plain text. No JSON.\
"""

BLOG_DRAFT_PROMPT = """\
PRODUCT BRIEF:
{brief}

APPROVED OUTLINE TO FOLLOW:
{outline}

TASK: Write the complete 500-word blog post body following this outline exactly.

TONE: {tone}
CREATIVITY: {creativity}{conditions}

WRITING RULES — breaking any causes rejection:
• Word count: 450–550 words. Write every paragraph. Do not skip or summarize.
• Prose only: no headers, no bullet points, no numbered lists, no markdown.
• Specific language: replace every vague phrase with a specific detail from the brief.
  WRONG: "It has impressive features."
  RIGHT: "With {first_feature}, you get [specific outcome from brief]."
• Human voice: read each sentence aloud. If it sounds like AI, rewrite it.
• No banned phrases: innovative, cutting-edge, game-changer, seamless, state-of-the-art.
• Facts only: every claim must come from the product brief above.

FACT CHECK — before finishing, verify:
  ✓ Product name used: {product_name}
  ✓ Value promise mentioned: {value_prop}
  ✓ At least 2 specific features referenced from the brief

OUTPUT: The blog post body text ONLY. No title, no byline, nothing else.\
"""

BLOG_REVISION_PROMPT = """\
PRODUCT BRIEF:
{brief}

REJECTION REASON:
{fb}

ORIGINAL POST (rejected — do NOT copy this, rewrite it):
{prev}

TASK: Write a completely new 500-word blog post that fixes every rejection reason.

TONE: {tone}{conditions}

REQUIREMENTS:
• 450–550 words (count carefully)
• 7 paragraphs: hook, intro, 3 feature/benefit paragraphs, context, CTA
• Flowing prose — no headers, bullets, markdown
• Every claim from the product brief only
• No banned phrases: innovative, cutting-edge, game-changer, seamless

OUTPUT: Complete corrected blog post body ONLY.\
"""


# ─────────────────────────────────────────────────────────────────────────────
# SOCIAL PROMPTS — one-post-at-a-time design
# ─────────────────────────────────────────────────────────────────────────────

# Context shown to every individual post call — establishes the arc
THREAD_CONTEXT = """\
PRODUCT BRIEF:
{brief}

THREAD ARC CONTEXT:
This is post {position} of 5 in a Twitter/X thread about {product_name}.
The full thread arc: Post 1 (Hook) → Post 2 (Problem) → Post 3 (Feature) → Post 4 (Benefit) → Post 5 (CTA)
{prev_posts_section}
TONE: {tone}\
"""

# Per-post role definitions with explicit DO/DON'T examples
POST_ROLE_DEFINITIONS = {
    1: """\
YOUR TASK: Write Post 1 — the HOOK.

PURPOSE: Stop the scroll. Create curiosity or state a bold claim.
The reader should think "wait, tell me more" — not "what is this product?"

RULES:
• Do NOT name the product yet.
• Do NOT list features.
• ONE compelling sentence or a short 2-sentence combo.
• Under 200 characters (leave room for engagement).

GOOD EXAMPLES (style only — write about THIS product):
  "You've been losing hours every week to a problem that was solved three years ago."
  "The average person wastes 2.3 hours a day on this. Most don't realize it."

BAD EXAMPLES (do not write like this):
  "Introducing an innovative new product that will change your life!"
  "Are you tired of struggling with [problem]?"\
""",

    2: """\
YOUR TASK: Write Post 2 — the PROBLEM.

PURPOSE: Name the specific pain point this product solves.
Make the reader feel understood, not lectured.

RULES:
• Name the problem concretely — not abstractly.
• Use "you" language — make it personal.
• Pull from the problem_solved or target_audience fields in the brief.
• Under 265 characters.

GOOD EXAMPLES (style only):
  "Tangled cables. Dead earbuds at hour 6 of a 12-hour flight. Charging cases that need their own charger."
  "You're managing 14 browser tabs because your tools don't talk to each other. That's not a workflow — that's chaos."

BAD EXAMPLES:
  "Many people face challenges with their current solutions in today's world."
  "The market lacks a proper solution for this common problem."\
""",

    3: """\
YOUR TASK: Write Post 3 — the FEATURE.

PURPOSE: Introduce one specific, impressive feature from the brief.
The feature should feel like the answer to the problem in post 2.

RULES:
• Name exactly ONE feature. Not two, not "features".
• Use a specific detail or number from the brief.
• Explain what it means for the user — not just what it is.
• Under 265 characters.

GOOD EXAMPLES (style only):
  "40 hours of battery. Not 20. Not 30. Forty. That's a full work week without reaching for a cable."
  "IPX5 waterproof rating means rain, sweat, and spilled coffee are irrelevant. Finally."

BAD EXAMPLES:
  "It has amazing features that will improve your experience."
  "The product offers cutting-edge technology for seamless use."\
""",

    4: """\
YOUR TASK: Write Post 4 — the BENEFIT.

PURPOSE: Translate the feature into a concrete life improvement.
Post 3 said WHAT it does. Post 4 says HOW THAT CHANGES YOUR LIFE.

RULES:
• Start from the user's perspective, not the product's.
• Be specific and personal — not abstract.
• Use a real-world scenario where possible.
• Under 265 characters.

GOOD EXAMPLES (style only):
  "Means your Monday morning commute, Tuesday gym session, Wednesday flight, and Thursday calls are all covered. One charge."
  "You stop planning your day around when you'll need to find a charging port. That's more valuable than it sounds."

BAD EXAMPLES:
  "Users will experience improved productivity and satisfaction."
  "This makes your life better in many ways."\
""",

    5: """\
YOUR TASK: Write Post 5 — the CTA (Call to Action).

PURPOSE: Convert interest into action. Be direct, specific, urgent.

RULES:
• Name a specific action: visit [brand site], try, order, grab.
• Create a reason to act NOW (if pricing/offer is in the brief, use it).
• If no price/offer in brief, use scarcity of attention: "you've read this far".
• Under 265 characters.

GOOD EXAMPLES (style only):
  "NovaPulse Pro. $79. Free shipping. If you've read this far, you already know you need it."
  "Stop compromising on audio because you think you can't afford not to. [link] starts at $79."

BAD EXAMPLES:
  "Click here to learn more about our innovative product!"
  "Visit our website today for more information."\
""",
}

# Single-post generation prompt
SINGLE_POST_PROMPT = """\
{thread_context}

{role_definition}

CHARACTER BUDGET: Your post must be UNDER {char_limit} characters.
Before finalizing, count the characters. If over {char_limit}, shorten it.

OUTPUT: Write the post text ONLY.
No labels ("Post 4:", "Benefit:"), no quotes around the text, no explanation.
Just the post content itself.\
"""

# Fallback: all-5 prompt used only as last resort on attempt 3
SOCIAL_FALLBACK_PROMPT = """\
PRODUCT BRIEF:
{brief}

TASK: Write 5 Twitter posts as a numbered list.

TONE: {tone}{conditions}

Write one post per line in this format:
1. [post text under 265 chars]
2. [post text under 265 chars]
3. [post text under 265 chars]
4. [post text under 265 chars]
5. [post text under 265 chars]

Post roles:
1. Hook — stops scroll, no product name, creates curiosity
2. Problem — names the specific pain point
3. Feature — one specific product feature with detail
4. Benefit — what the user gains in their real life
5. CTA — specific action + reason to act now

Rules: under 265 chars per post, facts from brief only, no generic phrases.
Write all 5 posts now:\
"""

SOCIAL_REVISION_PROMPT = """\
PRODUCT BRIEF:
{brief}

REJECTION REASON:
{fb}

ORIGINAL POSTS (rejected):
{prev}

TASK: Rewrite the social thread fixing every rejection reason.

TONE: {tone}{conditions}

Return a JSON array of EXACTLY 5 strings. Each under 265 characters. Facts only.
["post1", "post2", "post3", "post4", "post5"]\
"""


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL PROMPTS (unchanged from v2)
# ─────────────────────────────────────────────────────────────────────────────

EMAIL_PROMPT = """\
PRODUCT BRIEF:
{brief}

TASK: Write a marketing email teaser.

STRICT RULES (NON-NEGOTIABLE):
- Write EXACTLY 5 sentences.
- Each sentence must be clearly separated with a period.
- Do NOT merge sentences.
- Do NOT use bullet points.
- Do NOT use line breaks.
- Output must be ONE paragraph.

STRUCTURE:
1. Pain point
2. Product introduction
3. Feature/benefit 1
4. Feature/benefit 2
5. Clear CTA

TONE: {tone}
CREATIVITY: {creativity}{conditions}

OUTPUT: One paragraph with EXACTLY 5 sentences.
"""

EMAIL_REVISION_PROMPT = """\
PRODUCT BRIEF:
{brief}

REJECTION REASON:
{fb}

ORIGINAL EMAIL (rejected):
{prev}

TASK: Rewrite the email teaser fixing every rejection reason.

TONE: {tone}{conditions}

Must be ONE paragraph, 3–5 sentences, ending with a clear call to action.
Output the corrected paragraph ONLY.\
"""


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CLASS
# ─────────────────────────────────────────────────────────────────────────────

class CopywriterAgent:
    def __init__(self, provider: str, api_key: str, model: str):
        self.client = AIClient(provider, api_key, model)

    def run(
        self,
        fact_sheet: dict,
        tones: dict = None,
        creativity: float = 0.5,
        selected: list = None,
        conditions: str = "",
    ) -> dict:
        if selected is None:
            selected = ["blog", "social", "email"]
        if tones is None:
            tones = {}

        brief  = _build_brief(fact_sheet)
        cb     = _conditions_block(conditions)
        result = {}

        if "blog" in selected:
            result["blog"] = self._generate_blog(brief, fact_sheet, tones, creativity, cb)
        if "social" in selected:
            result["social"] = self._generate_social(brief, fact_sheet, tones, creativity, cb)
        if "email" in selected:
            result["email"] = self._generate_email(brief, tones, creativity, cb)

        return result

    def revise(
        self,
        fact_sheet: dict,
        content: dict,
        feedback_by_type: dict,
        tones: dict,
        conditions: str = "",
        creativity: float = 0.5,
    ) -> dict:
        brief  = _build_brief(fact_sheet)
        cb     = _conditions_block(conditions)
        result = dict(content)

        if "blog" in feedback_by_type and content.get("blog"):
            result["blog"] = self._revise_blog(
                brief, fact_sheet, feedback_by_type["blog"],
                content["blog"], _tone(tones.get("blog", "professional")), cb
            )
        if "social" in feedback_by_type and content.get("social"):
            result["social"] = self._revise_social(
                brief, feedback_by_type["social"],
                content["social"], _tone(tones.get("social", "casual")), cb
            )
        if "email" in feedback_by_type and content.get("email"):
            result["email"] = self._revise_email(
                brief, feedback_by_type["email"],
                content["email"], _tone(tones.get("email", "persuasive")), cb
            )

        return result

    def regenerate_single(
        self, fact_sheet: dict, content_type: str,
        tone_str: str, creativity: float, conditions: str = ""
    ) -> object:
        result = self.run(
            fact_sheet,
            tones={content_type: tone_str},
            creativity=creativity,
            selected=[content_type],
            conditions=conditions,
        )
        return result.get(content_type, "")

    # ── Blog (unchanged from v2) ───────────────────────────────────────────────

    def _generate_blog(self, brief, fact_sheet, tones, creativity, cb):
        tone       = _tone(tones.get("blog", "professional"))
        creat      = _creativity_note(creativity)
        product    = fact_sheet.get("product_name", "the product")
        vp         = fact_sheet.get("value_proposition", "")
        features   = fact_sheet.get("features", [])
        first_feat = features[0] if features else "its key feature"

        # Attempt 1: two-pass (outline → draft)
        try:
            outline = self.client.generate(
                BLOG_OUTLINE_PROMPT.format(
                    brief=brief, tone=tone, creativity=creat, product_name=product,
                ),
                system=COPYWRITER_SYSTEM, temperature=0.4, max_tokens=800,
            )
            draft = self.client.generate(
                BLOG_DRAFT_PROMPT.format(
                    brief=brief, outline=outline, tone=tone, creativity=creat,
                    conditions=cb, product_name=product,
                    value_prop=vp or "its core promise", first_feature=first_feat,
                ),
                system=COPYWRITER_SYSTEM, temperature=0.65, max_tokens=2800,
            )
            validate_blog(draft)
            logger.info("Blog: two-pass succeeded (%d words)", len(draft.split()))
            return draft
        except (ValidationError, Exception) as e:
            logger.warning("Blog two-pass failed: %s", e)

        # Attempt 2: single-pass with word count pressure
        expansion_prompt = (
            f"Write a 500-word blog post about {product}.\n\n"
            f"PRODUCT BRIEF:\n{brief}\n\n"
            f"TONE: {tone}\n"
            f"7 PARAGRAPHS REQUIRED:\n"
            f"1. Hook (60 words) — pain point, no product name yet\n"
            f"2. Introduce {product} and its promise (70 words)\n"
            f"3. Feature deep-dive 1 — specific detail from brief (80 words)\n"
            f"4. Feature deep-dive 2 — specific detail from brief (80 words)\n"
            f"5. Feature deep-dive 3 or key benefit (80 words)\n"
            f"6. How it fits the reader's life (70 words)\n"
            f"7. Call to action (60 words)\n\n"
            f"No headers. No bullets. Prose only. Output blog body ONLY.{cb}"
        )
        try:
            draft = self.client.generate(
                expansion_prompt, system=COPYWRITER_SYSTEM,
                temperature=0.6, max_tokens=2800,
            )
            validate_blog(draft)
            logger.info("Blog: attempt 2 succeeded (%d words)", len(draft.split()))
            return draft
        except (ValidationError, Exception) as e:
            logger.warning("Blog attempt 2 failed: %s", e)

        # Attempt 3: bare minimum
        bare = (
            f"Write a 500-word blog post about {product}.\nFacts:\n{brief}\n\n"
            f"- Hook paragraph (no product name)\n- Introduce product in para 2\n"
            f"- 3 paragraphs features/benefits\n- Context paragraph\n- CTA paragraph\n"
            f"- 450–550 words total, no headers, no bullets\n\nBlog post body:"
        )
        try:
            draft = self.client.generate(
                bare, system=COPYWRITER_SYSTEM, temperature=0.5, max_tokens=2800,
            )
            validate_blog(draft)
            logger.info("Blog: attempt 3 succeeded (%d words)", len(draft.split()))
            return draft
        except ValidationError as e:
            raise ValueError(f"Blog failed after 3 attempts. Last: {e}")

    # ── Social: one-post-at-a-time ────────────────────────────────────────────

    def _generate_social(self, brief, fact_sheet, tones, creativity, cb):
        """
        Generate 5 posts using one-at-a-time strategy.

        Why this works:
        - Each call asks for exactly 1 post → count compliance is guaranteed
        - Each call has a focused role definition → structure compliance improves
        - No JSON formatting required per call → format compliance is guaranteed
        - Posts are assembled and validated after all 5 are collected
        - Only failed individual posts are retried, not all 5

        API cost: 5 small calls (~50 tokens each) = ~250 tokens
        vs single-call failure → 3 retries × ~150 tokens = ~450 tokens
        One-at-a-time is CHEAPER when the single-call approach fails even once.
        """
        tone    = _tone(tones.get("social", "casual"))
        product = fact_sheet.get("product_name", "the product")
        posts   = []

        for position in range(1, 6):
            post = self._generate_single_post(
                position=position,
                brief=brief,
                product_name=product,
                tone=tone,
                previous_posts=posts,
                conditions=cb,
                creativity=_creativity_note(creativity),
            )
            posts.append(post)
            logger.debug("Post %d generated: %d chars", position, len(post))
            time.sleep(3)
        logger.info(
            "Social: one-at-a-time generated %d posts [%s]",
            len(posts),
            ", ".join(f"{len(p)}c" for p in posts),
        )

        try:
            validate_social(posts)
            return posts
        except ValidationError as e:
            # Surgical repair: fix only the posts that failed
            posts = self._repair_posts(posts, brief, product, tone, cb)
            validate_social(posts)
            return posts

    def _generate_single_post(
        self, position: int, brief: str, product_name: str,
        tone: str, previous_posts: list, conditions: str, creativity: str,
    ) -> str:
        """
        Generate one social post for a specific position in the thread arc.
        Retries up to 2 times if the post exceeds character limit.
        """
        role_def = POST_ROLE_DEFINITIONS[position]

        # Build previous posts section for context
        if previous_posts:
            prev_lines = "\n".join(
                f"Post {i+1} (already written): {p}"
                for i, p in enumerate(previous_posts)
            )
            prev_section = f"\nPREVIOUS POSTS IN THIS THREAD (for context and consistency):\n{prev_lines}\n"
        else:
            prev_section = ""

        context = THREAD_CONTEXT.format(
            brief=brief,
            position=position,
            product_name=product_name,
            prev_posts_section=prev_section,
            tone=tone,
        )

        prompt = SINGLE_POST_PROMPT.format(
            thread_context=context,
            role_definition=role_def,
            char_limit=265,
        )

        last_raw = ""
        for attempt in range(1, 3):
            raw = self.client.generate(
                prompt,
                system=COPYWRITER_SYSTEM,
                temperature=0.55,
                max_tokens=120,  # hard ceiling — a 265-char post needs max ~80 tokens
            )

            # Clean the raw output — strip any labels or quotes the model added
            post = self._clean_single_post(raw)
            last_raw = raw

            if len(post) <= 265 and len(post) >= 15:
                return post

            if len(post) > 265:
                logger.warning(
                    "Post %d attempt %d: %d chars, retrying with tighter constraint",
                    position, attempt, len(post)
                )
                # On retry, add explicit character count feedback
                prompt = (
                    f"Your previous post was {len(post)} characters — over the 265 limit.\n"
                    f"Rewrite it to be under 265 characters. Keep the same message but shorter.\n\n"
                    f"Previous post: {post}\n\n"
                    f"Write the shorter version now (just the post text, no labels):"
                )

        # Use the assembler to extract the best candidate from last raw output
        logger.warning("Post %d: using assembler on last raw output", position)
        try:
            from utils.social_assembler import SocialAssembler
            result = SocialAssembler().assemble(last_raw)
            if result.posts:
                return result.posts[0]
        except Exception:
            pass

        # Last resort: truncate to word boundary
        post_to_truncate = post if post else last_raw[:265]
        return self._truncate_post(post_to_truncate, 265)

    def _clean_single_post(self, raw: str) -> str:
        """Clean a single-post response — strip labels, quotes, fences."""
        raw = re.sub(r"```[a-z]*\s*|```", "", raw).strip()

        # Strip surrounding quotes
        if (raw.startswith('"') and raw.endswith('"')) or \
           (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1].strip()

        # Strip label prefixes
        label_re = re.compile(
            r"^(?:Post\s*\d+\s*[\(\[]?[A-Za-z]*[\)\]]?\s*:?\s*|"
            r"\d+\s*/\s*5\s*|\d+\.\s*|"
            r"(?:Hook|Problem|Feature|Benefit|CTA)\s*:\s*|"  # colon required
            r"[-•*]\s*)",
            re.IGNORECASE,
        )
        raw = label_re.sub("", raw).strip()

        # Normalize whitespace
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw

    def _truncate_post(self, text: str, limit: int) -> str:
        """Truncate to word boundary within limit."""
        if len(text) <= limit:
            return text
        truncated = text[:limit]
        last_space = truncated.rfind(" ")
        return (truncated[:last_space] if last_space > limit * 0.7 else truncated).strip()

    def _repair_posts(
        self, posts: list, brief: str, product_name: str, tone: str, cb: str
    ) -> list:
        """
        Surgical repair: only regenerate posts that have issues.
        Issues: wrong length (>265 or <15 chars), empty.
        """
        repaired = list(posts)

        for i, post in enumerate(repaired):
            needs_repair = (
                not post
                or len(post) < 15
                or len(post) > 265
            )
            if not needs_repair:
                continue

            position = i + 1
            logger.info("Repairing post %d (len=%d)", position, len(post))

            repair_prompt = (
                f"PRODUCT BRIEF:\n{brief}\n\n"
                f"Write Post {position} of 5 in a Twitter thread about {product_name}.\n"
                f"Role: {['', 'Hook', 'Problem', 'Feature', 'Benefit', 'CTA'][position]}\n\n"
                f"{POST_ROLE_DEFINITIONS[position]}\n\n"
                f"HARD LIMIT: under 265 characters. Count before submitting.\n"
                f"OUTPUT: Post text only. No labels.\n"
                f"TONE: {tone}{cb}"
            )
            try:
                raw = self.client.generate(
                    repair_prompt,
                    system=COPYWRITER_SYSTEM,
                    temperature=0.45,
                    max_tokens=120,
                )
                cleaned = self._clean_single_post(raw)
                if 15 <= len(cleaned) <= 265:
                    repaired[i] = cleaned
                    logger.info("Post %d repaired: %d chars", position, len(cleaned))
                else:
                    # Force truncate as absolute last resort
                    repaired[i] = self._truncate_post(cleaned or raw, 265)
            except Exception as e:
                logger.error("Post %d repair failed: %s", position, e)
                # Keep original even if bad — validator will surface the issue

        return repaired

    def _fallback_social_single_call(self, brief, tone, cb, product_name) -> list:
        """
        Emergency fallback: one-call numbered list format.
        Only used if one-at-a-time somehow produces < 3 valid posts.
        Uses assembler to extract from numbered list output.
        """
        logger.warning("Social: falling back to single-call numbered list")
        raw = self.client.generate(
            SOCIAL_FALLBACK_PROMPT.format(brief=brief, tone=tone, conditions=cb),
            system=COPYWRITER_SYSTEM,
            temperature=0.5,
            max_tokens=800,
        )
        return assemble_social_posts(raw)

    # ── Email ─────────────────────────────────────────────────────────────────

    def _generate_email(self, brief, tones, creativity, cb):
        tone  = _tone(tones.get("email", "persuasive"))
        creat = _creativity_note(creativity)
        prompt = EMAIL_PROMPT.format(
            brief=brief, tone=tone, creativity=creat, conditions=cb
        )
        last_error = None
        for attempt in range(1, 4):
            attempt_prompt = prompt
            if attempt > 1 and last_error:
                attempt_prompt = (
                    f"PREVIOUS ATTEMPT FAILED: {last_error}\n\n"
                    f"Email must have EXACTLY 3–5 sentences in ONE paragraph.\n\n{prompt}"
                )
            raw = self.client.generate(
                attempt_prompt,
                system=COPYWRITER_SYSTEM,
                temperature=0.45 + (attempt - 1) * 0.05,
                max_tokens=500,
            )

            # 🔥 STEP 1 — CLEAN
            email = raw.strip().replace("\n", " ")

            # 🔥 STEP 2 — SPLIT INTO SENTENCES
            sentences = re.split(r'(?<=[.!?])\s+', email)
            sentences = [s.strip() for s in sentences if s.strip()]

            # 🔥 STEP 3 — FORCE EXACTLY 5
            if len(sentences) != 5:
                logger.warning("Email not 5 sentences (%d) — fixing", len(sentences))

                fix_prompt = (
                    f"Rewrite this into EXACTLY 5 sentences:\n\n{email}\n\n"
                    f"Rules:\n"
                    f"- Keep meaning same\n"
                    f"- Exactly 5 sentences\n"
                    f"- Each sentence must end with a period\n"
                    f"- No merging\n"
                )

                fixed = self.client.generate(
                    fix_prompt,
                    system=COPYWRITER_SYSTEM,
                    temperature=0.3,
                    max_tokens=400,
                )

                sentences = re.split(r'(?<=[.!?])\s+', fixed.strip())
                sentences = [s.strip() for s in sentences if s.strip()]

            # 🔥 STEP 4 — FINAL GUARANTEE
            if len(sentences) < 5:
                sentences += ["Take action now."] * (5 - len(sentences))

            email = " ".join(sentences[:5]).strip()

            if not email.endswith("."):
                email += "."

            # ✅ VALIDATE FINAL
            try:
                validate_email(email)
                return email   # ✅ THIS is correct position
            except ValidationError as e:
                last_error = str(e)
    # ── Revision helpers ──────────────────────────────────────────────────────

    def _revise_blog(self, brief, fact_sheet, fb, prev, tone, cb):
        product = fact_sheet.get("product_name", "the product")
        vp = fact_sheet.get("value_proposition", "")
        prompt = BLOG_REVISION_PROMPT.format(
            brief=brief, fb=fb, prev=prev, tone=tone,
            conditions=cb, product_name=product,
            value_prop=vp or "its core promise",
        )
        return self.client.generate(
            prompt, system=COPYWRITER_SYSTEM, temperature=0.6, max_tokens=2800
        )

    def _revise_social(self, brief, fb, prev, tone, cb):
        prompt = SOCIAL_REVISION_PROMPT.format(
            brief=brief, fb=fb,
            prev=json.dumps(prev) if isinstance(prev, list) else prev,
            tone=tone, conditions=cb,
        )
        raw = self.client.generate(
            prompt, system=COPYWRITER_SYSTEM, temperature=0.55, max_tokens=800
        )
        try:
            return assemble_social_posts(raw)
        except AssemblyError:
            return self._parse_social_fallback(raw)

    def _revise_email(self, brief, fb, prev, tone, cb):
        prompt = EMAIL_REVISION_PROMPT.format(
            brief=brief, fb=fb, prev=prev, tone=tone, conditions=cb
        )
        return self.client.generate(
            prompt, system=COPYWRITER_SYSTEM, temperature=0.45, max_tokens=500
        )

    def _parse_social_fallback(self, raw: str) -> list:
        """Legacy fallback parser for revision path."""
        raw = re.sub(r"```json\s*|```\s*", "", raw).strip()
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                posts = json.loads(match.group(0))
                cleaned = [str(p).strip() for p in posts if str(p).strip()]
                if cleaned:
                    return cleaned
            except Exception:
                pass
        lines = [
            line.strip().lstrip("-•*0123456789.):'\"")
            for line in raw.split("\n") if line.strip()
        ]
        return [l for l in lines if len(l) > 20] or ["Could not parse posts — please regenerate."]
