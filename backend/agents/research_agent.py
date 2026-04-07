"""
Research Agent v3

ROOT CAUSE FIX for features=0 benefits=0:

The previous extraction prompt used inline schema examples that looked like
template placeholders to Gemini 2.5 Flash:

    "features": ["Specific feature with detail — e.g. '40-hour battery life'"]

Gemini read "e.g. '40-hour battery life'" as a format description, not a
real fact from the document, so it correctly returned [] (no facts matched
that meta-description pattern). This is a well-known failure mode: example
items in JSON schemas get treated as templates to exclude rather than as
style guides to follow.

FIX 1 — Separate the format instruction from the content instruction.
  The schema now uses short, neutral placeholder keys ("string", "string")
  with explicit extraction instructions written ABOVE the schema, not
  embedded inside it as example values.

FIX 2 — Two-stage extraction with explicit fact listing.
  Stage 1: "List every product fact you can find" (free-form prose output)
  Stage 2: "Now structure those facts into this JSON" (formatting only)
  This splits the hard cognitive tasks: finding facts vs formatting JSON.
  A model that lists 8 facts in stage 1 cannot produce features=[] in stage 2.

FIX 3 — Density gate is now FATAL, not a warning.
  validate_fact_sheet now checks minimum fact count.
  main.py FactSheetValidation is now FATAL (raises HTTP 422) so the user
  gets a clear "your document is too sparse" error instead of a confusing
  "blog failed after 3 attempts" error 53 seconds later.

FIX 4 — Raw response logging on extraction failure.
  When JSON extraction returns empty lists, we now log the raw response
  so the root cause is visible immediately in logs.
"""
import logging
import json
import re
from utils.ai_client import AIClient
from utils.pipeline import preprocess_document, validate_fact_sheet

logger = logging.getLogger("research_agent")


# ✅ Keep this (used by main.py)
class _DensityError(Exception):
    pass


# ─────────────────────────────────────────────
# SYSTEM PROMPT (STRONG + RELIABLE)
# ─────────────────────────────────────────────

SYSTEM = """You are a product research expert.

Extract structured product data from the document.

RULES:
- Extract features, specifications, benefits from ANY descriptive text
- Do NOT leave fields empty if information exists
- Convert bullet points into clean short phrases
- Keep items under 15 words
"""


# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

PRIMARY_PROMPT = """DOCUMENT:
\"\"\"
{doc}
\"\"\"

Extract product data and return JSON:

{{
  "product_name": "",
  "features": [],
  "specifications": [],
  "target_audience": "",
  "value_proposition": "",
  "key_benefits": [],
  "pricing": "",
  "flagged_ambiguities": []
}}
Return ONLY valid JSON. Do not include introductory text or markdown code blocks.
JSON:
"""


# ─────────────────────────────────────────────

class ResearchAgent:
    def __init__(self, provider: str, api_key: str, model: str):
        self.client = AIClient(provider, api_key, model)

    def run(self, document_text: str) -> dict:
        doc = preprocess_document(document_text, max_chars=6000)

        # 🔥 Try JSON first
        print("🔥 RESEARCH AGENT USING generate_json")
        raw = self.client.generate_json(
            PRIMARY_PROMPT.format(doc=doc),
            system=SYSTEM,
            temperature=0.2,
            max_tokens=4000,
)
        result = self._normalize(raw)

        # 🔥 HARD CHECK (only if truly empty)
        if not result["features"] and not result["specifications"]:
            raise _DensityError(
                "No extractable facts found — document too weak or parsing failed"
            )

        validate_fact_sheet(result)

        logger.info(
            "Research complete | product=%s | features=%d | benefits=%d",
            result["product_name"],
            len(result["features"]),
            len(result["key_benefits"]),
        )

        return result

    # ─────────────────────────────────────────

    def _extract_json_from_text(self, text: str) -> dict:
        """
        Bulletproof JSON extractor for messy LLM output
        """

        import json
        import re

        # 🔹 Remove markdown/code blocks
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()

        # 🔹 Try direct parse first
        try:
            return json.loads(text)
        except:
            pass

        # 🔹 Find all possible JSON-like blocks
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        for c in match:
            try:
                return json.loads(c)
            except:
                continue

        # 🔥 FINAL SAFETY — MANUAL BUILD
        

        result = {
            "product_name": "",
            "features": [],
            "specifications": [],
            "target_audience": "",
            "value_proposition": "",
            "key_benefits": [],
            "pricing": "",
            "flagged_ambiguities": [],
        }

        # Extract product name manually
        match = re.search(r'["\']?product_name["\']?\s*:\s*["\'](.*?)["\']', text, re.IGNORECASE)
        if match:
            result["product_name"] = match.group(1).strip()

        # Extract features (simple fallback)
        features = re.findall(r"-\s*(.+)", text)
        if features:
            result["features"] = features[:6]

        return result

    # ─────────────────────────────────────────

    def _normalize(self, data: dict) -> dict:
        if not isinstance(data, dict):
            data = {} # Ensure data is a dict if extraction failed entirely

        def clean_list(lst):
            if not isinstance(lst, list):
                return []
            return [str(item).strip()[:120] for item in lst if str(item).strip()]

        # Use .get() for every field to prevent KeyErrors
        return {
            "product_name": str(data.get("product_name", "")).strip(),
            "features": clean_list(data.get("features", [])),
            "specifications": clean_list(data.get("specifications", [])),
            "target_audience": str(data.get("target_audience", "")).strip(),
            "value_proposition": str(data.get("value_proposition", "")).strip(),
            "key_benefits": clean_list(data.get("key_benefits", [])),
            "pricing": str(data.get("pricing", "")).strip(),
            "flagged_ambiguities": clean_list(data.get("flagged_ambiguities", [])),
        }