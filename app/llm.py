"""Thin wrapper around the Groq chat API that always returns parsed JSON."""
import json
import re

from app import config


class GroqLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        from groq import Groq  # imported here so tests can run without a key

        key = api_key or config.GROQ_API_KEY
        if not key:
            raise RuntimeError(
                f"GROQ_API_KEY is not set. MediAid looked in {config.ENV_FILE} "
                f"({'found' if config.ENV_FILE.exists() else 'FILE NOT FOUND'}). "
                "Open that file and add a line: GROQ_API_KEY=gsk_your_key")
        self.client = Groq(api_key=key)
        self.model = model or config.GROQ_MODEL
        self._effort_ok = True

    def _create(self, **kwargs):
        """Call Groq. For GPT-OSS models, ask for low reasoning effort (much faster)."""
        if self._effort_ok and self.model.startswith("openai/gpt-oss") and config.GROQ_REASONING_EFFORT:
            try:
                return self.client.chat.completions.create(reasoning_effort=config.GROQ_REASONING_EFFORT, **kwargs)
            except TypeError:
                self._effort_ok = False      # very old groq package: no such parameter
            except Exception as e:  # noqa: BLE001
                if "reasoning_effort" not in str(e):
                    raise
                self._effort_ok = False      # model doesn't accept it: retry without
        return self.client.chat.completions.create(**kwargs)

    def chat_json(self, system: str, messages: list[dict], temperature: float = 0.0) -> dict:
        """Send a chat request and parse the reply as JSON.

        Groq's JSON mode requires the word "JSON" to appear in the prompt,
        so every system prompt we pass must mention it.
        """
        resp = self._create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
        return parse_json(resp.choices[0].message.content)

    def chat_text(self, system: str, messages: list[dict], temperature: float = 0.3) -> str:
        resp = self._create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
            temperature=temperature,
        )
        return resp.choices[0].message.content


def parse_json(text: str) -> dict:
    """Parse JSON, tolerating stray text around the object."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise
