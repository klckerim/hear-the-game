"""Microsoft Foundry narrator: one chat call writes the EN and TR sentence from `claim_facts` only."""
from __future__ import annotations

import json
import os
from typing import Any

from htg.narration.templates import narrate

PROMPT_VERSION = 1

SCHEMA = {
    "name": "narration",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"en": {"type": "string"}, "tr": {"type": "string"}, "used_facts": {"type": "array", "items": {"type": "string"}}},
        "required": ["en", "tr", "used_facts"],
        "additionalProperties": False,
    },
}

SYSTEM = (
    "You write one short live-radio sentence about a football match, in English (en) and Turkish (tr), "
    "for listeners who cannot see the pitch.\n"
    "Rules: exactly one sentence per language, at most 25 words. Use only the facts you are given. Write numbers as digits, copied "
    "exactly from the facts. Never introduce a number, a team or a player that is not in the facts. Do not explain causes and do not "
    "mention injuries. Never write number words or multipliers (two, twice, double, half; iki katı, yarı). Plain broadcast tone. "
    "In used_facts list the fact keys you used."
)


class FoundryNarrator:
    def __init__(self) -> None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import OpenAI

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/") + "/openai/v1"
        token = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
        self.client = OpenAI(base_url=endpoint, api_key=token)
        self.model = os.environ["FOUNDRY_MODEL"]
        self.name = f"foundry:{self.model}"
        self.tokens = 0

    def write(self, insight: dict, feedback: dict[str, list[str]] | None = None) -> dict[str, Any]:
        user = {"type": insight["type"], "claim_facts": insight["claim_facts"],
                "style_example": {"en": narrate(insight, "en"), "tr": narrate(insight, "tr")}}
        if feedback:
            user["fix_these_problems"] = feedback
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
            response_format={"type": "json_schema", "json_schema": SCHEMA},
        )
        self.tokens += resp.usage.total_tokens if resp.usage else 0
        return json.loads(resp.choices[0].message.content)
