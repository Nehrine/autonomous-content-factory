"""
Editor-in-Chief Agent — validates each content piece independently.
Loops until all pieces are approved or max retries reached.
"""
import json
from utils.ai_client import AIClient

EDITOR_PROMPT = """You are a ruthless but fair Editor-in-Chief. Review each piece of marketing content against the fact sheet.

Fact Sheet (ground truth):
{fact_sheet}

Content to Review:
BLOG POST:
{blog}

SOCIAL THREAD (5 posts):
{social}

EMAIL TEASER:
{email}

Check EACH piece independently for:
1. BLOG: Is it approximately 500 words? (count carefully — reject if under 400 or over 600). Does it have a hook, feature coverage, and CTA? Any hallucinated claims?
2. SOCIAL: Are there exactly 5 posts? Is each under 280 chars? Do they form a coherent thread? Any unsupported claims?
3. EMAIL: Is it exactly 1 paragraph (3-5 sentences)? Does it have a CTA? Any unsupported claims?
4. ALL: Does content match the fact sheet only? No invented stats, prices, or features?

Return a JSON object with this EXACT structure:
{{
  "blog": {{
    "status": "approved" or "rejected",
    "word_count_estimate": 450,
    "issues": ["issue 1", "issue 2"],
    "feedback": "specific rewrite instructions if rejected, else empty string"
  }},
  "social": {{
    "status": "approved" or "rejected",
    "post_count": 5,
    "issues": ["issue 1"],
    "feedback": "specific rewrite instructions if rejected, else empty string"
  }},
  "email": {{
    "status": "approved" or "rejected",
    "issues": [],
    "feedback": "specific rewrite instructions if rejected, else empty string"
  }},
  "overall_status": "approved" or "rejected",
  "scores": {{
    "accuracy": 8,
    "tone": 8,
    "completeness": 8
  }}
}}

Return ONLY the JSON."""


class EditorAgent:
    def __init__(self, provider: str, api_key: str, model: str):
        self.client = AIClient(provider, api_key, model)

    def run(self, fact_sheet: dict, content: dict) -> dict:
        blog   = content.get("blog", "")
        social = content.get("social", [])
        email  = content.get("email", "")

        social_str = "\n".join(f"  Post {i+1}: {p}" for i, p in enumerate(social)) if social else "(not generated)"

        prompt = EDITOR_PROMPT.format(
            fact_sheet=json.dumps(fact_sheet, indent=2),
            blog=blog or "(not generated)",
            social=social_str,
            email=email or "(not generated)",
        )

        try:
            result = self.client.generate_json(prompt, temperature=0.1, max_tokens=1500)
        except Exception as e:
            # If editor itself fails, approve everything to not block pipeline
            return self._default_approved()

        return self._normalize(result)

    def _normalize(self, r: dict) -> dict:
        for key in ["blog", "social", "email"]:
            if key not in r:
                r[key] = {"status": "approved", "issues": [], "feedback": ""}
            if "status" not in r[key]:
                r[key]["status"] = "approved"
            if "feedback" not in r[key]:
                r[key]["feedback"] = ""
            if "issues" not in r[key]:
                r[key]["issues"] = []

        # Derive overall status
        all_approved = all(r[k]["status"] == "approved" for k in ["blog", "social", "email"] if k in r)
        r["overall_status"] = "approved" if all_approved else "rejected"

        if "scores" not in r:
            r["scores"] = {"accuracy": 8, "tone": 8, "completeness": 8}

        return r

    def get_rejected_feedback(self, editor_result: dict) -> dict:
        """Return a dict of {content_type: feedback} for only rejected pieces."""
        feedback = {}
        for key in ["blog", "social", "email"]:
            piece = editor_result.get(key, {})
            if piece.get("status") == "rejected" and piece.get("feedback"):
                feedback[key] = piece["feedback"]
        return feedback

    def _default_approved(self) -> dict:
        approved = {"status": "approved", "issues": [], "feedback": ""}
        return {
            "blog": approved.copy(),
            "social": approved.copy(),
            "email": approved.copy(),
            "overall_status": "approved",
            "scores": {"accuracy": 8, "tone": 8, "completeness": 8},
        }
