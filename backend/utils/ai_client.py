print("🔥 AI CLIENT LOADED FROM:", __file__)
"""
AI Client — unified wrapper for Gemini, OpenAI, and Anthropic Claude.

Key improvements over original:
  - System prompt support separated from user prompt (proper role injection)
  - All providers share identical generate() / generate_json() interface
  - No duplicated client attributes (_client handles all providers)
  - Robust multi-strategy JSON extraction with detailed fallback
"""
import json
import re
import logging
from typing import Optional

logger = logging.getLogger("ai_client")


class AIClient:
    def __init__(self, provider: str, api_key: str, model: str):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self._client = None
        self._init_client()

    # ── Initialization ────────────────────────────────────────────────────────

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
                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("Run: pip install openai")
        elif self.provider == "claude":
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("Run: pip install anthropic")
        elif self.provider == "groq":
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
            except ImportError:
                raise ImportError("Run: pip install groq")
        else:
            raise ValueError(
                f"Unsupported provider: '{self.provider}'. Use: gemini, openai, claude, or groq."
            )

    # ── Core Generation ───────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.4,
        max_tokens: int = 3000,
    ) -> str:
        """
        Generate a text response.
        'system' is the role/system prompt; 'prompt' is the task.
        All providers receive both; each adapts them to its own API format.
        """
        import time
        dispatch = {
            "gemini": self._generate_gemini,
            "openai": self._generate_openai,
            "claude": self._generate_claude,
            "groq":   self._generate_groq,
        }
        for attempt in range(3):
            try:
                result = dispatch[self.provider](prompt, system, temperature, max_tokens)
                if self.provider == "gemini":
                    time.sleep(12)  # free tier: 5 req/min
                logger.debug(
                    "[%s/%s] Generated %d chars", self.provider, self.model, len(result)
                )
                return result
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "rate_limit" in err.lower():
                    wait = 20
                    logger.warning("Rate limited — waiting %ds before retry %d/3", wait, attempt + 1)
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("generate() failed after 3 rate-limit retries")
    
    def generate_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> dict:
        import time
        print("🔥 generate_json called | provider:", self.provider)

        if self.provider == "gemini":
            for attempt in range(3):
                try:
                    result = self._generate_gemini_json(prompt, system, temperature, max_tokens)
                    time.sleep(12)  # free tier: 5 req/min
                    return result
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        wait = 65
                        logger.warning("Rate limited (JSON) — waiting %ds before retry %d/3", wait, attempt + 1)
                        time.sleep(wait)
                    else:
                        raise
            raise RuntimeError("generate_json() failed after 3 rate-limit retries")

        # Other providers
        json_enforcement = (
            "\n\nOUTPUT FORMAT — MANDATORY:\n"
            "Return ONLY a valid JSON object. No markdown, no explanation."
        )
        raw = self.generate(
            prompt + json_enforcement,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._extract_json(raw)
    # ── Provider Implementations ──────────────────────────────────────────────

    def _generate_gemini_json(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> dict:
        import json

        print("🔥 GEMINI JSON MODE EXECUTED")

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "response_mime_type": "application/json",
                "system_instruction": system,   # ✅ ADD THIS
            },
        )
        # ── Attempt 1: native JSON mode ───────────────────────────────────────
        # The Gemini SDK with response_mime_type="application/json" sometimes
        # raises an exception whose MESSAGE IS the raw partial JSON text
        # (e.g. '\n  "product_name": ...') when the model output doesn't conform
        # to the SDK's internal JSON validator. We catch this and recover the
        # partial text, then fall through to our own parsing strategies.
        raw = ""
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    "response_mime_type": "application/json",
                },
            )
            try:
                raw = response.text or ""
            except Exception as e:
                # response.text itself can raise — message may be partial JSON
                raw = str(e)
                print(f"⚠️ response.text raised: {type(e).__name__}: {raw[:200]}")
        except Exception as sdk_err:
            err_str = str(sdk_err)
            # 429 / quota errors must bubble up — don't swallow them into KV fallback
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                raise
            # Other SDK errors: message is often the partial JSON text, try to recover
            raw = err_str
            print(f"⚠️ generate_content (JSON mode) raised: {type(sdk_err).__name__}: {raw[:200]}")

            # If the raw text from the exception doesn't look like JSON at all,
            # retry without response_mime_type (plain text mode + our parser)
            if not any(c in raw for c in ['"', '{', '[']):
                print("⚠️ Exception text not JSON-like — retrying in plain text mode")
                try:
                    response2 = self._client.models.generate_content(
                        model=self.model,
                        contents=content + "\n\nReturn ONLY valid JSON. No markdown.",
                        config={
                            "temperature": temperature,
                            "max_output_tokens": max_tokens,
                        },
                    )
                    raw = response2.text or ""
                except Exception as e2:
                    raw = str(e2)
                    print(f"⚠️ Plain text retry also failed: {e2}")

        raw = raw.strip()
        print("RAW GEMINI OUTPUT:", raw[:300])

        # ── Strategy 1: direct parse ──────────────────────────────────────────
        try:
            result = json.loads(raw)
            if isinstance(result, dict):
                return result
            if isinstance(result, str):
                try:
                    inner = json.loads(result)
                    if isinstance(inner, dict):
                        return inner
                except Exception:
                    pass
            if isinstance(result, list) and result and isinstance(result[0], dict):
                print("⚠️ Gemini returned JSON array — unwrapping first element")
                return result[0]
        except Exception as e:
            print("JSON LOAD FAILED (direct):", e)

        # ── Strategy 2: bare key-value text without outer {} ──────────────────
        # e.g. raw = '\n  "product_name": "X",\n  "features": [...]'
        stripped = raw.strip().rstrip(",")
        if stripped and not stripped.startswith("{"):
            try:
                result = json.loads("{" + stripped + "}")
                if isinstance(result, dict):
                    print("⚠️ Gemini returned bare KV text — wrapped with {}")
                    return result
            except Exception:
                pass

        # ── Strategy 3: extract/repair { ... } block, including truncated JSON ──
        # Try the full raw text first (handles truncated output with no closing })
        fixed = self._try_close_json(raw)
        if fixed and isinstance(fixed, dict):
            print("⚠️ Gemini JSON recovered via auto-close on raw text")
            return fixed
        # Then try extracting the outermost complete block if present
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, dict):
                    print("⚠️ Gemini JSON extracted via regex block search")
                    return result
            except Exception:
                fixed = self._try_close_json(match.group(0))
                if fixed and isinstance(fixed, dict):
                    print("⚠️ Gemini JSON recovered via auto-close on regex match")
                    return fixed

        # ── Strategy 4: key-value regex fallback ─────────────────────────────
        print("⚠️ All parse strategies failed — using KV regex fallback")
        return self._extract_kv_fallback(raw)

    def _generate_gemini(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,   # ✅ ONLY prompt here
            config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "system_instruction": system,   # ✅ THIS IS THE FIX
            },
        )
        
        try:
            text = response.text
            if text is None:
                raise ValueError("Gemini returned None text")
            return text.strip()
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                raise
            raw = str(e).strip()
            print(f"⚠️ _generate_gemini response.text raised: {type(e).__name__}: {raw[:200]}")
            if raw:
                return raw
            raise RuntimeError(f"Gemini text generation failed: {e}") from e

    def _generate_openai(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _generate_claude(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system

        message = self._client.messages.create(**kwargs)
        return message.content[0].text.strip()

    def _generate_groq(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        # Groq uses the OpenAI-compatible chat completions API
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    
    

    # ── JSON Extraction ───────────────────────────────────────────────────────

    def _extract_json(self, raw: str) -> dict:
        """
        Multi-strategy JSON extraction from LLM output.
        Strategy 1: strip fences, direct parse
        Strategy 2: extract outermost {...} block
        Strategy 3: attempt to auto-close truncated JSON
        Strategy 4: key-value regex fallback (last resort)
        """
        # Strip markdown fences
        text = re.sub(r"```json\s*", "", raw)
        text = re.sub(r"```\s*", "", text).strip()

        # Strategy 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: extract outermost { ... }
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                fixed = self._try_close_json(candidate)
                if fixed:
                    return fixed

        # Strategy 4: regex key-value fallback
        result = self._extract_kv_fallback(text)

        if not isinstance(result, dict):
            logger.error("Non-dict JSON result — forcing empty")
            return {}

        return result

    def _try_close_json(self, partial: str) -> Optional[dict]:
        """Attempt to salvage truncated JSON by appending closing brackets."""
        s = partial.rstrip()
        for _ in range(200):
            opens_brace   = s.count("{") - s.count("}")
            opens_bracket = s.count("[") - s.count("]")
            attempt = re.sub(r",\s*$", "", s.rstrip())
            closing = "]" * max(0, opens_bracket) + "}" * max(0, opens_brace)
            try:
                return json.loads(attempt + closing)
            except json.JSONDecodeError:
                pass
            s = s[:-1].rstrip().rstrip(",").rstrip('"')
            if len(s) < 10:
                break
        return None

    def _extract_kv_fallback(self, text: str) -> dict:
        """Last-resort: regex-extract known keys from malformed JSON output."""
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
