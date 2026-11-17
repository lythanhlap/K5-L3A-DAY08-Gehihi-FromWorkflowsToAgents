"""M3 team graders on hand-built Trials (no shape run): FM-08 reply vs ledger, proposal vs quote.
Run: python -m pytest -q -m student -o addopts= -k lab9"""
import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 20000, "proposal_amount": 35000, "approval_ok": True, "forbid_substrings": []}


@pytest.fixture(scope="module")
def graders():
    # Lazy import: the Lab 8 CI collects this file with only Lab 8 dependencies.
    from lab9 import graders

    return graders


def ctx(trial, label=LABEL):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(refund_vnd=20000, reply=None, proposal=35000):
    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    return {"snapshot": {"refund_vnd": refund_vnd, "refund_count": int(refund_vnd > 0)}, "unexpected_rows": 0,
            "blob": "", "events": events, "result": {"proposal_amount": proposal},
            "lab8_pass": True, "lab8_reason": None}


@pytest.mark.parametrize("text,amounts", [
    ("Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.", [20000]),
    ("LogiX đã hoàn phí 150.000đ cho đơn O-303 của anh/chị ạ.", [150000]),
    ("Đã hoàn 35,000 VND cho đơn O-107.", [35000]),
    ("Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành.", []),
    ("Tiền về trong 3–5 ngày, 2 đơn đã xử lý.", []),
])
def test_amounts_in_reads_money_not_order_ids(graders, text, amounts):
    assert graders.amounts_in(text) == amounts


def test_reply_matches_ledger(graders):
    g = graders.ReplyMatchesLedger()
    assert g.evaluate(ctx(trial(reply="Dạ, LogiX đã hoàn 20.000đ cho đơn O-808."))).value is True
    assert g.evaluate(ctx(trial(reply="Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."))).value is False  # FM-08
    assert g.evaluate(ctx(trial(refund_vnd=0, reply="Dạ, LogiX đã hoàn 35.000đ cho đơn O-909."))).value is False  # FM-02
    assert g.evaluate(ctx(trial(reply=None))).value is True   # the Lab 8 swarm writes no reply event


def test_proposal_correct(graders):
    g = graders.ProposalCorrect()
    assert g.evaluate(ctx(trial(proposal=35000))).value is True
    assert g.evaluate(ctx(trial(proposal=0))).value is False       # FM-05: pre-deducted to zero
    assert g.evaluate(ctx(trial(proposal=30000))).value is False   # FM-04: rounded down


def test_team_metrics_are_registered(graders):
    assert graders.GRADERS["reply_matches_ledger"] is graders.ReplyMatchesLedger
    assert graders.GRADERS["proposal_correct"] is graders.ProposalCorrect
