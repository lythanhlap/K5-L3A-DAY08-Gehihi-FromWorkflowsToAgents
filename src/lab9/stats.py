"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import comb
from numbers import Integral

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class
NEG = "PASS"


def _labels(values: Sequence[str], who: str) -> list[str]:
    """Normalise PASS/FAIL labels; anything else is a data error, not a silent PASS."""
    out = []
    for v in values:
        label = str(v).strip().upper()
        if label not in (POS, NEG):
            raise ValueError(f"{who} label {v!r} is neither PASS nor FAIL")
        out.append(label)
    return out


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    h, j = _labels(human, "human"), _labels(judge, "judge")
    if len(h) != len(j):
        raise ValueError(f"{len(h)} human labels but {len(j)} judge labels")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for hv, jv in zip(h, j):
        if jv == POS:
            cm["tp" if hv == POS else "fp"] += 1
        else:
            cm["fn" if hv == POS else "tn"] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    """precision = tp/(tp+fp), recall = tp/(tp+fn); 0.0 when the denominator is 0."""
    cm = confusion(human, judge)
    flagged, actual = cm["tp"] + cm["fp"], cm["tp"] + cm["fn"]
    return (cm["tp"] / flagged if flagged else 0.0, cm["tp"] / actual if actual else 0.0)


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = sum(cm.values())
    if n == 0:
        raise ValueError("kappa undefined: no labels")
    # Chance agreement from the two raters' marginals, kept in integers so p_e == 1 is exact.
    pe_num = ((cm["tp"] + cm["fn"]) * (cm["tp"] + cm["fp"])
              + (cm["tn"] + cm["fp"]) * (cm["tn"] + cm["fn"]))
    if pe_num == n * n:
        raise ValueError("kappa undefined: both raters gave every item the same label (p_e == 1)")
    p_o = (cm["tp"] + cm["tn"]) / n
    p_e = pe_num / (n * n)
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1].
    Undefined (ValueError) when sensitivity + specificity <= 1: such a judge is no better than chance."""
    youden = sensitivity + specificity - 1
    if youden <= 0:
        raise ValueError(f"Rogan-Gladen undefined: sensitivity + specificity - 1 = {youden:.3f} <= 0")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / youden))


def _mean_diff(x, y, axis=-1):
    return x.mean(axis=axis) - y.mean(axis=axis)


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np                     # lazy: Lab 8 CI imports lab9 without numpy/scipy
    from scipy import stats as sps

    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.ndim != 1 or x.shape != y.shape:
        raise ValueError(f"paired samples must be 1-D and aligned, got {x.shape} vs {y.shape}")
    if x.size == 0 or np.array_equal(x, y):   # no items, or no difference anywhere
        return (0.0, 0.0, 0.0)
    d = float(x.mean() - y.mean())
    if x.size == 1:                        # every resample is that one item
        return (d, d, d)
    res = sps.bootstrap((x, y), _mean_diff, paired=True, vectorized=True, n_resamples=n_resamples,
                        confidence_level=confidence, method="percentile",
                        rng=np.random.default_rng(rng))
    return (d, float(res.confidence_interval.low), float(res.confidence_interval.high))


def _check_nck(n: int, c: int, k: int) -> None:
    for name, v in (("n", n), ("c", c), ("k", k)):
        if isinstance(v, bool) or not isinstance(v, Integral):
            raise ValueError(f"{name} must be an integer, got {v!r}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got n={n}")
    if not 0 <= c <= n:
        raise ValueError(f"need 0 <= c <= n, got c={c}, n={n}")
    if not 1 <= k <= n:
        raise ValueError(f"need 1 <= k <= n, got k={k}, n={n}")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n
    (and for any other impossible triple: c outside [0, n], k < 1, n < 1, non-integers)."""
    _check_nck(n, c, k)
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    return comb(c, k) / comb(n, k)
