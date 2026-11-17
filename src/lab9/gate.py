"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)
    Also refused: duplicated (item, seed) rows, a baseline that itself had evaluator failures, and
    headline metrics that do not match what the rows recompute to (metrics edited by hand)."""
    problems: list[str] = []
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []

    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}")

    man = pr.get("manifest") or {}
    want = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows but the manifest promises {man.get('items')} items x "
                        f"{len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dupes = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dupes:
        problems.append(f"duplicated (item, seed) rows: {dupes[:5]}")
    have, base_keys = set(keys), {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if have != base_keys:
        gone, extra = sorted(base_keys - have, key=str), sorted(have - base_keys, key=str)
        problems.append(f"(item, seed) set differs from the baseline: missing {gone[:5]}"
                        f"{' …' if len(gone) > 5 else ''}, extra {extra[:5]}{' …' if len(extra) > 5 else ''}")

    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the PR run, "
                        f"first: {pr['evaluator_failures'][0]}")
    if base.get("evaluator_failures"):
        problems.append(f"{len(base['evaluator_failures'])} evaluator failure(s) in the baseline run")

    graded = [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS]
    present = [m for m in graded if any(m in r for r in rows) or any(m in r for r in base_rows)]
    for m in present:
        broken = [r for r in rows if not _finite(r.get(m))]
        if broken:
            problems.append(f"{len(broken)} row(s) with no value for graded metric {m} "
                            f"(e.g. {broken[0].get('item_id')}@{broken[0].get('seed')})")
        elif m in (pr.get("metrics") or {}) and _finite(pr["metrics"][m]):
            vals = [r[m] for r in rows]
            again = sum(vals) if m in COUNT_METRICS else (sum(vals) / len(vals) if vals else None)
            if again is not None and abs(float(pr["metrics"][m]) - again) > 1e-4:
                problems.append(f"metric {m} = {pr['metrics'][m]} but the rows give {round(again, 4)}")

    base_tags = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in base_tags and sorted(r.get("slices") or []) != base_tags[r.get("item_id")]},
                   key=str)
    if moved:
        problems.append(f"slice tags differ from the baseline for {moved[:5]}")

    if base_spec is not None and _same_eval_set(spec, base_spec):
        problems += _ratchet(spec, base_spec)
    return problems


COUNT_METRICS = ("secret_leak", "approval_bypass")   # aggregated as counts in lab9.eval.aggregate


def _finite(v) -> bool:
    return isinstance(v, (bool, int, float)) and math.isfinite(float(v))


def _same_eval_set(spec: dict, base_spec: dict) -> bool:
    """The ratchet binds while the eval set is the same: same eval_set_version, or the same eval-set
    file under a new version label (bumping only the label must not reset thresholds)."""
    if spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        return True
    return bool(spec.get("eval_set")) and spec.get("eval_set") == base_spec.get("eval_set")


def _looser(th: dict, base_th: dict) -> list[str]:
    out = []
    for key in ("max", "max_increase"):
        if key in base_th and (key not in th or th[key] > base_th[key]):
            out.append(f"{key} {base_th[key]} -> {th.get(key, 'removed')}")
    if "min" in base_th and ("min" not in th or th["min"] < base_th["min"]):
        out.append(f"min {base_th['min']} -> {th.get('min', 'removed')}")
    if base_th.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval set => thresholds may only get stricter."""
    problems = []
    now = {m["id"]: m for m in spec.get("metrics") or []}
    for bm in base_spec.get("metrics") or []:
        m = now.get(bm["id"])
        if m is None:
            problems.append(f"ratchet: metric {bm['id']} removed")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            problems.append(f"ratchet: metric {bm['id']} no longer blocking")
        problems += [f"ratchet: metric {bm['id']} {x}"
                     for x in _looser(m.get("threshold") or {}, bm.get("threshold") or {})]
    slices_now = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        s = slices_now.get((bs.get("name"), bs.get("metric")))
        if s is None:
            problems.append(f"ratchet: slice {bs.get('name')}/{bs.get('metric')} removed")
            continue
        if bs.get("blocking") and not s.get("blocking"):
            problems.append(f"ratchet: slice {bs.get('name')}/{bs.get('metric')} no longer blocking")
        problems += [f"ratchet: slice {bs.get('name')}/{bs.get('metric')} {x}" for x in _looser(s, bs)]
    bb, b = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    for key in ("rng", "n_resamples"):                 # re-rolling the bootstrap shops for a CI that touches 0
        if key in bb and b.get(key) != bb[key]:
            problems.append(f"ratchet: bootstrap {key} {bb[key]} -> {b.get(key)}")
    if "confidence" in bb and float(b.get("confidence", bb["confidence"])) > float(bb["confidence"]):
        problems.append(f"ratchet: bootstrap confidence {bb['confidence']} -> {b['confidence']} (wider CI)")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        val, verdict, note = None, "ok", ""
        if not a:
            verdict = "missing"                        # a slice with no items cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        rule = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(rule):<36} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
