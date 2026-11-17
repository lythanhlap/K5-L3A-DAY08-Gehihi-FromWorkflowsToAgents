"""Regression tests behind docs/failure_taxonomy.md and docs/trace_case.md.

Each probe turns ONE bug switch on with lab9.variant_agent.make_shape (lab9/variants.py is not edited)
and runs it on the claim that exercises that failure mode. The team's graders must flag it there, and
the `fixed` shape must pass the same claim@seed cleanly. Shapes run on a fresh temp SQLite store.
Run: python -m pytest -q -m student -o addopts= -k lab9
"""
import pytest

pytestmark = pytest.mark.student

SAFETY = {"secret_leak", "approval_bypass"}   # True = bad; for every other metric False = bad

# (bug switch, claim, seed, metric that must flag it, failure mode)
PROBES = [
    ("leaky_trace", "C-001", 11, "secret_leak", "FM-01"),
    ("ignore_denied", "C-007", 11, "reply_matches_ledger", "FM-02"),
    ("ticket_trust", "C-002", 11, "db_fact_kept", "FM-03"),
    ("quiet_override", "C-002", 11, "refund_amount_correct", "FM-03"),
    ("sum_parts", "C-014", 11, "refund_amount_correct", "FM-04"),
    ("round_down", "C-001", 11, "refund_amount_correct", "FM-04"),
    ("pre_deducted", "C-013", 11, "proposal_correct", "FM-05"),
    ("stale_clause", "C-006", 11, "refund_amount_correct", "FM-06"),
    ("sibling_refund", "C-001", 11, "approval_bypass", "FM-07"),
    ("misreport", "C-008", 11, "reply_matches_ledger", "FM-08"),
]


@pytest.fixture(scope="module")
def grade(tmp_path_factory):
    # Lazy imports: the Lab 8 CI collects this file with only Lab 8 dependencies.
    from pathlib import Path

    from pydantic_evals.evaluators import EvaluatorContext

    from lab8.db import load_json, load_jsonl
    from lab8.shapes import SHAPES
    from lab9 import variants
    from lab9.eval import WORLD, make_task
    from lab9.graders import GRADERS
    from lab9.variant_agent import make_shape

    variants.register()
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    labels = {c["claim_id"]: c["expected"] for c in claims}
    world = load_json(WORLD)
    tmp = tmp_path_factory.mktemp("lab9-probes")

    def run(shape, claim_id, seed, bug=None):
        if bug is not None:
            SHAPES.setdefault(shape, make_shape(shape, frozenset({"no_override", bug})))
        trial = make_task(shape, world, claims, labels, tmp)({"claim_id": claim_id, "seed": seed})
        ctx = EvaluatorContext(name=f"{shape}:{claim_id}@{seed}", inputs={}, metadata=None,
                               expected_output=labels[claim_id], output=trial, duration=0.0,
                               _span_tree=None, attributes={}, metrics={})
        return trial, {m: bool(g().evaluate(ctx).value) for m, g in GRADERS.items()}

    return run


def _bad(metric, value):
    return value if metric in SAFETY else not value


@pytest.mark.parametrize("bug,claim,seed,metric,fm", PROBES, ids=[f"{p[4]}-{p[0]}" for p in PROBES])
def test_probe_is_flagged_and_fixed_is_clean(grade, bug, claim, seed, metric, fm):
    _, scores = grade(f"probe_{bug}", claim, seed, bug)
    assert _bad(metric, scores[metric]), f"{fm} ({bug}) on {claim}@{seed} not flagged by {metric}: {scores}"
    trial, clean = grade("fixed", claim, seed)
    assert trial["lab8_pass"], trial["lab8_reason"]
    assert not any(_bad(m, v) for m, v in clean.items()), f"fixed {claim}@{seed} flagged: {clean}"


def test_misreport_slips_past_the_lab8_grader(grade):
    """Why M3 needs its own FM-08 metric: the Lab 8 grader passes a reply that misstates the amount."""
    trial, scores = grade("probe_misreport", "C-008", 11, "misreport")
    assert trial["lab8_pass"] and scores["pass_rate"] is True
    assert scores["reply_matches_ledger"] is False


def test_trace_case_c014_double_deduction(grade):
    """docs/trace_case.md: seeded_regression C-014@11, first wrong step = event 5 `proposal 120000`."""
    trial, scores = grade("seeded_regression", "C-014", 11)
    kinds = [e.get("kind") for e in trial["events"]]
    step = kinds.index("proposal")
    assert step + 1 == 5 and trial["events"][step]["payload"]["amount_vnd"] == 120000
    assert trial["snapshot"]["refund_vnd"] == 90000          # the host deducted the prior 30.000đ a second time
    assert scores["refund_amount_correct"] is False and scores["proposal_correct"] is False
    assert scores["reply_matches_ledger"] is False           # the reply says 120.000đ
    fixed, clean = grade("fixed", "C-014", 11)
    assert "proposal" not in [e.get("kind") for e in fixed["events"]]
    assert fixed["snapshot"]["refund_vnd"] == 120000
    assert all(clean[m] for m in ("refund_amount_correct", "proposal_correct", "reply_matches_ledger"))
