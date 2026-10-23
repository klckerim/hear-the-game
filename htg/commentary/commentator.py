"""Live commentator: one Foundry call per segment writes 0-2 short radio lines (EN and TR) from the segment's facts only.

`commentate()` verifies each line per language with the narration Verifier (football terms such as "first half" allowed, invented
details such as "header" or "top corner" rejected) and drops what fails: there is no template, the callouts cover the gap.
Verified lines are cached per (seed, segment, prompt version, model) as the fallback for a later session whose live
line is late or fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Protocol

from htg.commentary.segments import Segment
from htg.narration.verifier import verify

COMMENTARY_PROMPT_VERSION = 4  # part of the cache key: v3 lines (one called an equaliser a lead) are never played again
LANGS = ("en", "tr")
STYLES = ("calm", "lively", "excited", "explosive")
WORDS_PER_S = 2.5
MAX_LINES = 2
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "commentary"
# Line style -> Azure speaking style of the commentary voice, per language (MAI-Voice; the fallback voices keep what they have).
SPEECH_STYLE = {"en": {"explosive": "shouting", "excited": "excited", "lively": "joyful", "calm": "neutral"},
                "tr": {"explosive": "excited", "excited": "excited", "lively": "curious", "calm": "neutral"}}
# Football words that contain a banned phrase ("half", "yarı"); masked before the Verifier runs.
FOOTBALL_TERMS = re.compile(r"first half|second half|own half|half-time|half time|halftime|halfway|ilk yarı|ikinci yarı|yarı saha"
                            r"|(?:kendi|rakip) yarı\w*|devre arası", re.IGNORECASE)
# Details no segment fact can carry: how the ball was struck, where it went, what the referee or a player did besides the facts.
# Not "var" (Turkish for "there is") and not "orta" ("orta saha" is midfield, a fact).
INVENTED = re.compile(r"\b(volley\w*|header|headed|top corner|bottom corner|top bin|crossbar|the bar|the post|woodwork|penalt\w*"
                      r"|offside|cross(?:es|ed)?|dribbl\w*|tackl\w*|vole\w*|kafa\w*|köşe\w*|direk\w*|penaltı\w*|ofsayt\w*"
                      r"|çalım\w*|ortala\w*|(?:in|into|the) box|clip\w*|ceza saha\w*|ceza alan\w*"
                      r"|restor\w*|yeniden öne\w*|edge of the \w+|the area)\b", re.IGNORECASE)  # also history ("lead restored")
# Who is ahead is a fact (the score, and goal_effect after a goal), not the model's inference: "lead" words only when the score says so.
LEAD = re.compile(r"\b(lead\w*|ahead|in front|öne geç\w*|önde)\b", re.IGNORECASE)
LEVEL = re.compile(r"\b(level\w*|equali[sz]\w*|all square|parity|berabere\w*|beraberli\w*|eşit\w*)\b", re.IGNORECASE)
# Pressing is a measured pattern (pressure_shift), not a word for "attacking": only when the facts carry that Insight.
PRESSING = re.compile(r"\b(press\w*|baskı\w*|bastır\w*)\b", re.IGNORECASE)

SCHEMA = {
    "name": "commentary",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"lines": {"type": "array", "items": {
            "type": "object",
            "properties": {"en": {"type": "string"}, "tr": {"type": "string"}, "style": {"type": "string", "enum": list(STYLES)},
                           "offset_s": {"type": "number"}},
            "required": ["en", "tr", "style", "offset_s"],
            "additionalProperties": False}}},
        "required": ["lines"],
        "additionalProperties": False,
    },
}

SYSTEM = (
    "You are a live radio football commentator, talking to fans who cannot see the pitch. You get the facts of the last few "
    "seconds of play and the lines you said just before (recent). Write 0, 1 or 2 short lines; each line in English (en) and "
    "Turkish (tr) with the same meaning. English is the main language: write it first and make it sound like real British radio.\n"
    "Rules:\n"
    "- Length: all lines together at most seconds_available x 2.5 words per language. Short exclamations are good ('Ooh!', "
    "'What a hit!', 'Kurtardı!', 'Ne vuruş!').\n"
    "- Silence is fine: return no lines when nothing new happened (a quiet spell of passing in their own half or midfield) or you "
    "would repeat a recent line. Never repeat or paraphrase a recent line, and vary your words (not 'probing' every time). Plain "
    "passing play gets at most 8 words; save longer lines for shots, goals, cards and attacks in the final third.\n"
    "- Use only the facts. Names and numbers only as given (digits). Never invent a detail: no headers, volleys, crosses, "
    "dribbles, tackles, chips, the box or penalty area, corners of the goal, posts, penalties, offside, injuries, causes, weather, "
    "crowd, referee words beyond the card. Pressing (press, baskı) only when tactical_insight is pressure_shift; an attack is not "
    "pressing. Do not describe how a pass was played (no 'threads', 'clips', 'slips'): say who passed to whom. Describe "
    "only what the facts hold: who had the ball, who passed to whom, where, and how it ended; nothing about the keeper, a player "
    "being free, on the ground or looking up, unless a fact says it. "
    "Never write a fact key or a code value such as final_third or off_target; say it in words.\n"
    "- Do not say the minute, except at half-time or full-time. Say the score only after a goal or at the end of a half.\n"
    "- A goal: say what it did exactly as goal_effect says: takes_lead = they go ahead, extends_lead = they extend the lead, "
    "equaliser = it is level, pulls_one_back = they pull one back and still trail. Never 'lead' or 'öne geçti' for an equaliser, "
    "never 'restored' or 'again' (you do not know the earlier score). Outside a goal, say a team leads only when the score shows it.\n"
    "- style: explosive only for a goal; excited for shots, saves and cards; lively for an attack in the final third; calm otherwise.\n"
    "- offset_s: seconds after the segment ends when the line starts, 0 to 3; a second line starts after the first has finished.\n"
    "- Turkish: no number with a suffix (not 89'luk, 1-0'a); rephrase. Natural Turkish radio jargon (şut, kurtardı, taç, korner, "
    "serbest vuruş, sarı kart, gol). Where the ball is: final_third = 'rakip yarı sahada' or 'hücumda', midfield = 'orta sahada', "
    "own_half = 'kendi yarı sahasında'; never 'son üçüncü'.\n"
    "Fact meanings: team_in_possession had the ball; player_1..player_4 = players of that team who played the ball, in order; "
    "pass_count = their passes in this stretch; progression = how far up the pitch they got (own_half, midfield, final_third); "
    "started_with = the restart this stretch began with; ended_by = what stopped play (play_on = play goes on); shot_outcome: "
    "saved = the keeper saves, off_target = wide, blocked = blocked, goal = goal; shot_speed_kmh = ball speed of the shot; "
    "scoring_team / scorer = who scored; home_score / away_score = the score now (after this play); goal_effect = what the goal did "
    "(takes_lead, extends_lead, equaliser, pulls_one_back); put_out_by = the team that put the ball out; fouling_team committed "
    "the foul; booked_player got the card; tactical_insight = a pattern the analysts just spotted (pressure_shift, tempo_change, "
    "flank_overload, physical_drop, chance), by tactical_team."
)


class Model(Protocol):
    name: str

    def write(self, facts: dict, recent: list[str]) -> dict[str, Any]: ...


class FoundryCommentator:
    def __init__(self) -> None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import OpenAI

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/") + "/openai/v1"
        token = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
        # The stream gives up after its budget (~17 s) anyway; without a timeout one hung call held a thread for 10 minutes (eval).
        self.client = OpenAI(base_url=endpoint, api_key=token, timeout=20.0)
        self.model = os.environ.get("FOUNDRY_COMMENTARY_MODEL") or os.environ["FOUNDRY_MODEL"]
        self.name = f"foundry:{self.model}"
        self.effort = os.environ.get("FOUNDRY_REASONING_EFFORT", "").strip()

    def write(self, facts: dict, recent: list[str]) -> dict[str, Any]:
        extra = {"reasoning_effort": self.effort} if self.effort else {}
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": json.dumps({"facts": facts, "recent": recent}, ensure_ascii=False)}],
            response_format={"type": "json_schema", "json_schema": SCHEMA},
            **extra,
        )
        return json.loads(resp.choices[0].message.content)


def get_commentator() -> Model | None:
    """Foundry when HTG_ENV=azure and COMMENTARY is not off; else None (no live commentary: callouts and narration only)."""
    flag = os.environ.get("COMMENTARY", "on" if os.environ.get("HTG_ENV") == "azure" else "off")
    if flag != "on":
        return None
    try:
        return FoundryCommentator()
    except Exception as e:
        print(f"Commentator unavailable ({type(e).__name__}); callouts and narration only.")
        return None


def warm(model: Model) -> float | None:
    """One throwaway call when the server starts, as a broadcast would have its commentator ready before kick-off: the first call
    after a start took 7-12 s (credential, connection), later ones 2-3 s, so the first listener's opening lines came late. The
    answer is discarded (not verified, not cached). Returns the seconds it took, None on an error (the server starts anyway)."""
    facts = {"minute": 1, "home_team": "Northport", "away_team": "Valemont", "home_score": 0, "away_score": 0,
             "team_in_possession": "Northport", "pass_count": 0, "ended_by": "play_on", "seconds_available": 3.0}
    t0 = time.perf_counter()
    try:
        model.write(facts, [])
    except Exception:
        return None
    return round(time.perf_counter() - t0, 2)


def verify_line(text: str, lang: str, facts: dict, names: list[str], max_words: int) -> list[str]:
    """The narration Verifier on the segment facts, plus: no invented detail, no longer than the segment allows."""
    reasons = verify(FOOTBALL_TERMS.sub("x", text), lang, {"claim_facts": facts}, names)
    reasons += [f"invented detail '{m}'" for m in INVENTED.findall(text)]
    if facts.get("tactical_insight") != "pressure_shift":
        reasons += [f"'{m}' without a pressure Insight" for m in PRESSING.findall(text)]
    reasons += score_state_reasons(text, facts)
    if len(text.split()) > max_words:
        reasons.append(f"longer than {max_words} words")
    return reasons


def score_state_reasons(text: str, facts: dict) -> list[str]:
    """A lead word needs a lead (after a goal: the scoring team's, goal_effect takes_lead / extends_lead); a level word needs a level
    score. The Verifier checks numbers and names; this is the one piece of meaning cheap enough to check from the facts."""
    if "home_score" not in facts:
        return []
    level = facts["home_score"] == facts["away_score"]
    lead_ok = facts["goal_effect"] in ("takes_lead", "extends_lead") if "goal_effect" in facts else not level
    out = [f"'{m}' but the score does not show that lead" for m in LEAD.findall(text) if not lead_ok]
    return out + [f"'{m}' but the score is not level" for m in LEVEL.findall(text) if not level]


def commentate(seg: Segment, model: Model, names: list[str], recent: list[str]) -> dict:
    """{"lines": [{"en", "tr", "style", "offset_s"}], "dropped": n, "reasons": [...], "latency_s"}. A line keeps the languages that
    pass (a missing one is None) and is dropped when none does. Model errors propagate; the caller falls back."""
    t0 = time.perf_counter()
    draft = model.write(seg.facts, recent[-3:])
    budget = max(4, round(seg.facts["seconds_available"] * WORDS_PER_S))
    lines, reasons, dropped, used = [], [], 0, {lang: 0 for lang in LANGS}
    for raw in draft.get("lines", [])[:MAX_LINES]:
        line: dict[str, Any] = {"style": raw.get("style") if raw.get("style") in STYLES else "calm",
                                "offset_s": round(min(max(float(raw.get("offset_s") or 0), 0.0), 3.0), 1)}
        for lang in LANGS:
            text = str(raw.get(lang, "")).strip()
            bad = verify_line(text, lang, seg.facts, names, budget - used[lang]) if text else ["empty"]
            line[lang] = None if bad else text
            if bad:
                reasons += [f"{lang}: {r}" for r in bad]
            else:
                used[lang] += len(text.split())
        if line["en"] is None and line["tr"] is None:
            dropped += 1
        else:
            lines.append(line)
    return {"lines": lines, "dropped": dropped, "reasons": reasons, "latency_s": round(time.perf_counter() - t0, 3)}


def cache_path(seed: object, segment_id: str, model_name: str, cache_dir: Path = CACHE_DIR) -> Path:
    """Segments are cut the same way over the whole match wherever a session starts (the warm-up feeds the segmenter), so the key is
    the match and the segment: a Live start at any minute and a Highlights clip share the same fallback lines."""
    key = json.dumps([seed, segment_id, COMMENTARY_PROMPT_VERSION, model_name])
    return cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.json"


def load_cached(path: Path) -> list[dict] | None:
    try:
        return json.loads(path.read_text())["lines"] or None
    except (OSError, ValueError, KeyError):
        return None


def save_cached(path: Path, lines: list[dict]) -> None:
    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"lines": lines}, ensure_ascii=False))
