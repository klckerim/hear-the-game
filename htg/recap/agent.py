"""Recap agent: "What did I miss?" and the full-time recap, written by a Foundry agent that calls the deterministic tools.

The agent (a Foundry Agent Service prompt agent with function tools, called through the Responses API) chooses which tools to call,
at most `MAX_TOOL_CALLS`, then writes 2-3 sentences per language. Every sentence goes through the same Verifier as the narration,
with the values the tools returned in this run as the known facts. A failing sentence is dropped; a language with no surviving
sentence gets the template recap. Numbers come from the tools, words from the model.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Protocol

from htg.narration.verifier import verify
from htg.recap.tools import MatchRecord, get_insights, get_player, get_score, get_stats
from htg.telemetry import tracer

LANGS = ("en", "tr")
RECAP_VERSION = 6  # part of the cache key and the agent's metadata: bump when the instructions or the tools change
AGENT_NAME = "htg-recap"
MAX_TOOL_CALLS = 4
MAX_ROUNDS = 6  # model turns; a model that keeps asking for tools after the limit ends in the template
MAX_SENTENCES = 3
MIN_SENTENCES = 1  # fewer surviving sentences in a language -> the template recap for it
EVEN_PCT = 52  # the template calls possession "even" up to this share
# a result said before the final whistle ("the match finished as a draw" at half-time)
RESULT = {"en": re.compile(r"\b(won|drew|a draw|full[- ]time|final (score|whistle)|finished|(match|game) is over)\b", re.I),
          "tr": re.compile(r"(berabere (bitti|kaldı|tamamla\w*)|maç\w* (bitti|sona erdi|kazan\w*|kaybet\w*)|maç sonu\w*|"
                           r"takımın (kazandı|kaybetti)|galip)", re.I)}
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "recap"
AUDIO_DIR = CACHE_DIR / "audio"  # recap clips apart from the narration clips, which the narration pregen prunes

_WINDOW = {"from_min": {"type": ["number", "null"], "description": "First match minute of the window; null = kick-off"},
           "to_min": {"type": ["number", "null"], "description": "Last match minute of the window; null = now"}}
TOOLS = [
    {"type": "function", "name": "get_score", "description": "Score now, minutes played, period, full time or not, and every goal so far "
     "(minute, team, scorer).", "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    {"type": "function", "name": "get_stats", "description": "Per team in a window: possession_pct, shots, shots_on_target, "
     "pass_completion_pct, pressing_pct, corners, fouls.",
     "parameters": {"type": "object", "properties": _WINDOW, "required": list(_WINDOW), "additionalProperties": False}},
    {"type": "function", "name": "get_insights", "description": "Tactical and physical Insights detected in a window (pressing, tempo, "
     "flank, tiring players, shots), each with its facts.",
     "parameters": {"type": "object", "properties": _WINDOW, "required": list(_WINDOW), "additionalProperties": False}},
    {"type": "function", "name": "get_player", "description": "One player in a window: touches, passes, pass_completion_pct, shots, "
     "high-speed running per minute and as a percentage of his earlier level.",
     "parameters": {"type": "object", "properties": {"player": {"type": "string", "description": "Player name or id"}, **_WINDOW},
                    "required": ["player", *_WINDOW], "additionalProperties": False}},
]

INSTRUCTIONS = (
    "You write short radio recaps of a football match for listeners who cannot see it. You get the moment of the match, the minute "
    "the listener's recap starts from, the listener's favourite club (or none) and a persona.\n"
    "Steps: call the tools you need (at most 4 calls; get_score first is usually right), then answer.\n"
    "Answer with JSON only: {\"en\": [2-3 sentences], \"tr\": [2-3 sentences], \"tools_used\": [tool names]}.\n"
    "Rules for every sentence:\n"
    "- One idea per sentence, at most 18 words. Radio tone. Lead with the score or a goal if there was one.\n"
    "- Use only facts from the tool results of this conversation. Copy numbers as digits exactly. Never name a team or a player that "
    "is not in a tool result. No causes, no injuries, no feelings, no weather or crowd, nothing the tools did not measure.\n"
    "- At full time say who won, lost or drew ('your team won', 'takımın kazandı'), not who is ahead.\n"
    "- Possession is '60% of the ball' / 'topun yüzde 60 kadarı'.\n"
    "- Never read out a key or a code value such as pressure_shift or off_target; say it in words.\n"
    "- Never use the words half, double, twice, window, level, data; in Turkish never yarı, pencere, seviye, veri. Say 'before the "
    "break' / 'after the break' in English and 'ilk devre' / 'ikinci devre' in Turkish. No number words (two, three): digits only.\n"
    "- When a favourite club is given, tell it from that club's side: 'your team' / 'takımın', and lead with what matters to them.\n"
    "- Turkish: the voice spells out any suffix stuck to a number, so a Turkish number must stand alone, followed only by a space and "
    "a plain word, a comma or a full stop. Never 22'de, 87de, 87 de, 60'ı, 50sine, 12'ye, 1-2'lik. Rewrite like this: "
    "'dakika 79'da gol attı' -> 'Arda gol attı, dakika 79.'; 'topun yüzde 60'ına sahip' -> 'topun yüzde 60 kadarı onlarda'; "
    "'12 şutla' -> '12 şut çekti'; '1-2'lik skor' -> 'skor 1-2'; 'dakika 57'den beri' -> 'son 10 dakikada' or "
    "'dakika 57 sonrası'. Percentages are 'yüzde 42' (never % or %42).\n"
    "- The Turkish sentences say the same as the English ones.\n"
    "Example (teams Eastbrook and Westmere, favourite Westmere, fan; not this match's facts):\n"
    "{\"en\": [\"It is Eastbrook 1, Westmere 2, and your team are ahead.\", \"Kowalski scored for your team in minute 74.\", "
    "\"Eastbrook have had more of the ball since then, but only 1 shot.\"], "
    "\"tr\": [\"Skor Eastbrook 1, Westmere 2; takımın önde.\", \"Takımının golünü Kowalski attı, dakika 74.\", "
    "\"O andan beri top daha çok Eastbrook tarafında, ama yalnızca 1 şut var.\"], \"tools_used\": [\"get_score\", \"get_stats\"]}"
)
PERSONA = {
    "fan": "Persona: fan. Warm and lively, for a casual fan. Numbers only for the score and goal minutes; say other stats in words "
           "that the numbers support ('Valemont had far more shots').",
    "analyst": "Persona: analyst. Precise: give the key numbers and a comparison between the teams; at most 3 numbers per sentence.",
}


class RecapModel(Protocol):
    """One model turn. Returns (response_id, function calls [{"name", "arguments", "call_id"}], final text)."""

    name: str

    def respond(self, input: Any, previous_id: str | None) -> tuple[str, list[dict], str]: ...


class FoundryRecapAgent:
    """The recap agent in Foundry Agent Service: a prompt agent with the four function tools, run with the Responses API.

    The agent version is created once per `RECAP_VERSION` (found again by its metadata on later starts)."""

    def __init__(self) -> None:
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition, Reasoning
        from azure.identity import DefaultAzureCredential

        project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=DefaultAzureCredential())
        model = os.environ["FOUNDRY_MODEL"]
        self.name = f"foundry-agent:{model}"
        version = _find_version(project, str(RECAP_VERSION))
        if version is None:
            effort = os.environ.get("FOUNDRY_REASONING_EFFORT", "").strip()
            definition = PromptAgentDefinition(model=model, instructions=INSTRUCTIONS, tools=TOOLS,
                                               reasoning=Reasoning(effort=effort) if effort else None)
            version = project.agents.create_version(agent_name=AGENT_NAME, definition=definition,
                                                    metadata={"recap_version": str(RECAP_VERSION)},
                                                    description="Hear the Game recap agent: calls deterministic match tools").version
        self.ref = {"agent_reference": {"name": AGENT_NAME, "version": str(version), "type": "agent_reference"}}
        self.client = project.get_openai_client()

    def respond(self, input: Any, previous_id: str | None) -> tuple[str, list[dict], str]:
        extra = {"previous_response_id": previous_id} if previous_id else {}
        r = self.client.responses.create(input=input, extra_body=self.ref, **extra)
        calls = [{"name": o.name, "arguments": o.arguments, "call_id": o.call_id} for o in r.output if o.type == "function_call"]
        return r.id, calls, r.output_text or ""


def _find_version(project: Any, recap_version: str) -> str | None:
    try:
        for v in project.agents.list_versions(agent_name=AGENT_NAME):
            if (v.metadata or {}).get("recap_version") == recap_version:
                return v.version
    except Exception:  # the agent does not exist yet
        return None
    return None


def get_recap_model() -> RecapModel | None:
    """The Foundry agent with HTG_ENV=azure; None (template recap only) locally or when Azure is unreachable."""
    if os.environ.get("HTG_ENV", "local") != "azure":
        return None
    try:
        return FoundryRecapAgent()
    except Exception as e:
        print(f"Recap agent unavailable ({type(e).__name__}: {e}); using the template recap.")
        return None


# ---------------------------------------------------------------------------------------------------------------- tools
def call_tool(rec: MatchRecord, t: float, name: str, args: dict) -> dict:
    """Runs one tool for the agent. `t` is fixed by the request: the model cannot ask about later moments."""
    w = {"from_min": args.get("from_min"), "to_min": args.get("to_min")}
    if name == "get_score":
        return get_score(rec, t)
    if name == "get_stats":
        return get_stats(rec, t, **w)
    if name == "get_insights":
        return get_insights(rec, t, **w)
    if name == "get_player":
        return get_player(rec, t, str(args.get("player", "")), **w)
    return {"error": f"unknown tool {name}"}


def _scalars(x: Any, out: dict[str, Any], key: str = "") -> dict[str, Any]:
    """Every scalar in a tool result, flattened to {path: value}: the facts a recap sentence may use."""
    if isinstance(x, dict):
        for k, v in x.items():
            _scalars(v, out, f"{key}.{k}" if key else k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _scalars(v, out, f"{key}.{i}")
    elif isinstance(x, (int, float, str)) and not isinstance(x, bool):
        out[key] = x
    return out


def verify_recap(sentences: list[str], lang: str, facts: dict[str, Any], names: list[str],
                 full_time: bool = True) -> tuple[list[str], list[str]]:
    """(kept, reasons): sentences that pass the narration Verifier against the tool facts; at most MAX_SENTENCES.
    Before full time a sentence that calls the result (won, drew, the match finished) is rejected too."""
    kept, reasons = [], []
    pseudo = {"claim_facts": facts}
    for s in sentences:
        s = str(s).strip()
        bad = verify(s, lang, pseudo, names) if s else ["empty"]
        if s and not full_time and RESULT[lang].search(s):
            bad = [*bad, "result before full time"]
        if bad:
            reasons += [f"{s[:60]!r}: {', '.join(bad)}"]
        else:
            kept.append(s)
    return kept[:MAX_SENTENCES], reasons


# ---------------------------------------------------------------------------------------------------------------- template
def template_recap(rec: MatchRecord, t: float, since_min: float) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Deterministic recap from the same tools: score, the spell's possession and shots, the last goal in the spell."""
    sc, st = get_score(rec, t), get_stats(rec, t, since_min, None)
    H, A = sc["home"], sc["away"]
    h, a, m = sc["home_score"], sc["away_score"], sc["minutes_played"]
    top = st["home"] if (st["home"]["possession_pct"] or 0) >= (st["away"]["possession_pct"] or 0) else st["away"]
    whole = since_min <= 0
    en = [f"Full time: {H['team_en']} {h}, {A['team_en']} {a}." if sc["full_time"]
          else f"After {m} minutes it is {H['team_en']} {h}, {A['team_en']} {a}."]
    tr = [f"Maç bitti: {H['team_tr']} {h}, {A['team_tr']} {a}." if sc["full_time"]
          else f"Skor {H['team_tr']} {h}, {A['team_tr']} {a}; oynanan süre {m} dakika."]
    if top["possession_pct"] is not None:
        span_en, span_tr = ("Over the match", "Maç boyunca") if whole else (f"In the last {st['length_min']} minutes",
                                                                          f"Son {st['length_min']} dakikada")
        shots_en = f"shots: {H['team_en']} {st['home']['shots']}, {A['team_en']} {st['away']['shots']}."
        shots_tr = f"Şutlar: {H['team_tr']} {st['home']['shots']}, {A['team_tr']} {st['away']['shots']}."
        if top["possession_pct"] <= EVEN_PCT:
            en.append(f"{span_en} possession was even; {shots_en}")
            tr.append(f"{span_tr} topa sahip olma dengeliydi. {shots_tr}")
        else:
            en.append(f"{span_en} {top['team_en']} had {top['possession_pct']}% of the ball; {shots_en}")
            tr.append(f"{span_tr} topa en çok {top['team_tr']} sahip oldu, yüzde {top['possession_pct']}. {shots_tr}")
    goals = [g for g in sc["goals"] if g["minute"] >= since_min]
    if goals and goals[-1]["player"]:
        g = goals[-1]
        en.append(f"The latest goal: {g['player']} for {g['team_en']} in minute {g['minute']}.")
        tr.append(f"Son gol: {g['player']}, {g['team_tr']} için, dakika {g['minute']}.")
    return {"en": en, "tr": tr}, _scalars([sc, st], {})


