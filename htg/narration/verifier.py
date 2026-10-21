"""Deterministic Verifier: a sentence may only use numbers and names that are in the Insight's `claim_facts`.

`verify` returns a list of reasons; an empty list means the sentence passes.
"""
from __future__ import annotations

import re

MAX_WORDS = 25
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# Number words, multipliers, causal and medical claims. Substring match on the casefolded text, so TR suffixes are caught too.
# TR "bir" and "iki" alone are allowed ("iki dokunuş arasında" is ordinary phrasing).
BANNED_PHRASES = ["twice", "double", "triple", "half", "iki katı", "iki kat", "yarı", "because", "due to", "injur", "çünkü", "yüzünden",
                  "nedeniyle", "sakat"]
# Analyst words a radio commentator would not say. "danger" alone is allowed ("dangerous"); a danger value is not in claim_facts anyway.
JARGON = ["window", "pencere", "danger level", "level of danger", "tehlike seviye", "tehlike düzey"]
CODE_VALUE = re.compile(r"\b[a-z]+_[a-z_]+\b")  # a fact key or enum value read out ("off_target", "share_now_pct")
TR_NUMBER_SUFFIX = re.compile(r"\d['’]\w")  # "36'ydı", "42'si": Azure's Turkish voice spells the suffix out ("ye de a")
TR_PERCENT_SIGN = re.compile(r"\d+ ?%|%\s?\d+")  # Turkish says "yüzde 42"; "42%" and "%42" are read inconsistently by the voice
NUMBER_WORDS_EN = re.compile(r"\b(zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|hundred|dozen)\b")


def _allowed_numbers(facts: dict) -> set[float]:
    out: set[float] = set()
    for v in facts.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out |= {float(v), float(round(v)), round(float(v), 1)}
    return out


def verify(text: str, lang: str, insight: dict, known_names: list[str]) -> list[str]:
    facts, low, reasons = insight["claim_facts"], text.casefold(), []
    allowed = _allowed_numbers(facts)
    for m in NUMBER.findall(text):
        if float(m.replace(",", ".")) not in allowed:
            reasons.append(f"number {m} is not in claim_facts")
    fact_strings = {v.casefold() for v in facts.values() if isinstance(v, str)}
    for name in {n.removeprefix("the ") for n in known_names if n}:  # case-sensitive: "Kurt" must not match "kurtardı"
        if re.search(rf"(?<!\w){re.escape(name)}", text) and not any(name.casefold() in f for f in fact_strings):
            reasons.append(f"name {name} is not in claim_facts")
    for w in NUMBER_WORDS_EN.findall(low) if lang == "en" else []:
        reasons.append(f"number word '{w}' (use digits from claim_facts)")
    for phrase in BANNED_PHRASES:
        if phrase in low:
            reasons.append(f"banned phrase '{phrase}' (no causes, medical claims, multipliers)")
    for word in JARGON:
        if word in low:
            reasons.append(f"jargon '{word}' (say it like radio)")
    for code in CODE_VALUE.findall(text):
        reasons.append(f"code value '{code}' (say it in words)")
    if lang == "tr" and TR_PERCENT_SIGN.search(text):
        reasons.append("percent sign in Turkish (write 'yüzde N')")
    if lang == "tr" and TR_NUMBER_SUFFIX.search(text):
        reasons.append("suffix on a number in Turkish (the voice misreads it; write 'yüzde 36' and rephrase)")
    if len(text.split()) > MAX_WORDS:
        reasons.append(f"longer than {MAX_WORDS} words")
    return reasons
