"""
Copywriter Agent — generates blog (500 words), social thread (5 posts),
and email teaser (1 paragraph). Each content type has its OWN tone setting.
"""
import json
from utils.ai_client import AIClient

TONE_DESCRIPTIONS = {
    "formal":       "formal, authoritative, and precise. Use structured sentences and professional vocabulary.",
    "casual":       "casual, conversational, and relaxed. Use simple everyday language, contractions are fine.",
    "friendly":     "warm, friendly, and approachable. Feel like a knowledgeable friend giving advice.",
    "professional": "professional, trustworthy, and credible. Confident but never stiff or robotic.",
    "persuasive":   "highly persuasive, compelling, and action-oriented. Create urgency and desire. Use power words.",
}

BLOG_PROMPT = """You are a senior content writer. Write a complete, publish-ready blog post of EXACTLY 500 words.

Product Fact Sheet:
{fact_sheet}

Tone: {tone_desc}
Creativity: {creativity_label}
{conditions_block}

STRICT REQUIREMENTS:
- EXACTLY 500 words — count carefully. Not 300, not 400. Five hundred.
- Structure: Hook paragraph → Problem/Context → Product Introduction → 3-4 Feature sections → Value Proposition → Call to Action
- Only use facts from the fact sheet. Do NOT invent stats, prices, or claims.
- Write in flowing prose — NO bullet points, NO headers, NO markdown.
- Must feel human and engaging, not robotic.
- End with a strong, specific call to action.
- Output ONLY the blog post body text. Nothing else."""

SOCIAL_PROMPT = """You are a social media strategist. Write a coordinated 5-post Twitter/X thread about this product.

Product Fact Sheet:
{fact_sheet}

Tone: {tone_desc}
Creativity: {creativity_label}
{conditions_block}

STRICT REQUIREMENTS:
- Exactly 5 posts forming a coherent THREAD (post 1 hooks, posts 2-4 go deeper, post 5 is CTA).
- Post 1: Must start with a hook that stops the scroll.
- Posts 2-4: Each covers a different feature or benefit with specifics.
- Post 5: Strong call-to-action.
- EACH post must be under 270 characters (leave room for thread numbering).
- Only use facts from the fact sheet.
- Return ONLY a valid JSON array of exactly 5 strings: ["post1", "post2", "post3", "post4", "post5"]
- No markdown, no labels like "Post 1:", just the text."""

EMAIL_PROMPT = """You are an email marketing expert. Write a single-paragraph email teaser of 3-5 sentences.

Product Fact Sheet:
{fact_sheet}

Tone: {tone_desc}
Creativity: {creativity_label}
{conditions_block}

STRICT REQUIREMENTS:
- Exactly ONE paragraph (3-5 sentences).
- Sentence 1: Attention-grabbing opener that speaks to the reader's pain or desire.
- Sentences 2-3: Introduce the product and its core value proposition with 1-2 specific benefits.
- Sentence 4-5: Urgency + clear call-to-action with next step.
- Only use facts from the fact sheet.
- Output ONLY the paragraph text. No subject line, no greeting, no sign-off."""

BLOG_REVISION_PROMPT = """You are revising a blog post based on editor feedback. Produce a COMPLETE, corrected blog post.

Fact Sheet:
{fact_sheet}

Previous blog post:
{previous}

Editor feedback:
{feedback}

Tone: {tone_desc}
{conditions_block}

STRICT REQUIREMENTS:
- Fix ALL issues the editor raised.
- EXACTLY 500 words.
- Same structure rules as before: Hook → Context → Features → Value Prop → CTA.
- Output ONLY the corrected blog post text."""

SOCIAL_REVISION_PROMPT = """Revise these social posts based on editor feedback.

Fact Sheet:
{fact_sheet}

Previous posts:
{previous}

Editor feedback:
{feedback}

Tone: {tone_desc}
{conditions_block}

Fix all issues. Return ONLY a JSON array of 5 strings."""

EMAIL_REVISION_PROMPT = """Revise this email teaser based on editor feedback.

Fact Sheet:
{fact_sheet}

Previous email:
{previous}

Editor feedback:
{feedback}

Tone: {tone_desc}
{conditions_block}

Fix all issues. Output ONLY the corrected paragraph."""


