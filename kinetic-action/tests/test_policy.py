from app import policy

RULES = [{"roles": ["plant_operator"], "when": "target.plant == actor.plant"},
         {"roles": ["plant_manager"]}]
OP_P1 = {"sub": "a", "roles": ["plant_operator"], "plant": "P1"}
NOW = "2026-10-21T00:00:00Z"


def test_allow_when_matches():
    assert policy.evaluate(RULES, OP_P1, {"plant": "P1"}, {}, NOW) == (True, None)


def test_deny_with_reason():
    ok, reason = policy.evaluate(RULES, OP_P1, {"plant": "P2"}, {}, NOW)
    assert not ok and "target.plant == actor.plant" in reason


def test_default_deny_without_rules():
    ok, reason = policy.evaluate([], OP_P1, {"plant": "P1"}, {}, NOW)
    assert not ok and "기본 거부" in reason


def test_roles_filter_rules():
    viewer = {"sub": "v", "roles": ["viewer"], "plant": "P1"}
    ok, reason = policy.evaluate(RULES, viewer, {"plant": "P1"}, {}, NOW)
    assert not ok and "역할" in reason
    manager = {"sub": "m", "roles": ["plant_manager"]}
    assert policy.evaluate(RULES, manager, {"plant": "P9"}, {}, NOW)[0]  # when 생략 = true


def test_empty_roles_means_any_authenticated():
    assert policy.evaluate([{"when": "params.reason != ''"}], {"sub": "x", "roles": []}, {}, {"reason": "r"}, NOW)[0]


def test_eval_error_is_deny():
    ok, reason = policy.evaluate([{"when": "target.missing == 1"}], OP_P1, {"plant": "P1"}, {}, NOW)
    assert not ok and "평가 오류" in reason
    ok, reason = policy.evaluate([{"when": "target.plant =="}], OP_P1, {"plant": "P1"}, {}, NOW)
    assert not ok and "평가 오류" in reason
    ok, reason = policy.evaluate([{"when": "target.plant"}], OP_P1, {"plant": "P1"}, {}, NOW)
    assert not ok and "bool" in reason


def test_key_and_now_variables():
    rule = [{"when": 'target["$key"].startsWith("EQ-") && now > "2026-01-01"'}]
    assert policy.evaluate(rule, OP_P1, {"$key": "EQ-1"}, {}, NOW)[0]


def test_visibility_uses_roles_only():
    assert policy.visible(RULES, OP_P1)
    assert not policy.visible(RULES, {"sub": "v", "roles": ["viewer"]})
    assert policy.visible([{"when": "false"}], {"sub": "v", "roles": []})
    assert not policy.visible([], OP_P1)
