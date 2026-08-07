"""Phase 0: check every derived constant the handoff plan states, before any of
it is implemented. Nothing here is used by the pipeline; it exists so that a
number in the brief that does not reproduce is found now rather than after a
four-hour run. ASCII only.
"""

import math

import numpy as np
from scipy import integrate, stats

OUT = []


def rep(label, got, want=None, tol=1e-4):
    if want is None:
        OUT.append(f"  {label:<58} {got!r}")
        return
    ok = abs(got - want) <= tol
    OUT.append(
        f"  {label:<58} got={got:.6f}  plan={want:.6f}  "
        f"{'OK' if ok else '*** MISMATCH ***'}"
    )


# ---------------------------------------------------------------- 2.1.2
OUT.append("\n=== 2.1.2  Kitahara class III composition ===")
CLASS3_N = np.array([6803.0, 1978.0, 627.0, 156.0])
CLASS3_SHARE = CLASS3_N / CLASS3_N.sum()
CLASS3_TAIL = np.cumsum(CLASS3_SHARE[::-1])[::-1][1:]

rep("total participants", float(CLASS3_N.sum()), 9564.0, 0)
for i, v in enumerate(CLASS3_SHARE):
    rep(f"conditional share sub-band {i+1}", float(v),
        [0.71131326, 0.20681723, 0.06555834, 0.01631117][i], 1e-8)
for i, v in enumerate(CLASS3_TAIL):
    rep(f"tail fraction F({45+5*i})", float(v),
        [0.28868674, 0.08186951, 0.01631117][i], 1e-8)

# Top-band mean BMI under the uniform-within-sub-band CDF.
mids = np.array([42.5, 47.5, 52.5, 57.5])
top_mean = float((CLASS3_SHARE * mids).sum())
rep("top-band mean BMI", top_mean, 44.4343, 1e-4)

# Deaths-weighted alternative the plan says it rejected.
DEATH_N = np.array([669.0, 245.0, 87.0, 35.0])
death_share = DEATH_N / DEATH_N.sum()
rep("top-band mean BMI, DEATHS-weighted (rejected)",
    float((death_share * mids).sum()), 45.03, 5e-3)

# Crossover at the mean effect.
MEAN_EFFECT = 0.118
crossover = 40.0 / (1.0 - MEAN_EFFECT)
rep("crossover BMI at mean effect", crossover, 45.3515, 1e-4)


def top_band_survival(b):
    """P(BMI > b | BMI >= 40) under the four uniform sub-bands."""
    b = np.asarray(b, dtype=float)
    out = np.zeros_like(b)
    edges = np.array([40.0, 45.0, 50.0, 55.0, 60.0])
    for j in range(4):
        lo, hi = edges[j], edges[j + 1]
        # mass of sub-band j lying above b
        frac = np.clip((hi - np.clip(b, lo, hi)) / (hi - lo), 0.0, 1.0)
        out += CLASS3_SHARE[j] * frac
    out[b < 40.0] = 1.0
    return out


rep("fraction of top band above the point crossover",
    float(top_band_survival(crossover)), 0.2741, 1e-4)

# Integrating over the effect distribution: an individual at baseline b stays
# >= 40 iff b*(1-e) >= 40, i.e. b >= 40/(1-e). Effect e ~ N(0.118, 0.06).
EFFECT_SD = 0.06


def stay_above_40(e):
    thr = 40.0 / (1.0 - e)
    return top_band_survival(np.array([thr]))[0] * stats.norm.pdf(
        e, MEAN_EFFECT, EFFECT_SD
    )


val, err = integrate.quad(stay_above_40, -0.5, 0.9, limit=400)
rep("P(new_bmi >= 40 | top-band adherer), integrated", float(val), 0.3645, 1e-4)
OUT.append(f"    (quad abs error {err:.2e})")