# ---------------------------------------------------------------------------------------------------------------- agent loop
def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        out = json.loads(m.group()) if m else {}
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


def _request(rec: MatchRecord, t: float, since_min: float, favourite: str | None, persona: str) -> str:
    teams = {side.lower(): {"team_en": rec.team_name(side)["en"], "team_tr": rec.team_name(side)["tr"],
                            "players": [p["name"] for p in rec.meta["teams"][side]["players"]]} for side in ("HOME", "AWAY")}
    fav = {"team_en": rec.team_name(favourite)["en"], "team_tr": rec.team_name(favourite)["tr"]} if favourite else None
    if since_min > 0:
        kind = f"what the listener missed since minute {int(since_min)}"
    elif get_score(rec, t)["full_time"]:
        kind = "full-time recap of the whole match"
    elif t < 45 * 60:  # an early "Catch me up" (before minute 10) also asks from minute 0, but there has been no break yet
        kind = "what the listener missed since kick-off: the first period is still being played"
    else:  # the half-time break: the match is not over, so no won/lost/drew
        kind = ("half-time recap of the first 45 minutes: the match is NOT over and the second period is still to play; give the "
                "score at the break ('at the break' / 'ilk devre sonunda'), never say who won, lost or drew or that the match finished")
    return json.dumps({"task": kind, "now_minute": int(t // 60), "recap_from_minute": int(since_min), "favourite_club": fav,
                       "persona": persona, "persona_style": PERSONA[persona], "teams": teams}, ensure_ascii=False)


def _check(draft: dict, facts: dict[str, Any], names: list[str], full_time: bool) -> dict[str, tuple[list[str], list[str], int]]:
    out = {}
    for lang in LANGS:
        sents = draft.get(lang) if isinstance(draft.get(lang), list) else []
        kept, reasons = verify_recap(sents, lang, facts, names, full_time)
        out[lang] = (kept, reasons, len(sents))
    return out


def run_agent(rec: MatchRecord, t: float, since_min: float, favourite: str | None, persona: str, model: RecapModel,
              names: list[str]) -> dict[str, Any]:
    """The tool-calling loop, then the Verifier, then at most one revision with the Verifier's reasons. Raises on model errors.

    Returns {"text": {lang: kept sentences}, "reasons", "verifier": {"first"|"final": {lang: [passed, total]}}, "revised",
    "tools_used"}."""
    facts: dict[str, Any] = {}
    tools_used: list[str] = []
    tool_args: list[dict] = []
    prev, inp, text = None, _request(rec, t, since_min, favourite, persona), ""
    for _ in range(MAX_ROUNDS):
        prev, calls, text = model.respond(inp, prev)
        if not calls:
            break
        inp = []
        for c in calls:
            if len(tools_used) >= MAX_TOOL_CALLS:
                out = {"error": "tool call limit reached: write the recap now from the results you have"}
            else:
                try:
                    args = json.loads(c["arguments"] or "{}")
                except ValueError:
                    args = {}
                args = args if isinstance(args, dict) else {}
                out = call_tool(rec, t, c["name"], args)
                tools_used.append(c["name"])
                tool_args.append({"name": c["name"], **args})
                _scalars(out, facts, f"r{len(tools_used)}")
            inp.append({"type": "function_call_output", "call_id": c["call_id"], "output": json.dumps(out, ensure_ascii=False)})
    else:
        text = ""  # still asking for tools after MAX_ROUNDS
    full_time = get_score(rec, t)["full_time"]
    first = _check(_parse(text), facts, names, full_time)
    final, revised = dict(first), False
    problems = {lang: r for lang, (_, r, _) in first.items() if r}
    if text and problems:  # one revision: the agent sees why sentences were rejected
        revised = True
        _, _, text2 = model.respond(json.dumps({"fix_these_problems": problems, "instruction": "Rewrite the whole answer in the "
                                                "same JSON format, with no tool calls, fixing these problems."}), prev)
        second = _check(_parse(text2), facts, names, full_time)
        for lang in problems:
            if len(second[lang][0]) > len(first[lang][0]):  # more sentences survive (every kept sentence passed)
                final[lang] = second[lang]
    return {"text": {lang: final[lang][0] for lang in LANGS},
            "reasons": {lang: first[lang][1] for lang in LANGS if first[lang][1]},
            "verifier": {k: {lang: [len(v[lang][0]), v[lang][2]] for lang in LANGS} for k, v in (("first", first), ("final", final))},
            "revised": revised, "tools_used": tools_used, "tool_args": tool_args}


def fingerprint(match_id: str, t: float, since_min: float, favourite: str | None, persona: str, model: str) -> str:
    key = [match_id, round(t, 1), since_min, favourite, persona, RECAP_VERSION, model]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:32]


