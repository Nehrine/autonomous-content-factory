"""
AI Client wrapper - supports Gemini, OpenAI, and Anthropic Claude.
"""
import json
import re
from typing import Optional


class AIClient:
    def __init__(self, provider: str, api_key: str, model: str):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self._client = None
        self._openai_client = None
        self._anthropic_client = None
        self._init_client()

    def _init_client(self):
        if self.provider == "gemini":
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise ImportError("Run: pip install google-genai")
        elif self.provider == "openai":
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("Run: pip install openai")
        elif self.provider == "claude":
            try:
                import anthropic
                self._anthropic_client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("Run: pip install anthropic")
        else:
            raise ValueError(f"Unsupported provider: {self.provider}. Use gemini, openai, or claude.")

    def generate(self, prompt: str, temperature: float = 0.4, max_tokens: int = 3000) -> str:
        if self.provider == "gemini":
            return self._generate_gemini(prompt, temperature, max_tokens)
        elif self.provider == "openai":
            return self._generate_openai(prompt, temperature, max_tokens)
        elif self.provider == "claude":
            return self._generate_claude(prompt, temperature, max_tokens)

    def _generate_gemini(self, prompt: str, temperature: float, max_tokens: int) -> str:
        from google.genai import types
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text.strip()

    def _generate_openai(self, prompt: str, temperature: float, max_tokens: int) -> str:
        response = self._openai_client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _generate_claude(self, prompt: str, temperature: float, max_tokens: int) -> str:
        message = self._anthropic_client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()

    def generate_json(self, prompt: str, temperature: float = 0.2, max_tokens: int = 2000) -> dict:
        full_prompt = (
            prompt
            + "\n\nCRITICAL: Return ONLY valid JSON. No markdown fences, no explanation, no extra text before or after."
        )
        raw = self.generate(full_prompt, temperature=temperature, max_tokens=max_tokens)
        return self._extract_json(raw)

    def _extract_json(self, raw: str) -> dict:
        text = re.sub(r"```json\s*", "", raw)
        text = re.sub(r"```\s*", "", text).strip()

        # Strategy 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: find outermost { ... }
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                fixed = self._try_close_json(candidate)
                if fixed:
                    return fixed

        # Strategy 3: key-value regex fallback
        return self._extract_kv_fallback(text)

    def _try_close_json(self, partial: str) -> Optional[dict]:
        s = partial.rstrip()
        for _ in range(200):
            attempt = s
            opens_brace   = attempt.count('{') - attempt.count('}')
            opens_bracket = attempt.count('[') - attempt.count(']')
            attempt = re.sub(r',\s*$', '', attempt.rstrip())
            closing = ']' * max(0, opens_bracket) + '}' * max(0, opens_brace)
            candidate = attempt + closing
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            s = s[:-1].rstrip().rstrip(',').rstrip('"')
            if len(s) < 10:
                break
        return None

    def _extract_kv_fallback(self, text: str) -> dict:
        result = {
            "product_name": "", "features": [], "specifications": [],
            "target_audience": "", "value_proposition": "", "key_benefits": [],
            "pricing": "", "flagged_ambiguities": [],
        }
        for key in ["product_name", "target_audience", "value_proposition", "pricing"]:
            m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
            if m:
                result[key] = m.group(1)
        for key in ["features", "specifications", "key_benefits", "flagged_ambiguities"]:
            m = re.search(rf'"{key}"\s*:\s*\[([^\]]*)\]', text, re.DOTALL)
            if m:
                result[key] = re.findall(r'"([^"]+)"', m.group(1))
        return result