class CopywriterAgent:
    def __init__(self, provider: str, api_key: str, model: str):
        self.client = AIClient(provider, api_key, model)

    def _td(self, tone: str) -> str:
        return TONE_DESCRIPTIONS.get(tone.lower(), TONE_DESCRIPTIONS["professional"])

    def _cl(self, creativity: float) -> str:
        if creativity < 0.3:
            return "Conservative — stick closely to the facts, minimal creative embellishment."
        elif creativity < 0.6:
            return "Balanced — some creative flair while staying grounded in facts."
        else:
            return "Expressive — vivid language, strong storytelling, while remaining factually accurate."

    def _cb(self, conditions: str) -> str:
        if not conditions or not conditions.strip():
            return ""
        return f"\nSPECIAL CONDITIONS (obey strictly):\n{conditions.strip()}\n"

    def run(self, fact_sheet: dict, tones: dict = None, creativity: float = 0.5,
            selected: list = None, conditions: str = "") -> dict:
        """
        tones: dict with per-content tone e.g. {"blog": "professional", "social": "casual", "email": "persuasive"}
        Falls back to "professional" for any missing key.
        """
        if selected is None:
            selected = ["blog", "social", "email"]
        if tones is None:
            tones = {}

        fs   = json.dumps(fact_sheet, indent=2)
        temp = 0.3 + creativity * 0.4
        cb   = self._cb(conditions)
        result = {}

        if "blog" in selected:
            td = self._td(tones.get("blog", "professional"))
            cl = self._cl(creativity)
            result["blog"] = self.client.generate(
                BLOG_PROMPT.format(fact_sheet=fs, tone_desc=td, creativity_label=cl, conditions_block=cb),
                temperature=temp, max_tokens=2000,
            )

        if "social" in selected:
            td  = self._td(tones.get("social", "casual"))
            cl  = self._cl(creativity)
            raw = self.client.generate(
                SOCIAL_PROMPT.format(fact_sheet=fs, tone_desc=td, creativity_label=cl, conditions_block=cb),
                temperature=temp, max_tokens=800,
            )
            result["social"] = self._parse_social(raw)

        if "email" in selected:
            td = self._td(tones.get("email", "persuasive"))
            cl = self._cl(creativity)
            result["email"] = self.client.generate(
                EMAIL_PROMPT.format(fact_sheet=fs, tone_desc=td, creativity_label=cl, conditions_block=cb),
                temperature=min(temp, 0.6), max_tokens=400,
            )

        return result

    def revise(self, fact_sheet: dict, content: dict, feedback_by_type: dict,
               tones: dict, conditions: str = "", creativity: float = 0.5) -> dict:
        """Revise only the pieces that were rejected, keeping approved ones unchanged."""
        fs   = json.dumps(fact_sheet, indent=2)
        temp = 0.3 + creativity * 0.35
        cb   = self._cb(conditions)
        result = dict(content)  # start with existing content

        if "blog" in feedback_by_type and content.get("blog"):
            td = self._td(tones.get("blog", "professional"))
            result["blog"] = self.client.generate(
                BLOG_REVISION_PROMPT.format(
                    fact_sheet=fs, previous=content["blog"],
                    feedback=feedback_by_type["blog"], tone_desc=td, conditions_block=cb
                ),
                temperature=temp, max_tokens=2000,
            )

        if "social" in feedback_by_type and content.get("social"):
            td  = self._td(tones.get("social", "casual"))
            raw = self.client.generate(
                SOCIAL_REVISION_PROMPT.format(
                    fact_sheet=fs, previous=json.dumps(content["social"]),
                    feedback=feedback_by_type["social"], tone_desc=td, conditions_block=cb
                ),
                temperature=temp, max_tokens=800,
            )
            result["social"] = self._parse_social(raw)

        if "email" in feedback_by_type and content.get("email"):
            td = self._td(tones.get("email", "persuasive"))
            result["email"] = self.client.generate(
                EMAIL_REVISION_PROMPT.format(
                    fact_sheet=fs, previous=content["email"],
                    feedback=feedback_by_type["email"], tone_desc=td, conditions_block=cb
                ),
                temperature=temp, max_tokens=400,
            )

        return result

    def _parse_social(self, raw: str) -> list:
        import re
        raw = raw.strip()
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                posts = json.loads(match.group(0))
                return [str(p).strip() for p in posts if str(p).strip()][:5]
            except Exception:
                pass
        lines = [l.strip().lstrip("-•123456789.").strip() for l in raw.split("\n") if l.strip()]
        return [l for l in lines if len(l) > 15][:5]

    def regenerate_single(self, fact_sheet: dict, content_type: str, tone: str,
                          creativity: float, conditions: str = "") -> object:
        result = self.run(
            fact_sheet,
            tones={content_type: tone},
            creativity=creativity,
            selected=[content_type],
            conditions=conditions,
        )
        return result.get(content_type, "")
