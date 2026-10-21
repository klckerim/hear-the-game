from htg.engine.director import SILENCE_S, decide


def ins(id_="a", type_="pressure_shift", team="HOME", t=100.0, ttl=120.0, priority=3, **facts):
    return {"insight_id": id_, "type": type_, "team": team, "t": t, "expires_at": t + ttl, "priority": priority, "claim_facts": facts}


DEAD = {"in_play": False, "danger": 0.0}
CALM = {"in_play": True, "danger": 0.05}
ATTACK = {"in_play": True, "danger": 0.6}


def actions(queue, state, now, **kw):
    return [d.action for d in decide(queue, state, now, **kw)]


def test_speaks_when_ball_is_dead_or_calm():
    assert actions([ins()], DEAD, 110) == ["speak"]
    assert actions([ins()], CALM, 110) == ["speak"]


def test_holds_during_an_attack():
    assert actions([ins()], ATTACK, 110) == ["hold"]


def test_goal_speaks_immediately_even_in_an_attack_and_inside_the_budget():
    goal = ins("g", "goal", priority=5, ttl=60)
    assert actions([goal], ATTACK, 101, spoken=[(100.0, "tempo_change", "AWAY")]) == ["speak"]


def test_drops_danger_only_chance_but_speaks_a_shot():
    assert actions([ins(type_="chance", priority=4, source="danger")], DEAD, 110) == ["drop"]
    assert actions([ins(type_="chance", priority=4, source="shot")], DEAD, 110) == ["speak"]


def test_drops_expired():
    assert actions([ins(ttl=30)], DEAD, 131) == ["drop"]
    assert actions([ins(ttl=30)], DEAD, 129) == ["speak"]


def test_drops_same_type_and_team_within_five_minutes_only():
    spoken = [(0.0, "pressure_shift", "HOME")]
    assert actions([ins(t=200, ttl=1000)], DEAD, 299, spoken=spoken) == ["drop"]
    assert actions([ins(t=290, ttl=1000, team="AWAY")], DEAD, 299, spoken=spoken) == ["speak"]
    assert actions([ins(t=290, ttl=1000, type_="tempo_change")], DEAD, 299, spoken=spoken) == ["speak"]
    assert actions([ins(t=290, ttl=1000)], DEAD, 301, spoken=spoken) == ["speak"]


def test_silence_budget_depends_on_mode():
    spoken = [(100.0, "tempo_change", "AWAY")]
    gap = SILENCE_S["eyes_free"] + 1
    assert actions([ins()], DEAD, 100 + gap, mode="eyes_free", spoken=spoken) == ["speak"]
    assert actions([ins()], DEAD, 100 + gap, mode="casual", spoken=spoken) == ["hold"]


def test_one_at_a_time_highest_priority_first():
    q = [ins("low", "tempo_change", priority=2), ins("high", "physical_drop", priority=4)]
    assert [(d.insight["insight_id"], d.action) for d in decide(q, DEAD, 110)] == [("low", "hold"), ("high", "speak")]


def test_unknown_mode_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        decide([], DEAD, 0, mode="loud")
