"""M5-M7 team checks on hand-built reports: eval-gaming moves beyond the public traps.
Run: python -m pytest -q -m student -o addopts= -k advanced"""
import copy

import pytest

pytestmark = pytest.mark.student

ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["denial"] if i < 2 else []}
        for i in range(4) for s in (1, 2)]
SPEC = {"eval_set_version": "v2", "eval_set": "data/eval/eval_set_v2.jsonl",
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.8}}],
        "slices": [{"name": "denial", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True,
                    "blocking": True}]}


def _report(rows, metrics=None, items=4, seeds=(1, 2), failures=()):
    vals = [r["pass_rate"] for r in rows]
    metrics = {"pass_rate": sum(vals) / len(vals)} if metrics is None else metrics
    return {"manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)},
            "rows": rows, "metrics": metrics, "evaluator_failures": list(failures)}


@pytest.fixture(scope="module")
def gate():
    from lab9 import gate

    return gate


def test_clean_report_is_trusted(gate):
    base = _report(copy.deepcopy(ROWS))
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


def test_duplicated_row_in_place_of_a_failing_one(gate):
    base = _report(copy.deepcopy(ROWS))
    rows = copy.deepcopy(ROWS)
    rows[1] = dict(rows[0])                       # (E-000, 2) failed; replaced by a copy of (E-000, 1)
    problems = gate.integrity_check(_report(rows), base, SPEC)
    assert any("duplicated" in p for p in problems)


def test_evaluator_failures_on_a_green_run(gate):
    base = _report(copy.deepcopy(ROWS))
    green = _report(copy.deepcopy(ROWS), failures=["E-001@1:RefundAmountCorrect:KeyError"])
    assert gate.integrity_check(green, base, SPEC)


def test_headline_metric_edited_by_hand(gate):
    base = _report(copy.deepcopy(ROWS))
    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = False
    edited = _report(rows, metrics={"pass_rate": 1.0})   # rows say 0.875
    assert any("rows give" in p for p in gate.integrity_check(edited, base, SPEC))


def test_item_relabelled_out_of_a_slice(gate):
    base = _report(copy.deepcopy(ROWS))
    rows = copy.deepcopy(ROWS)
    for r in rows:
        if r["item_id"] == "E-000":
            r["slices"] = []
    assert any("slice tags" in p for p in gate.integrity_check(_report(rows), base, SPEC))


@pytest.mark.parametrize("loosen", [
    lambda s: s.update(slices=[]),                                          # slice removed
    lambda s: s["slices"][0].pop("no_significant_drop"),                    # slice CI check dropped
    lambda s: s["slices"][0].update(min=0.5),                               # slice floor lowered
    lambda s: s["metrics"][0].update(blocking=False),                       # metric made advisory
    lambda s: s.update(metrics=[]),                                         # metric removed
    lambda s: s.update(eval_set_version="v2.1", slices=[]),                 # new label, same eval set
    lambda s: s.update(bootstrap={"rng": 7}),                               # re-rolled bootstrap
], ids=["slice-removed", "slice-nsd-dropped", "slice-min-lowered", "non-blocking", "metric-removed",
        "relabelled-version", "bootstrap-reroll"])
def test_ratchet_blocks_looser_specs(gate, loosen):
    base_spec = copy.deepcopy(SPEC)
    base_spec["bootstrap"] = {"rng": 2027}
    spec = copy.deepcopy(base_spec)
    loosen(spec)
    base = _report(copy.deepcopy(ROWS))
    assert any("ratchet" in p for p in gate.integrity_check(base, base, spec, base_spec))


def test_ratchet_allows_stricter_and_new_eval_sets(gate):
    base = _report(copy.deepcopy(ROWS))
    stricter = copy.deepcopy(SPEC)
    stricter["metrics"][0]["threshold"]["min"] = 0.9
    assert gate.integrity_check(base, base, stricter, SPEC) == []
    new_set = dict(copy.deepcopy(SPEC), eval_set_version="v3", eval_set="data/eval/eval_set_v3.jsonl", slices=[])
    assert gate.integrity_check(base, base, new_set, SPEC) == []


def test_slice_ci_blocks_a_drop_even_above_the_floor(gate):
    rows = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["money_movement"]}
            for i in range(12) for s in range(5)]
    base = _report(rows, items=12, seeds=range(5))
    pr_rows = copy.deepcopy(rows)
    for r in pr_rows:
        if r["seed"] == 0:
            r["pass_rate"] = False                # every item drops from 1.0 to 0.8
    spec = {"slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.5,
                        "no_significant_drop": True, "blocking": True}]}
    blocked, _ = gate.slice_check(_report(pr_rows, items=12, seeds=range(5)), base, spec)
    assert blocked == ["slice:money_movement/pass_rate"]


def test_paired_bootstrap_with_no_items_is_zero():
    from lab9 import stats

    assert stats.paired_bootstrap([], []) == (0.0, 0.0, 0.0)
