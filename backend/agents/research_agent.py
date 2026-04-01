"""
Research Agent — extracts structured product facts from raw document text.
NO hallucination: only uses information from the source document.
"""
import json
from utils.ai_client import AIClient


RESEARCH_PROMPT = """You are a Research & Fact-Check Agent. Analyze this document and extract ONLY facts explicitly stated.

RULES:
1. NEVER hallucinate or infer information not in the document.
2. If information is missing use "" or [].
3. Vague or unverifiable claims go in "flagged_ambiguities".
4. Keep each list item SHORT (under 15 words each).
5. Maximum 6 items per list.

Document:
\"\"\"
{document}
\"\"\"

Return this exact JSON (no markdown, no extra text):
{{
  "product_name": "name here",
  "features": ["feature 1", "feature 2", "feature 3"],
  "specifications": ["spec 1", "spec 2"],
  "target_audience": "who this is for",
  "value_proposition": "main benefit in one sentence",
  "key_benefits": ["benefit 1", "benefit 2", "benefit 3"],
  "pricing": "",
  "flagged_ambiguities": ["ambiguity 1"]
}}"""


# Minimal fallback prompt if the full one fails
RESEARCH_PROMPT_MINIMAL = """Extract product info from this text as JSON only.

Text: {document}

Return only this JSON structure:
{{
  "product_name": "...",
  "features": ["..."],
  "specifications": [],
  "target_audience": "...",
  "value_proposition": "...",
  "key_benefits": ["..."],
  "pricing": "",
  "flagged_ambiguities": []
}}"""


class ResearchAgent:
    def __init__(self, provider: str, api_key: str, model: str):
        self.client = AIClient(provider, api_key, model)

    def run(self, document_text: str) -> dict:
        # Truncate document to avoid token overflow
        doc = document_text[:6000]

        # Attempt 1: full prompt with 2500 tokens
        try:
            prompt = RESEARCH_PROMPT.format(document=doc)
            fact_sheet = self.client.generate_json(prompt, temperature=0.1, max_tokens=2500)
            return self._normalize(fact_sheet)
        except Exception as e1:
            first_error = str(e1)

        # Attempt 2: shorter document + minimal prompt
        try:
            short_doc = document_text[:3000]
            prompt = RESEARCH_PROMPT_MINIMAL.format(document=short_doc)
            fact_sheet = self.client.generate_json(prompt, temperature=0.1, max_tokens=1500)
            return self._normalize(fact_sheet)
        except Exception as e2:
            raise ValueError(
                f"Research Agent failed after 2 attempts.\n"
                f"Attempt 1: {first_error}\n"
                f"Attempt 2: {e2}"
            )

    def _normalize(self, fact_sheet: dict) -> dict:
        required = {
            "product_name": "",
            "features": [],
            "specifications": [],
            "target_audience": "",
            "value_proposition": "",
            "key_benefits": [],
            "pricing": "",
            "flagged_ambiguities": [],
        }
        for key, default in required.items():
            if key not in fact_sheet:
                fact_sheet[key] = default
            # Truncate oversized lists
            if isinstance(fact_sheet[key], list):
                fact_sheet[key] = [str(i)[:120] for i in fact_sheet[key][:8]]
            elif isinstance(fact_sheet[key], str):
                fact_sheet[key] = fact_sheet[key][:500]
        return fact_sheet