def write_recap(rec: MatchRecord, t: float, since_min: float, favourite: str | None, persona: str, model: RecapModel | None,
                names: list[str], cache_dir: Path | None = CACHE_DIR) -> dict[str, Any]:
    """{"en": [...], "tr": [...], "source": {lang: "agent"|"template"}, "tools_used", "reasons", "latency_s", "cached"}. Never raises.

    One span per recap with the tool calls, the Verifier result and the source; the agent's model calls nest under it."""
    with tracer.start_as_current_span("htg.recap") as span:
        span.set_attribute("recap.since_min", since_min)
        span.set_attribute("persona", persona)
        span.set_attribute("favourite", favourite or "")
        result = _write(rec, t, since_min, favourite, persona, model, names, cache_dir)
        span.set_attribute("cached", result["cached"])
        span.set_attribute("recap.tools_used", ",".join(result["tools_used"]))
        span.set_attribute("verifier.reasons", "; ".join(f"{k}: {' | '.join(v)}" for k, v in result["reasons"].items())[:2000])
        for lang in LANGS:
            span.set_attribute(f"source.{lang}", result["source"][lang])
        return result


def _write(rec: MatchRecord, t: float, since_min: float, favourite: str | None, persona: str, model: RecapModel | None,
           names: list[str], cache_dir: Path | None) -> dict[str, Any]:
    path = None
    if model is not None and cache_dir is not None:
        path = cache_dir / f"{fingerprint(rec.meta['match_id'], t, since_min, favourite, persona, model.name)}.json"
        if path.exists():
            return {**json.loads(path.read_text()), "cached": True}
    t0 = time.perf_counter()
    template, _ = template_recap(rec, t, since_min)
    out: dict[str, Any] = {"source": {lang: "template" for lang in LANGS}, "tools_used": [], "reasons": {}, **template}
    errored = model is None
    if model is not None:
        try:
            run = run_agent(rec, t, since_min, favourite, persona, model, names)
            out.update(tools_used=run["tools_used"], tool_args=run["tool_args"], reasons=run["reasons"], verifier=run["verifier"],
                       revised=run["revised"])
            for lang in LANGS:
                if len(run["text"][lang]) >= MIN_SENTENCES:
                    out[lang], out["source"][lang] = run["text"][lang], "agent"
        except Exception as e:  # model or network failure: the template recap carries on
            errored, out["reasons"]["error"] = True, [f"{type(e).__name__}: {e}"[:200]]
    out["latency_s"] = round(time.perf_counter() - t0, 3)
    if path is not None and not errored:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False))
    return {**out, "cached": False}
