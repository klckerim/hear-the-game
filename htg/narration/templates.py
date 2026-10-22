"""Deterministic one-sentence narration per Insight type, EN and TR.

Numbers and names come only from `claim_facts`. This is the fallback the Verifier uses (Day 3) and today's narration.
Turkish sentences avoid suffixes on names and numbers ("yüzde 44", "{team} için") so they stay grammatical without morphology.
"""
from __future__ import annotations

OUTCOME_EN = {"saved": "the keeper saves it", "off_target": "it goes off target", "blocked": "it is blocked"}
OUTCOME_TR = {"saved": "kaleci kurtardı", "off_target": "top auta gitti", "blocked": "şut engellendi"}


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _poss(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")  # "Valemont's", "the Whites'"


def _tr_num(x: float) -> str:
    return str(x).replace(".", ",")  # Turkish decimal comma, so the voice reads "2,3" as a number


def _en(i: dict) -> str:
    f, ty = i["claim_facts"], i["type"]
    team, opp = _cap(f["team_en"]), f.get("opponent_en")
    last = f"in the last {f.get('recent_min')} minutes"
    if ty == "pressure_shift":
        return (f"{team} are pressing harder: {f['share_now_pct']}% of {_poss(opp)} actions are under pressure {last}, "
                f"{f['share_before_pct']}% earlier in the match.")
    if ty == "tempo_change":
        return (f"{team} are slowing the game down: about {f['gap_now_s']} seconds per touch {last}, "
                f"{f['gap_before_s']} earlier in the match.")
    if ty == "flank_overload":
        return (f"{team} keep going down the {f['side']}: {f['share_now_pct']}% of their passes end there {last}, "
                f"{f['share_before_pct']}% earlier in the match.")
    if ty == "physical_drop":
        return f"{f['player']} of {f['team_en']} is tiring: high-speed running {last} is down to {f['hsr_now_pct']}% of the earlier amount."
    if ty == "goal":
        return f"Goal! {f['player']} scores for {f['team_en']}. It is now {f['home_score']}-{f['away_score']}."
    if ty == "chance" and f["source"] == "shot":
        return f"{team} have a chance: {f['player']} shoots, {OUTCOME_EN.get(f['outcome'], 'it does not count')}."
    return f"{team} are bearing down on goal."


def _tr(i: dict) -> str:
    f, ty = i["claim_facts"], i["type"]
    team, opp = f["team_tr"], f.get("opponent_tr")
    last = f"Son {f.get('recent_min')} dakikada"
    if ty == "pressure_shift":
        return (f"{team} baskıyı artırdı. {last} {opp} için baskı altındaki hareket oranı yüzde {f['share_now_pct']}, "
                f"maçın önceki bölümünde yüzde {f['share_before_pct']}.")
    if ty == "tempo_change":
        return (f"{team} oyunu yavaşlattı. {last} dokunuş başına yaklaşık {_tr_num(f['gap_now_s'])} saniye, "
                f"maçın önceki bölümünde {_tr_num(f['gap_before_s'])}.")
    if ty == "flank_overload":
        return (f"{team} {f['side_tr']} kanada yükleniyor. {last} pasların bu bölgede bitme oranı yüzde {f['share_now_pct']}, "
                f"maçın önceki bölümünde yüzde {f['share_before_pct']}.")
    if ty == "physical_drop":
        return (f"{f['player']} ({team}) yoruluyor: son {f.get('recent_min')} dakikadaki yüksek tempolu koşusu, "
                f"önceki bölümün yüzde {f['hsr_now_pct']} kadarı.")
    if ty == "goal":
        return f"Gol! {f['player']} {team} için attı. Skor {f['home_score']}-{f['away_score']}."
    if ty == "chance" and f["source"] == "shot":
        return f"{team} için fırsat: {f['player']} vurdu, {OUTCOME_TR.get(f['outcome'], 'sonuçlanmadı')}."
    return f"{team} kaleye yaklaşıyor."


def narrate(insight: dict, lang: str = "en") -> str:
    """One deterministic sentence for an Insight. `lang` is "en" or "tr"."""
    if lang not in ("en", "tr"):
        raise ValueError(f"unsupported language: {lang}")
    return _en(insight) if lang == "en" else _tr(insight)