# ---------------------------------------------------------------- 2.15
OUT.append("\n=== 2.15.4 / 2.15.5  hazard ladder above 40 ===")
HR_PER_5 = 1.40
seg_const = (HR_PER_5 - 1.0) / math.log(HR_PER_5)
rep("(1.4-1)/ln(1.4)", seg_const, 1.188805, 1e-6)

seg_means = np.array([seg_const * HR_PER_5 ** j for j in range(4)])
for i, v in enumerate(seg_means):
    rep(f"segment mean sub-band {i+1}", float(v),
        [1.188805, 1.664328, 2.330059, 3.262082][i], 1e-5)

contrib = seg_means * CLASS3_SHARE
for i, v in enumerate(contrib):
    rep(f"contribution sub-band {i+1}", float(v),
        [0.845613, 0.344212, 0.152755, 0.053208][i], 1e-5)

K = float(contrib.sum())
rep("K", K, 1.395788, 1e-6)

HR_TOP_BASE = 2.76
HR_TOP_ANCHOR = HR_TOP_BASE / K
rep("HR_TOP_ANCHOR", HR_TOP_ANCHOR, 1.977378, 1e-6)


def hr_top(b):
    return HR_TOP_ANCHOR * HR_PER_5 ** ((np.minimum(b, 60.0) - 40.0) / 5.0)


OUT.append("  ladder table:")
for b, want in [(40, 1.9774), (45, 2.7683), (50, 3.8757),
                (55, 5.4259), (60, 7.5963)]:
    rep(f"    hr_top({b})", float(hr_top(b)), want, 1e-4)

rep("40-boundary discontinuity, new", HR_TOP_ANCHOR - 1.94, 0.0374, 1e-4)
rep("40-boundary discontinuity, old", 2.76 - 1.94, 0.82, 1e-9)

# 40-45 sub-band mean baseline hazard under the new ladder.
rep("mean hr_top over 40-45", float(HR_TOP_ANCHOR * seg_const), 2.3507, 1e-4)

# G9 assertion 2: integrate hr_top against the ELEVEN-KNOT CDF, not the closed
# form. Build the knot vector for a stratum with p40 = 1 (top band only) and
# check the composition-weighted mean returns 2.76.
OUT.append("\n=== G9 assertion 2 rehearsal: knot-vector integration ===")
p40 = 1.0
x_knots = np.array([40.0, 45.0, 50.0, 55.0, 60.0])
cdf_knots = np.array([1.0 - p40,
                      1.0 - p40 * CLASS3_TAIL[0],
                      1.0 - p40 * CLASS3_TAIL[1],
                      1.0 - p40 * CLASS3_TAIL[2],
                      1.0])
# Invert the piecewise-linear CDF on a fine u-grid and average hr_top.
u = (np.arange(2_000_000) + 0.5) / 2_000_000
b = np.interp(u, cdf_knots, x_knots)
rep("mean hr_top over knot-vector sample", float(hr_top(b).mean()), 2.76, 1e-4)
rep("mean BMI over knot-vector sample", float(b.mean()), 44.4343, 1e-3)

# ---------------------------------------------------------------- 2.3
OUT.append("\n=== 2.3  Sorkin height loss ===")
COEF = {
    "Men": (0.0435, -0.00009, -0.000015),
    "Women": (0.0714, -0.00075, -0.000016),
}
START, CAP = 30, 90


def height_loss_cm(age, sex):
    k1, k2, k3 = COEF[sex]
    cum = lambda A: k1 * A + k2 * A ** 2 + k3 * A ** 3
    a = np.clip(age, START, CAP)
    return np.maximum(0.0, cum(START) - cum(a))


G3B = [("Men", 50, 0.744), ("Men", 70, 3.360), ("Men", 80, 5.595),
       ("Women", 50, 1.340), ("Women", 70, 5.200), ("Women", 80, 8.315)]
for sex, age, want in G3B:
    rep(f"height_loss_cm({age}, {sex})",
        float(height_loss_cm(np.array([age]), sex)[0]), want, 1e-3)

