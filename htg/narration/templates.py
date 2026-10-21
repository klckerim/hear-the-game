"""Deterministic one-sentence narration per Insight type, EN and TR.

Numbers and names come only from `claim_facts`. This is the fallback the Verifier uses (Day 3) and today's narration.
Turkish sentences avoid suffixes on names and numbers ("yüzde 44", "{team} için") so they stay grammatical without morphology.
"""
from __future__ import annotations

OUTCOME_EN = {"saved": "the keeper saves it", "off_target": "it goes off target", "blocked": "it is blocked"}
OUTCOME_TR = {"saved": "kaleci kurtardı", "off_target": "top auta gitti", "blocked": "şut engellendi"}


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _en(i: dict) -> str:
    f, ty = i["claim_facts"], i["type"]
    team, opp = _cap(f["team_en"]), f["opponent_en"]
    if ty == "pressure_shift":
        return (f"{team} have stepped up their press: {f['share_now_pct']}% of {opp}' actions are now under pressure, "
                f"up from {f['share_before_pct']}%.")
    if ty == "tempo_change":
        return (f"{team} have slowed down: the typical gap between their touches is now {f['gap_now_s']} seconds, "
                f"up from {f['gap_before_s']}.")
    if ty == "flank_overload":
        return (f"{team} are leaning on their {f['side']} flank: {f['share_now_pct']}% of their passes now end there, "
                f"up from {f['share_before_pct']}%.")
    if ty == "physical_drop":
        return f"{f['player']} of {f['team_en']} is fading: high-speed running is down to {f['hsr_now_pct']}% of the earlier level."
    if ty == "goal":
        return f"Goal! {f['player']} scores for {f['team_en']}. It is now {f['home_score']}-{f['away_score']}."
    if ty == "chance" and f["source"] == "shot":
        return f"{team} have a chance: {f['player']} shoots, {OUTCOME_EN.get(f['outcome'], 'it does not count')}."
    return f"{team} are in a dangerous position."


def _tr(i: dict) -> str:
    f, ty = i["claim_facts"], i["type"]
    team, opp = f["team_tr"], f["opponent_tr"]
    if ty == "pressure_shift":
        return (f"{team} presi artırdı. {opp} için baskı altındaki hareket oranı yüzde {f['share_now_pct']}, "
                f"öncesinde yüzde {f['share_before_pct']}.")
    if ty == "tempo_change":
        return f"{team} oyunu yavaşlattı: iki dokunuş arasındaki süre {f['gap_now_s']} saniye, öncesinde {f['gap_before_s']}."
    if ty == "flank_overload":
        return (f"{team} {f['side_tr']} kanada yükleniyor. Pasların bu bölgede bitme oranı yüzde {f['share_now_pct']}, "
                f"öncesinde yüzde {f['share_before_pct']}.")
    if ty == "physical_drop":
        return f"{f['player']} ({team}) yoruluyor: yüksek tempolu koşusu önceki düzeyin yüzde {f['hsr_now_pct']} seviyesine düştü."
    if ty == "goal":
        return f"Gol! {f['player']} {team} için attı. Skor {f['home_score']}-{f['away_score']}."
    if ty == "chance" and f["source"] == "shot":
        return f"{team} için fırsat: {f['player']} vurdu, {OUTCOME_TR.get(f['outcome'], 'sonuçlanmadı')}."
    return f"{team} tehlikeli bölgede."


def narrate(insight: dict, lang: str = "en") -> str:
    """One deterministic sentence for an Insight. `lang` is "en" or "tr"."""
    if lang not in ("en", "tr"):
        raise ValueError(f"unsupported language: {lang}")
    return _en(insight) if lang == "en" else _tr(insight)
