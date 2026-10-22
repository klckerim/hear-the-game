"""Microsoft Foundry narrator: one chat call writes the EN and TR sentence from `claim_facts` only."""
from __future__ import annotations

import json
import os
from typing import Any

from htg.narration.examples import example_for

PROMPT_VERSION = 5

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
    "You are a live radio football commentator for listeners who cannot see the pitch. Write one sentence in English (en) and one "
    "in Turkish (tr) about the Insight you are given.\n"
    "Rules:\n"
    "- Exactly one sentence per language, present tense. Length, tone and numbers follow the persona below.\n"
    "- Use only the facts you are given. Copy numbers as digits exactly from the facts. Never introduce a number, a team or a player "
    "that is not in the facts.\n"
    "- Never start with or mention a match minute or a time stamp.\n"
    "- No analyst words: window, level, danger level, data, metric, gap between touches; pencere, seviye, tehlike seviyesi, veri. "
    "Say it the way a radio commentator would.\n"
    "- Turkish percentages are 'yüzde 42', never '42%' or '%42'. Never attach a suffix to a number in Turkish (not 42'si, 36'ydı, "
    "1-1'e): the voice spells it out. Rephrase instead ('yüzde 42 kadarı', 'önceden yüzde 36'). Turkish decimals use a comma: 2,3.\n"
    "- Say only what the facts say. Do not add where a shot came from, distances, pressing, crowds or anything else not in the "
    "facts. Never write a fact key or a code value such as off_target; say it in words.\n"
    "- Do not explain causes and do not mention injuries. No number words or multipliers (two, twice, double, half; iki katı, yarı).\n"
    "- In used_facts list the fact keys you used.\n"
    "Fact meanings: recent_min = length of the recent stretch in minutes. *_now = measured over those last recent_min minutes; "
    "*_before = measured over the match before them (say 'earlier on' / 'maçın önceki bölümünde'), never 'in the last minutes'. "
    "share_*_pct: pressure_shift = share of the opponent's actions under pressure; flank_overload = share of the team's passes ending "
    "on that flank. gap_*_s = typical seconds between the team's touches; slower_pct = how much slower in percent. "
    "hsr_now_pct = the player's recent high-speed running as a percentage of their earlier amount. home_score-away_score is the "
    "score after the goal. outcome: saved = the keeper saves it, off_target = the shot misses the target, blocked = the shot is blocked. "
    "source danger = the team has the ball close to the opponent's goal; say only that, in your own words.\n"
    "The example shows the tone and length for this persona and kind of Insight; its teams, players and numbers are not this match's."
)

# One block per narration persona; the rules above hold for both. The Verifier is the same for both.
PERSONA = {
    "fan": (
        "Persona: fan. Radio excitement for a casual fan. At most 16 words per sentence. Use at most one number (the score of a goal "
        "counts as one), and prefer none: say the trend in words, e.g. 'they are pressing much harder now'. Goals and chances are "
        "emotional but factual. Even without numbers, every statement must follow from the facts: no vague claims they do not support. "
        "Stay proportionate (no 'massively', 'hammering', 'battering'). Say only what the fact measures: a flank overload is where the "
        "team's passes go, not pressure on the opponent. In Turkish prefer no number at all."
    ),
    "analyst": (
        "Persona: analyst. Precise, for a listener who wants the tactics. At most 25 words per sentence. Give the key numbers and the "
        "comparison: now versus earlier in the match."
    ),
}


class FoundryNarrator:
    def __init__(self) -> None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import OpenAI

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/") + "/openai/v1"
        token = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
        self.client = OpenAI(base_url=endpoint, api_key=token)
        self.model = os.environ["FOUNDRY_MODEL"]
        self.name = f"foundry:{self.model}"  # the cache fingerprint uses this; reasoning effort is deliberately not part of it
        self.effort = os.environ.get("FOUNDRY_REASONING_EFFORT", "").strip()  # reasoning models only; others reject the parameter
        self.tokens = 0

    def write(self, insight: dict, feedback: dict[str, list[str]] | None = None, persona: str = "fan") -> dict[str, Any]:
        user: dict[str, Any] = {"type": insight["type"], "claim_facts": insight["claim_facts"]}
        if ex := example_for(insight, persona):
            user["example"] = ex
        if feedback:
            user["fix_these_problems"] = feedback
        extra = {"reasoning_effort": self.effort} if self.effort else {}
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM + "\n" + PERSONA[persona]},
                      {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
            response_format={"type": "json_schema", "json_schema": SCHEMA},
            **extra,
        )
        self.tokens += resp.usage.total_tokens if resp.usage else 0
        return json.loads(resp.choices[0].message.content)