# The plan's claim that pmax(0,...) never binds: derivative sign.
for sex in ("Men", "Women"):
    k1, k2, k3 = COEF[sex]
    # d/dA of cum = k1 + 2 k2 A + 3 k3 A^2 ; root where it turns negative
    roots = np.roots([3 * k3, 2 * k2, k1])
    pos = sorted(r.real for r in roots if abs(r.imag) < 1e-12 and r.real > 0)
    rep(f"cubic derivative turns negative at, {sex}",
        float(pos[0]) if pos else float("nan"),
        {"Men": 29.2, "Women": 26.0}[sex], 0.1)

# Exact re-integrated coefficients the plan tabulates, for the record.
EXACT = {
    "Men": (0.043478, -0.000093660, -0.000014633),
    "Women": (0.071357, -0.000753400, -0.000015867),
}
OUT.append("  printed-vs-exact inflation of modelled loss:")
for sex in ("Men", "Women"):
    for age in (50, 70, 80):
        k1, k2, k3 = COEF[sex]
        e1, e2, e3 = EXACT[sex]
        cp = lambda A, a=k1, b=k2, c=k3: a * A + b * A ** 2 + c * A ** 3
        ce = lambda A, a=e1, b=e2, c=e3: a * A + b * A ** 2 + c * A ** 3
        lp = cp(30) - cp(age)
        le = ce(30) - ce(age)
        OUT.append(
            f"    {sex:<6} age {age}: printed={lp:.4f} exact={le:.4f} "
            f"delta={lp-le:+.4f} cm ({100*(lp/le-1):+.2f}%)"
        )

OUT.append("  Sorkin abstract sanity note (reported, not gated):")
for sex, age, abstract in [("Men", 70, 3.0), ("Men", 80, 5.0),
                           ("Women", 70, 5.0), ("Women", 80, 8.0)]:
    got = float(height_loss_cm(np.array([age]), sex)[0])
    OUT.append(
        f"    {sex:<6} age {age}: model={got:.3f} abstract~{abstract:.0f} "
        f"delta={got-abstract:+.3f} cm"
    )

# ---------------------------------------------------------------- 2.1 knots
OUT.append("\n=== 2.1.2  full knot vector, worked example ===")
LOWER_BOUND = 13.0  # existing grid: seq(13, 60, by = 0.1)
shares = np.array([0.028518, 0.049085, 0.330858, 0.322533,
                   0.164165, 0.066128, 0.038713])  # global pop-wtd, from the
shares = shares / shares.sum()                      # bmi_mixture report
cum6 = np.cumsum(shares)[:6]
p40 = shares[6]
x = np.array([LOWER_BOUND, 18.5, 20, 25, 30, 35, 40, 45, 50, 55, 60])
cdf = np.concatenate([[0.0], cum6,
                      [1 - p40 * CLASS3_TAIL[0],
                       1 - p40 * CLASS3_TAIL[1],
                       1 - p40 * CLASS3_TAIL[2],
                       1.0]])
OUT.append(f"  LOWER_BOUND from existing grid seq(13, 60, by=0.1): {LOWER_BOUND}")
OUT.append("  knots:")
for xi, ci in zip(x, cdf):
    OUT.append(f"    x={xi:6.2f}  F={ci:.10f}")
OUT.append(f"  strictly increasing: {bool(np.all(np.diff(cdf) > 0))}")
OUT.append(
    "  NOTE the >=40 knots collapse to ties when p40 -> 0; that is what the "
    "extra guard line in 2.1.1 is for."
)

# Interior threshold claims.
OUT.append("\n=== 2.1.1  interior thresholds under a linear CDF ===")
rep("share of the 25-30 band above 27", (30 - 27) / (30 - 25), 0.60, 1e-12)
rep("share of the 25-30 band above 27.5", (30 - 27.5) / (30 - 25), 0.50, 1e-12)

print("\n".join(OUT))
print("\ndone")
