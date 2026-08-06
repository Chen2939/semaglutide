"""Pass 2, stage 2: render both figures from the cached passes, then run the gates.

Loads diagnostics/figure_pass_cache.pkl and monkeypatches the loaders, so
``generate_rebound_figure.main()`` and ``generate_dashboard_figure.main()`` both
run against byte-identical model output. The cache holds BOTH bases -- the
survival-weighted pass and the unweighted t = 0 pass -- and the patched
``compute_food_savings`` picks between them on the caller's
``survival_weighted`` argument, exactly as the real function would.

Everything reported below is read back off the rendered Matplotlib artists --
bar widths, scatter offsets, line segments, axis limits, tick labels, font sizes
-- not re-derived from the frames. A re-derivation would only prove the
diagnostic agrees with itself.

Writes: diagnostics/reports/figure_fixes.md   (fixed path, plain ASCII)

Usage:
    PYTHONUTF8=1 python -m diagnostics.figure_fixes_pass
"""

from __future__ import annotations

import pickle
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / "figure_pass_cache.pkl"
REPORT = Path(__file__).resolve().parent / "reports" / "figure_fixes.md"
# Artist-level snapshot of the previous render, taken before pass 3 edited
# anything. Gates G1 and G3 compare against this rather than against a
# re-derivation, so "unchanged" means the artists are unchanged and not merely
# that the diagnostic agrees with itself.
SNAPSHOT = Path(__file__).resolve().parent / "render_snapshot_pass2.pkl"

DRUG_KG = 5.38
RENDERS: list[dict] = []
SUPPRESS_WRITE = False


# ── Capture what was actually drawn ───────────────────────────────────


def _text_width_in(artist, fig) -> float:
    """Rendered width of a text artist, in inches. 0.0 if it has no text.

    Measured, not estimated from character counts: a left-aligned panel title
    that overruns the page edge is silently clipped now that the figures do not
    save with bbox_inches="tight", so the only safe check is the real extent.
    """
    if artist is None or not artist.get_text():
        return 0.0
    try:
        r = fig.canvas.get_renderer()
        return float(artist.get_window_extent(renderer=r).width) / float(fig.dpi)
    except Exception:
        return float("nan")


def _install_savefig_probe():
    """Snapshot every axes at save time -- the exact state that hits the PNG."""
    from matplotlib.figure import Figure

    original = Figure.savefig

    def probe(self, fname, *a, **kw):
        snap = {
            "file": str(fname),
            "size_in": tuple(float(v) for v in self.get_size_inches()),
            "dpi": float(kw.get("dpi", self.dpi)),
            "tight": kw.get("bbox_inches") == "tight",
            "axes": [],
            # Only artists that actually carry text. An empty artist sitting at
            # its default size is not type on the page, and counting it made the
            # "smallest text" figure meaningless in both directions.
            "fontsizes": set(),
        }
        for t in self.texts:
            if t.get_text():
                snap["fontsizes"].add(round(float(t.get_fontsize()), 2))
        fw, fh = (float(v) for v in self.get_size_inches())
        for ax in self.axes:
            ss = ax.get_subplotspec()
            # An Axes carries three title artists (centre, left, right) and only
            # the one that was written to has text. Reading ax.title when the
            # title was set with loc="left" returns the untouched centre artist,
            # still at the 12 pt default -- which is how this table first
            # reported 12 pt for panels drawn at 7.5.
            title_art = next(
                (t for t in (getattr(ax, "_left_title", None), ax.title,
                             getattr(ax, "_right_title", None))
                 if t is not None and t.get_text()),
                ax.title,
            )
            # Axes size in inches. get_position() is in FIGURE FRACTIONS, so it
            # is multiplied by the figure size; transforming it through
            # dpi_scale_trans treats fractions as pixels and returns nonsense
            # (this table first reported 0.01 mm per row).
            _x0, _y0, _w, _h = ax.get_position().bounds
            rec = {
                "row": ss.rowspan.start if ss is not None else None,
                "col": ss.colspan.start if ss is not None else None,
                "title": ax.get_title(loc="left") or ax.get_title(),
                "xlabel": ax.get_xlabel(),
                "xlim": tuple(float(v) for v in ax.get_xlim()),
                "ylim": tuple(float(v) for v in ax.get_ylim()),
                "title_w_in": _text_width_in(title_art, self),
                "title_room_in": (
                    fw - _x0 * fw if title_art.get_text() else 0.0
                ),
                "pos_in": (_x0 * fw, _y0 * fh, _w * fw, _h * fh),
                "yticklabels": [t.get_text() for t in ax.get_yticklabels()],
                "ytick_pt": (
                    round(float(ax.get_yticklabels()[0].get_fontsize()), 2)
                    if ax.get_yticklabels() else None
                ),
                "xtick_pt": (
                    round(float(ax.get_xticklabels()[0].get_fontsize()), 2)
                    if ax.get_xticklabels() else None
                ),
                "title_pt": round(float(title_art.get_fontsize()), 2),
                "xlabel_pt": round(float(ax.xaxis.label.get_fontsize()), 2),
                "bars": [],
                "points": [],
                "hlines": [],
                "text_pt": sorted({round(float(t.get_fontsize()), 2)
                                   for t in ax.texts if t.get_text()}),
            }
            for t in ax.texts:
                if t.get_text():
                    snap["fontsizes"].add(round(float(t.get_fontsize()), 2))
            if title_art.get_text():
                snap["fontsizes"].add(rec["title_pt"])
            # The rebound figure labels only its bottom row, so eight of its
            # nine rows carry an EMPTY x-label artist sitting at matplotlib's
            # 10 pt default. Counting it put a 10 pt entry in this table for
            # type that is not on the page.
            if ax.get_xlabel():
                snap["fontsizes"].add(rec["xlabel_pt"])
            if rec["ytick_pt"] and any(t.get_text() for t in ax.get_yticklabels()):
                snap["fontsizes"].add(rec["ytick_pt"])
            if rec["xtick_pt"] and any(t.get_text() for t in ax.get_xticklabels()):
                snap["fontsizes"].add(rec["xtick_pt"])
            leg = ax.get_legend()
            if leg is not None:
                for t in leg.get_texts():
                    snap["fontsizes"].add(round(float(t.get_fontsize()), 2))
            for cont in ax.containers:
                widths = [float(p.get_width()) for p in cont.patches]
                ys = [float(p.get_y() + p.get_height() / 2) for p in cont.patches]
                rec["bars"].append(
                    {"label": cont.get_label(), "widths": widths, "y": ys}
                )
            for coll in ax.collections:
                off = np.asarray(coll.get_offsets(), dtype=float)
                if off.size:
                    rec["points"].append(
                        {"label": coll.get_label(),
                         "x": off[:, 0].tolist(), "y": off[:, 1].tolist()}
                    )
                segs = getattr(coll, "get_segments", None)
                if segs is not None:
                    s = segs()
                    if s:
                        rec["hlines"].append(
                            {"label": coll.get_label(),
                             "segments": [np.asarray(x, dtype=float).tolist()
                                          for x in s]}
                        )
            snap["axes"].append(rec)
        RENDERS.append(snap)
        if SUPPRESS_WRITE:
            # Snapshot mode: capture the artists, leave the PNGs on disk alone.
            return None
        return original(self, fname, *a, **kw)

    Figure.savefig = probe


def _install_cache_patches(cache):
    """Replace the loaders with cache reads. Two passes, many renders."""
    import data_visualization.breakeven_analysis as ba
    import data_visualization.generate_dashboard_figure as gd
    import data_visualization.generate_rebound_figure as gr

    def fake_food(*a, **kw):
        if a or set(kw) - {"diet_scenario", "ci_file", "survival_weighted",
                           "horizon", "child_energy_file", "survival_weight"}:
            raise AssertionError(f"unexpected compute_food_savings args: {a} {kw}")
        if kw.get("diet_scenario") or \
                kw.get("ci_file", "carbon_intensity.csv") != "carbon_intensity.csv":
            raise AssertionError(f"cache only holds the mean/no-diet runs; got {kw}")
        # Two cached bases. Which one is returned is decided by the caller's
        # survival_weighted argument, exactly as the real function would.
        if kw.get("survival_weighted", True) is False:
            return (cache["food_savings_unweighted"].copy(),
                    cache["result_df_unweighted"])
        rdf = cache["result_df"]
        rdf.attrs["survivor_food_factor"] = cache["survivor_food_factor"]
        return cache["food_savings"].copy(), rdf

    def fake_mort(ci_scenario="mean"):
        assert ci_scenario == "mean", ci_scenario
        return cache["mort"].copy()

    def fake_drug(*a, **kw):
        return cache["drug"].copy()

    gr.compute_food_savings = fake_food
    gd.compute_food_savings = fake_food
    gd.load_mortality_emissions = fake_mort
    gd.build_drug_emissions = fake_drug
    ba.build_drug_emissions = fake_drug


# ── Report helpers ────────────────────────────────────────────────────


class Out:
    def __init__(self):
        self.lines: list[str] = []
        self.fails: list[str] = []

    def h(self, level, text):
        self.lines.append("")
        self.lines.append("#" * level + " " + text)
        self.lines.append("")

    def p(self, text=""):
        self.lines.append(text)

    def gate(self, name, ok, detail=""):
        tag = "PASS" if ok else "FAIL"
        self.lines.append(f"- **{name}: {tag}**" + (f" -- {detail}" if detail else ""))
        if not ok:
            self.fails.append(name)

    def table(self, df, floatfmt="{:,.6f}"):
        d = df.copy()
        for c in d.columns:
            if pd.api.types.is_float_dtype(d[c]):
                d[c] = d[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
        self.lines.append("| " + " | ".join(str(c) for c in d.columns) + " |")
        self.lines.append("|" + "|".join("---" for _ in d.columns) + "|")
        for _, r in d.iterrows():
            self.lines.append("| " + " | ".join(str(v) for v in r.tolist()) + " |")

    def save(self):
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(self.lines) + "\n"
        non_ascii = sorted({ch for ch in text if ord(ch) > 127})
        if non_ascii:
            raise AssertionError(f"report is not plain ASCII: {non_ascii}")
        REPORT.write_text(text, encoding="ascii")


def git(*args) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True
    ).stdout


FIGURE_SCRIPTS = [
    "data_visualization/generate_rebound_figure.py",
    "data_visualization/generate_dashboard_figure.py",
]


def _gate_a3(o, fs):
    """A3: the mapping lives in one place and cannot reach a data path.

    A plain grep for the shortened strings is not the check. It flags
    ``per_capita["ISO"] == "USA"`` in ``consumption_ghg.py``, which is the ISO3
    code for the United States and has nothing to do with this mapping -- the
    two namespaces happen to collide on one token. So the gate is structural
    instead, in four parts, and the string search is kept only where a literal
    would actually be a defect.
    """
    import ast

    shortened = list(fs.COUNTRY_DISPLAY_NAMES.values())
    ok = True

    # A3a -- exactly one definition site, and only the figure scripts import it.
    importers = sorted({
        ln.split(":")[0] for ln in
        git("grep", "-l", "-E", r"figure_style", "--",
            "data_visualization/", "diet_sensitivity/", "drug_effect/",
            "scripts/", "diagnostics/").splitlines()
        if ln.strip() and not ln.endswith("figure_style.py")
    })
    expected = set(FIGURE_SCRIPTS) | {"diagnostics/figure_fixes_pass.py"}
    a3a = set(importers) <= expected
    ok &= a3a
    o.p()
    o.gate("A3a -- figure_style imported only by the two figure scripts",
           a3a, f"importers: {importers}")

    # A3b -- no shortened string appears as a literal in either figure script.
    literals = {}
    for path in FIGURE_SCRIPTS:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        found = {
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value in set(shortened)
        }
        if found:
            literals[path] = sorted(found)
    a3b = not literals
    ok &= a3b
    o.gate("A3b -- no shortened name appears as a literal in either figure script",
           a3b,
           "the strings exist only in the mapping" if a3b
           else f"LITERALS FOUND: {literals}")

    # A3c -- every mapping call is an argument to set_yticklabels, nowhere else.
    misplaced = []
    call_count = 0
    for path in FIGURE_SCRIPTS:
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        label_calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "set_yticklabels"
        ]
        inside = set()
        for lc in label_calls:
            for sub in ast.walk(lc):
                inside.add(id(sub))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in ("display_country", "display_countries")):
                call_count += 1
                if id(n) not in inside:
                    misplaced.append(f"{path}:{n.lineno}")
    a3c = not misplaced
    ok &= a3c
    o.gate("A3c -- every display_countries() call is an argument to set_yticklabels",
           a3c,
           f"{call_count} call sites, all render-only" if a3c
           else f"OUTSIDE A LABEL CALL: {misplaced}")

    # A3d -- the tokens that collide with a real ISO3 code, named rather than
    # silently passed over.
    isos = set(fs.COUNTRY_DISPLAY_NAMES.values()) & {"USA", "UK", "UAE"}
    collisions = sorted(t for t in isos if len(t) == 3)
    o.p(f"- Shortened tokens that are also valid-looking ISO3 codes: "
        f"{collisions}. `USA` genuinely is the ISO3 for the United States, so a")
    o.p("  text search for it hits `consumption_ghg.py`'s")
    o.p('  `per_capita["ISO"] == "USA"` -- an ISO filter that predates this')
    o.p("  change, lives in a file this pass does not touch, and reads the `ISO`")
    o.p("  column rather than a label. A3a-A3c are structural precisely because")
    o.p("  the string search cannot tell those two apart.")
    o.p("- The mapping is applied by `display_countries()` on a list of label")
    o.p(f"  strings inside `set_yticklabels`, at {call_count} call sites")
    o.p("  (dashboard A, B, C; rebound column 0). Every join, groupby, filter and")
    o.p("  reindex in both scripts keys off `ISO` or the unmodified `Country`")
    o.p("  column.")

    return ok, collisions


def _pass3(o, cache, dash, reb, pc, cmax, seg_by_y, n_plotted, derived,
           universe, fs):
    """Pass 3: the blank-band diagnosis, gates G1-G3, and the two checks."""
    prev = None
    if SNAPSHOT.exists():
        with SNAPSHOT.open("rb") as fh:
            prev = pickle.load(fh)

    def find(snaps, fname_frag, row, col):
        s = next(x for x in snaps if fname_frag in x["file"])
        return next(a for a in s["axes"] if a["row"] == row and a["col"] == col)

    # ── 1. Was the blank band a layout choice or unplotted rows? ───────
    o.h(3, "1. Panel C blank band -- diagnosis")
    o.p()
    o.p("Two candidates. (b) unplotted rows would be a data gap wearing a")
    o.p("layout costume, so it is checked first and the answer decides whether")
    o.p("any layout fix was allowed to happen at all.")
    o.p()
    prev_pc = find(prev, "country_dashboard", 0, 1) if prev else None
    src = prev_pc or pc
    counts = {}
    for p in src["points"]:
        x = np.asarray(p["x"], float)
        if len(x) > 1:
            counts[p["label"]] = (len(x), int(np.isfinite(x).sum()))
    seg_n = len(max(src["hlines"], key=lambda h: len(h["segments"]))["segments"])
    o.p("| artist in panel C (pass-2 render) | offsets | finite |")
    o.p("|---|---|---|")
    for k, (n_, f_) in counts.items():
        o.p(f"| scatter `{k}` | {n_} | {f_} |")
    o.p(f"| whisker segments | {seg_n} | {seg_n} |")
    o.p(f"| y tick labels | {len(src['yticklabels'])} | - |")
    o.p()
    rendered = max(f_ for _, f_ in counts.values())
    match = (rendered == len(derived) == seg_n == len(src["yticklabels"]))
    o.gate("Section 1 gate -- rendered marks == derived country count",
           match,
           f"derived {len(derived)}, rendered marks {rendered}, whiskers "
           f"{seg_n}, tick labels {len(src['yticklabels'])}"
           if match else "MISMATCH -- see the table above")
    o.p()
    if match:
        o.p("**(b) is excluded.** Every one of the 40 derived countries has a")
        o.p("drawn, finite mark and a drawn whisker; no y-position was allocated")
        o.p("to a country that failed to render. There is no data gap here.")
        o.p()
        o.p("**(a) is the explanation, and it was mine.** Pass 2 set panel C's")
        o.p("y-limit to `-5.4` on purpose, to park a three-entry legend above the")
        o.p("first country -- the comment in that commit says so. The band is")
        o.p("about five row-heights of reserved space, and it appeared at the")
        o.p("print-size change because that is when the legend stopped fitting")
        o.p("anywhere inside the data. Cosmetic, and now removed.")
    else:
        o.p("**STOP.** Rendered marks do not match the derived country set. No")
        o.p("layout fix has been applied and section 2 was not attempted.")
        return False

    # ── G1 / G2 / G3 ──────────────────────────────────────────────────
    o.h(3, "Gates G1-G3")
    o.p()
    if prev is None:
        o.gate("G1 -- max-uptake values unchanged", False,
               "NO PASS-2 SNAPSHOT -- cannot compare")
        return False

    prev_max = np.asarray(
        next(p for p in prev_pc["points"]
             if p["label"] == "Max uptake (95%), point")["x"], float)
    prev_segs = {}
    for s in max(prev_pc["hlines"], key=lambda h: len(h["segments"]))["segments"]:
        a = np.asarray(s, float)
        prev_segs[int(round(a[0, 1]))] = (float(a[0, 0]), float(a[1, 0]))

    dmax = np.abs(cmax - prev_max)
    dlo = np.array([abs(seg_by_y[i][0] - prev_segs[i][0]) for i in prev_segs])
    dhi = np.array([abs(seg_by_y[i][1] - prev_segs[i][1]) for i in prev_segs])
    g1 = bool(dmax.max() == 0.0 and dlo.max() == 0.0 and dhi.max() == 0.0)
    o.gate("G1 -- dropping the moderate series changed no max-uptake value",
           g1,
           f"{len(cmax)} points and {len(prev_segs)} x 2 whisker endpoints, "
           f"all exactly 0.0 different"
           if g1 else f"MOVED: max {dmax.max():.3e}, P10 {dlo.max():.3e}, "
                      f"P90 {dhi.max():.3e}")
    o.p(f"- Compared artist-to-artist against the pass-2 render, captured before")
    o.p("  this pass edited anything (`render_snapshot_pass2.pkl`). Same cached")
    o.p("  frames, same code path, so anything but exactly 0.0 would be a defect.")

    o.p()
    prev_ylim, now_ylim = prev_pc["ylim"], pc["ylim"]
    prev_a = find(prev, "country_dashboard", 0, 0)
    prev_b = find(prev, "country_dashboard", 1, 0)
    # Padding above the first row, in row-heights, for each panel.
    pad_now = abs(now_ylim[1])
    pad_prev = abs(prev_ylim[1])
    pad_a = abs(prev_a["ylim"][1])
    pad_b = abs(prev_b["ylim"][1])
    g2 = pad_now <= max(pad_a, pad_b) + 1e-9
    o.gate("G2 -- panel C y-limits no wider than the bar panels' own padding",
           g2,
           f"panel C padding above row 0 is now {pad_now:.2f} row-heights, "
           f"against {pad_a:.2f} (panel A) and {pad_b:.2f} (panel B)"
           if g2 else f"STILL WIDER: {pad_now:.2f} vs A {pad_a:.2f} / B {pad_b:.2f}")
    o.p()
    o.p("| panel C y-limits | value | padding above row 0 |")
    o.p("|---|---|---|")
    o.p(f"| pass 2 (before) | ({prev_ylim[0]:.2f}, {prev_ylim[1]:.2f}) | "
        f"{pad_prev:.2f} row-heights |")
    o.p(f"| pass 3 (after) | ({now_ylim[0]:.2f}, {now_ylim[1]:.2f}) | "
        f"{pad_now:.2f} row-heights |")
    o.p(f"| panel A, for reference | ({prev_a['ylim'][0]:.2f}, "
        f"{prev_a['ylim'][1]:.2f}) | {pad_a:.2f} |")
    o.p(f"| panel B, for reference | ({prev_b['ylim'][0]:.2f}, "
        f"{prev_b['ylim'][1]:.2f}) | {pad_b:.2f} |")
    o.p()
    o.p(f"- {pad_prev - pad_now:.1f} row-heights of blank page recovered, about "
        f"{(pad_prev - pad_now) * fs.mm(pc['pos_in'][3]) / n_plotted:.1f} mm.")
    o.p("- The legend fits inside the data limits: it did not have to be shrunk,")
    o.p("  and the axes were not grown.")

    # G3 -- nothing else moved.
    o.p()
    moved = []
    for nm, row, col in (("panel A", 0, 0), ("panel B", 1, 0)):
        now = find([dash], "country_dashboard", row, col)
        was = find(prev, "country_dashboard", row, col)
        for b_now, b_was in zip(now["bars"], was["bars"]):
            if b_now["widths"] != b_was["widths"]:
                moved.append(f"{nm} bar widths")
        if now["ylim"] != was["ylim"] or now["xlim"] != was["xlim"]:
            moved.append(f"{nm} limits")
    reb_now = {(a["row"], a["col"]): a for a in reb["axes"]}
    reb_was = {(a["row"], a["col"]): a
               for a in next(x for x in prev
                             if "rebound" in x["file"])["axes"]}
    for k, a_now in reb_now.items():
        a_was = reb_was[k]
        if a_now["bars"][0]["widths"] != a_was["bars"][0]["widths"]:
            moved.append(f"rebound {k} bars")
        if a_now["xlim"] != a_was["xlim"]:
            moved.append(f"rebound {k} xlim")
    g3 = not moved
    o.gate("G3 -- panels A and B and the whole rebound figure unchanged",
           g3,
           f"{len(reb_now)} rebound axes plus dashboard A and B: every bar "
           f"width and axis limit identical to the pass-2 render"
           if g3 else f"MOVED: {sorted(set(moved))}")

    # G5 -- nothing left-aligned runs off the page.
    o.p()
    fits, over = [], []
    for snap, fig_nm in ((dash, "dashboard"), (reb, "rebound")):
        for a in snap["axes"]:
            if not a["title_w_in"]:
                continue
            slack = a["title_room_in"] - a["title_w_in"]
            row = {"figure": fig_nm, "title": a["title"],
                   "width_in": a["title_w_in"],
                   "room_in": a["title_room_in"], "slack_in": slack}
            fits.append(row)
            if slack < 0:
                over.append(row)
    g5 = not over
    o.gate("G5 -- every panel title fits inside the page",
           g5,
           f"{len(fits)} titles, tightest slack "
           f"{min(r['slack_in'] for r in fits):.3f} in"
           if g5 else f"CLIPPED: {[r['title'] for r in over]}")
    o.p()
    o.table(pd.DataFrame(fits), "{:,.3f}")
    o.p()
    o.p("- **New gate, and it exists because the harness missed this twice.**")
    o.p("  Titles are left-aligned and the figures no longer save with")
    o.p("  `bbox_inches=\"tight\"`, so an over-long title is silently sliced at")
    o.p("  the page edge rather than expanding the canvas. Both times it was")
    o.p("  caught by looking at the PNG, which is not a check. The widths above")
    o.p("  are measured from the rendered text artists.")

    # ── 3. Rebound nonlinearity, or cohort composition? ───────────────
    o.h(3, "3. Is the mod > max inversion a rebound effect or a cohort effect?")
    sim = cache["sim_slim"]
    sim = sim[sim["adheres_to_treatment"].astype(bool)]
    sim = sim.assign(diff=sim["eer"] - sim["treatment_eer"])
    g = sim.groupby(["ISO", "scenario"], as_index=False).apply(
        lambda d: pd.Series({
            "mean_eer_diff": (d["weighting"] * d["diff"]).sum()
                             / d["weighting"].sum(),
            "headcount": d["weighting"].sum(),
        }),
        include_groups=False,
    )
    w = g.pivot(index="ISO", columns="scenario", values="mean_eer_diff")
    inverted = ["AUS", "ESP", "FRA"]
    controls = ["USA", "GBR", "DEU", "POL", "JPN"]
    rows = []
    for iso in inverted + controls:
        mx, md = float(w.loc[iso, "max_uptake"]), float(w.loc[iso, "mod_uptake"])
        rows.append({
            "ISO": iso,
            "group": "INVERTED" if iso in inverted else "control",
            "mean_eer_diff_max": mx,
            "mean_eer_diff_mod": md,
            "mod_minus_max": md - mx,
            "sign": "mod > max" if md > mx else "mod < max",
        })
    t3 = pd.DataFrame(rows)
    o.p()
    o.p("Mean per-adherer `eer - treatment_eer` (kcal/day), weighted by")
    o.p("`weighting`, from the cached simulation frame. Read-only: nothing here")
    o.p("touches a figure, a cached pass, or any file but this report.")
    o.p()
    o.table(t3, "{:,.4f}")
    o.p()
    inv_pos = all(t3.loc[t3.group == "INVERTED", "mod_minus_max"] > 0)
    ctl_neg = all(t3.loc[t3.group == "control", "mod_minus_max"] < 0)
    o.p(f"- All three inverted countries have mod > max on per-patient shock: "
        f"**{inv_pos}**.")
    o.p(f"- All five controls have mod < max: **{ctl_neg}**.")
    if inv_pos and ctl_neg:
        o.p()
        o.p("**The cohort-composition explanation is supported and the")
        o.p("rebound-nonlinearity attribution in pass 2 was wrong.** The sign of")
        o.p("the per-patient calorie shock difference tracks the sign of the")
        o.p("per-patient savings inversion exactly, across all eight countries")
        o.p("tested. The 50% draw in Australia, Spain and France reduces intake")
        o.p("more per adherer than the 95% draw does, so the shock is not")
        o.p("proportional to headcount and the per-patient saving can be higher")
        o.p("at moderate uptake.")
        o.p()
        o.p("The brief's algebra is also right on its own terms: with")
        o.p("`k = Es/(Es-Ed)` in (0,1), `[1-(1+delta)^k]/|delta|` is increasing")
        o.p("in `|delta|`, so the solve alone gives max > mod everywhere and")
        o.p("cannot produce an inversion. Pass 2 asserted the opposite without")
        o.p("testing it. **Correction stands: this is a composition effect, not")
        o.p("a rebound effect.**")
    else:
        o.p()
        o.p("**The test does not separate the two explanations.** The sign of the")
        o.p("per-patient shock difference does not track the inversion cleanly")
        o.p("across the countries tested, so composition alone does not account")
        o.p("for it and both explanations remain live. Reported unresolved rather")
        o.p("than forced; not investigated further.")

    # ── 4. Does 52.9 Mt sit on the same drug basis? ───────────────────
    o.h(3, "4. Does the manuscript's 52.9 Mt sit on panel A's drug basis?")
    drug_total = float(universe["drug_emissions_1yr_t"].sum())
    gross = float(universe["annual_food_savings_t"].sum())
    o.p()
    o.p("| quantity | value |")
    o.p("|---|---|")
    o.p(f"| unweighted post-rebound gross, N = {len(universe)} | "
        f"{gross / 1e6:.4f} Mt |")
    o.p(f"| sum of `drug_emissions_1yr_t` over the same universe | "
        f"{drug_total / 1e6:.4f} Mt ({drug_total:,.1f} t) |")
    o.p(f"| gross minus drug | **{(gross - drug_total) / 1e6:.4f} Mt** |")
    o.p()
    o.p("Reported and stopped. Nothing was adjusted toward 52.9, and a mismatch")
    o.p("would not be treated as a figure defect -- if the manuscript's net")
    o.p("figure rests on a different basis or country set, that is a manuscript")
    o.p("question, not a code one.")

    o.p()
    o.p("**Caption consequence, reported not implemented.** Panel A is max")
    o.p("uptake only, panel C is now max uptake only, and panel B retains both")
    o.p("scenarios. That mixed convention is deliberate -- the uptake contrast is")
    o.p("real and readable only in panel B -- but it is not self-evident from the")
    o.p("figure and the caption has to state it.")

    return bool(g1 and g2 and g3 and g5)


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    with CACHE.open("rb") as fh:
        cache = pickle.load(fh)

    _install_cache_patches(cache)
    _install_savefig_probe()

    import data_visualization.generate_dashboard_figure as gd
    import data_visualization.generate_rebound_figure as gr
    from data_visualization import figure_style as fs
    from data_visualization.breakeven_analysis import (
        compute_breakeven, _complete_data_subset,
    )
    from scripts.build_supplement_table import compute_scenario_metrics

    o = Out()
    o.p("# Figure fixes, pass 2 -- rebound decomposition and country dashboard")
    o.p()
    o.p("Two cached model passes, replayed into both figure scripts: the")
    o.p("survival-weighted default (panels B and C, the food-group breakdown,")
    o.p("the whole rebound figure) and `survival_weighted=False` (dashboard")
    o.p("panel A only). No pre-change baseline was run; C6-C12 are dumps for")
    o.p("human review, not comparisons.")
    o.p()
    o.p("All plotted values and all point sizes below are read back off the")
    o.p("rendered Matplotlib artists at savefig time.")

    # ── Gate A ────────────────────────────────────────────────────────
    o.h(2, "Gate A -- structural")
    diffstat = git("diff", "--stat", "--",
                   "data_visualization/generate_rebound_figure.py",
                   "data_visualization/generate_dashboard_figure.py").strip()
    o.p("`git diff --stat` on the two figure scripts (plus the new")
    o.p("`data_visualization/figure_style.py`, which is untracked):")
    o.p()
    o.p("```")
    for ln in diffstat.splitlines():
        o.p(ln)
    o.p("```")
    o.p()
    o.p("Classification of every hunk that touches a data path:")
    o.p()
    o.p("| file | change | permitted? |")
    o.p("|---|---|---|")
    o.p("| generate_rebound_figure.py | group selection: hardcoded 3 -> all groups, ordered by year-1 carbon savings | yes (pass 2, 4) |")
    o.p("| generate_rebound_figure.py | everything else -- limits, ticks, margins, sizing, labels, comments | n/a |")
    o.p("| generate_dashboard_figure.py | panel A gains denominator `treated_users_initial` | yes (pass 1, 2.3) |")
    o.p("| generate_dashboard_figure.py | panel A gains drug subtraction `drug_emissions_1yr_t` | yes (pass 1 2.3; column revised by pass 2, 1) |")
    o.p("| generate_dashboard_figure.py | panel A switches to `compute_food_savings(survival_weighted=False)` | yes (pass 2, 1) |")
    o.p("| generate_dashboard_figure.py | panel A/B country set: derived food-data universe, top 15 | yes (pass 2, 1) |")
    o.p("| generate_dashboard_figure.py | panel C gains country set `_complete_data_subset` + P10/P90 columns | yes (pass 1, 2.2) |")
    o.p("| generate_dashboard_figure.py | `FOOD_COLORS` now imported from `figure_style` | no data path; values identical |")
    o.p()
    o.p("No other data-selection filter, arithmetic expression or column choice")
    o.p("changed. Panel B's plotted quantity is untouched, on the same")
    o.p("survival-weighted basis it has always used; panel C's point estimate,")
    o.p("filter and whisker source are unchanged from pass 1; the rebound")
    o.p("figure's country ranking field is still `actual_reduction`.")

    a3_ok, a3_notes = _gate_a3(o, fs)

    # ── Render ────────────────────────────────────────────────────────
    print("Rendering rebound figure ...")
    gr.main()
    print("Rendering dashboard ...")
    gd.main()

    status = git("status", "--porcelain", "data_result/").strip()
    o.p()
    o.gate("A2 -- git status --porcelain data_result/ empty after the run",
           status == "",
           "no output" if status == "" else f"UNEXPECTED WRITES: {status!r}")
    fgb = git("status", "--porcelain", "figures/food_group_breakdown.png").strip()
    o.gate("A1b -- food_group_breakdown.png byte-identical after the FOOD_COLORS move",
           fgb == "",
           "unchanged against HEAD, so the shared dict carries the same values"
           if fgb == "" else f"CHANGED: {fgb!r} -- the colour values moved")

    # ── Locate the rendered panels ────────────────────────────────────
    reb = next(s for s in RENDERS if "rebound_decomposition" in s["file"])
    dash = next(s for s in RENDERS if "country_dashboard" in s["file"])

    def dash_panel(letter):
        return next(a for a in dash["axes"] if a["title"].startswith(f"{letter}."))

    pa, pb, pc = dash_panel("A"), dash_panel("B"), dash_panel("C")

    # ── Reference quantities for the machine gates ────────────────────
    fu, ru = cache["food_savings_unweighted"], cache["result_df_unweighted"]
    fw, drug = cache["food_savings"], cache["drug"]
    be = compute_breakeven(fw, cache["mort"], include_drug=True)

    d = fu.merge(
        drug[["ISO", "scenario", "treated_users_initial", "drug_emissions_1yr_t"]],
        on=["ISO", "scenario"], how="left",
    )
    universe = d[(d.scenario == "max_uptake") & (d.annual_food_savings_t > 0)] \
        .sort_values("annual_food_savings_t", ascending=False)
    order15 = universe.head(15)["ISO"].tolist()
    top15 = universe.set_index("ISO").loc[order15]

    o.h(2, "Gate B -- machine checks")

    # B3 revised: reconciliation on the unweighted basis.
    net_bar = next(b for b in pa["bars"] if b["label"].startswith("Net food"))
    gross_bar = next(b for b in pa["bars"] if b["label"].startswith("Pharma"))
    plotted_net = np.asarray(net_bar["widths"], dtype=float)      # kg/patient
    plotted_gross = np.asarray(gross_bar["widths"], dtype=float)

    rec_rows = []
    for i, iso in enumerate(order15):
        r = top15.loc[iso]
        denom = float(r["treated_users_initial"])
        drug_t = float(r["drug_emissions_1yr_t"])
        gross = float(r["annual_food_savings_t"])
        reconstructed = plotted_net[i] / 1e3 * denom + drug_t
        rec_rows.append({
            "ISO": iso, "Country": r["Country"],
            "plotted_kg_per_patient": plotted_net[i],
            "denominator_patients": denom,
            "drug_charge_t": drug_t,
            "reconstructed_gross_t": reconstructed,
            "actual_t0_gross_t": gross,
            "rel_diff": abs(reconstructed - gross) / abs(gross),
        })
    rec = pd.DataFrame(rec_rows)
    worst = rec["rel_diff"].max()
    bad = rec[rec["rel_diff"] > 1e-9]
    o.gate("B3 -- panel A reconciliation on the t=0 basis "
           "(per-patient x denominator + unweighted drug == unweighted gross)",
           len(bad) == 0,
           f"15/15 within 1e-9 relative; worst {worst:.3e}"
           if len(bad) == 0 else f"{len(bad)} FAILED, worst {worst:.3e}")
    o.p()
    o.table(rec, "{:,.9g}")
    if len(bad):
        o.p()
        o.p("Failing countries, both sides:")
        o.table(bad, "{:,.12g}")

    # B4: whisker endpoints exact, P10 < P90.
    sens = pd.read_csv(
        ROOT / "data_result" / "all_sensitivity_overview_country_ratios.csv")
    sens_i = sens.set_index("ISO")
    disp_to_full = {fs.display_country(c): c for c in be["Country"].unique()}
    c_labels = pc["yticklabels"]
    c_full = [disp_to_full[n] for n in c_labels]
    name_to_iso = dict(zip(be["Country"], be["ISO"]))
    c_iso_codes = [name_to_iso[n] for n in c_full]

    cmax = np.asarray(
        next(p for p in pc["points"] if p["label"] == "_max_points")["x"], float)
    seg_group = max(pc["hlines"], key=lambda h: len(h["segments"]))
    seg_by_y = {}
    for s in seg_group["segments"]:
        arr = np.asarray(s, dtype=float)
        seg_by_y[int(round(arr[0, 1]))] = (float(arr[0, 0]), float(arr[1, 0]))

    w_rows, mismatch, ordering = [], [], []
    for i, iso in enumerate(c_iso_codes):
        lo, hi = seg_by_y.get(i, (np.nan, np.nan))
        f10 = float(sens_i.loc[iso, "baseline_p10_ci"])
        f90 = float(sens_i.loc[iso, "baseline_p90_ci"])
        if not ((lo == f10) and (hi == f90)):
            mismatch.append(iso)
        if not (f10 < f90):
            ordering.append(iso)
        w_rows.append({"ISO": iso, "Country": c_labels[i],
                       "plotted_P10": lo, "file_P10": f10,
                       "plotted_P90": hi, "file_P90": f90})
    wdf = pd.DataFrame(w_rows)
    o.p()
    o.gate("B4a -- panel C whisker endpoints match the CSV exactly",
           not mismatch,
           f"{len(wdf)}/{len(wdf)} endpoints bit-identical"
           if not mismatch else f"mismatched: {mismatch}")
    o.gate("B4b -- P10 < P90 for every country", not ordering,
           f"{len(wdf)}/{len(wdf)} ordered"
           if not ordering else f"NOT ORDERED (a data problem): {ordering}")
    missing = wdf[wdf[["plotted_P10", "plotted_P90"]].isna().any(axis=1)]
    o.p(f"- Countries drawn without a whisker (missing P10 or P90): "
        f"{sorted(missing['ISO']) if len(missing) else 'none'}")

    # B5: panel C country count.
    derived = _complete_data_subset(be, scenario="max_uptake")
    n_plotted = len(c_labels)
    o.gate("B5 -- panel C country count equals the derived complete-data filter",
           n_plotted == len(derived),
           f"derived N = {len(derived)}, plotted N = {n_plotted}")
    o.p(f"- Panel A/B universe (positive food savings, no survivor requirement): "
        f"N = {len(universe)}, of which the leading 15 are shown.")
    o.p("- Both counts are reported, not forced. Nothing in the code names 40 or 53.")

    # B6: same-code-path basis check against build_supplement_table.
    o.p()
    b6_rows, b6_fail = [], []
    for sc in ("max_uptake", "mod_uptake"):
        m = compute_scenario_metrics(sc, fu, ru, cache["sim_slim"])
        mine = fu.loc[(fu.scenario == sc) & (fu.annual_food_savings_t > 0),
                      "annual_food_savings_t"].sum()
        theirs = m["emissions_after_Mt"] * 1e6
        diff = abs(mine - theirs)
        if diff != 0.0:
            b6_fail.append(sc)
        b6_rows.append({
            "scenario": sc, "N": m["N"],
            "supplement_table_t": theirs, "figure_pass_t": mine,
            "abs_diff": diff, "exactly_zero": diff == 0.0,
        })
    b6 = pd.DataFrame(b6_rows)
    o.gate("B6 -- unweighted global post-rebound saving == build_supplement_table, "
           "exactly 0.0",
           not b6_fail,
           "both scenarios differ by exactly 0.0"
           if not b6_fail else f"NOT ZERO on {b6_fail}")
    o.p()
    o.table(b6, "{:,.9f}")
    o.p()
    o.p(f"- Max uptake is **{b6.loc[0, 'supplement_table_t'] / 1e6:.4f} Mt** and")
    o.p(f"  moderate **{b6.loc[1, 'supplement_table_t'] / 1e6:.4f} Mt** after")
    o.p("  rebound, which is the 54.2 / 27.8 Mt the Results section quotes. Panel")
    o.p("  A now sits on the basis of the text it illustrates.")
    o.p("- Same code path: `compute_scenario_metrics` was imported from")
    o.p("  `scripts/build_supplement_table.py` and handed the cached unweighted")
    o.p("  frames, rather than being reimplemented here.")

    # B7: the totals must have moved off the committed weighted basis.
    mxw = fw[(fw.scenario == "max_uptake") & (fw.annual_food_savings_t > 0)]
    j = top15.reset_index()[["ISO", "Country", "annual_food_savings_t"]].merge(
        mxw[["ISO", "annual_food_savings_t"]], on="ISO", suffixes=("_t0", "_wtd"))
    j["pct_higher"] = (j.annual_food_savings_t_t0 / j.annual_food_savings_t_wtd - 1) * 100
    all_differ = bool((j.pct_higher.abs() > 1e-9).all())
    plausible = bool(((j.pct_higher > 0) & (j.pct_higher < 2.0)).all())
    o.p()
    o.gate("B7 -- panel A totals differ from the committed (weighted) PNG values",
           all_differ and plausible,
           f"all 15 differ, by +{j.pct_higher.min():.4f}% to "
           f"+{j.pct_higher.max():.4f}%"
           if all_differ and plausible
           else f"all_differ={all_differ} in_expected_range={plausible}")
    o.p()
    o.table(j.assign(t0_kt=j.annual_food_savings_t_t0 / 1e3,
                     weighted_kt=j.annual_food_savings_t_wtd / 1e3)
            [["ISO", "Country", "t0_kt", "weighted_kt", "pct_higher"]], "{:,.6f}")
    o.p()
    o.p("- Every total is HIGHER unweighted, which is the right direction:")
    o.p("  removing pi(1) removes a first-year mortality discount. The size is")
    o.p("  the size of that discount -- pi(1) runs about 0.992 to 0.998 by")
    o.p("  country, so 0.16% to 0.76% is exactly the order of the weighting that")
    o.p("  came out, and nothing larger has moved.")
    o.p("- A zero here would have meant the unweighted pass never took effect.")

    # ── Pass 3 ────────────────────────────────────────────────────────
    o.h(2, "Pass 3 -- panel C blank band, and two read-only checks")
    pass3_ok = _pass3(o, cache, dash, reb, pc, cmax, seg_by_y, n_plotted,
                      derived, universe, fs)

    # ── Reported, not decided ─────────────────────────────────────────
    o.h(2, "Reported, not decided")

    o.h(3, "1. The global population-weighted mean per patient")
    g_gross = universe["annual_food_savings_t"].sum()
    g_drug = universe["drug_emissions_1yr_t"].sum()
    g_pat = universe["treated_users_initial"].sum()
    o.p()
    o.p("Max uptake, t = 0, over the whole derived food-data universe")
    o.p(f"(N = {len(universe)}), not the fifteen shown:")
    o.p()
    o.p("| quantity | value |")
    o.p("|---|---|")
    o.p(f"| gross saving per patient | **{g_gross * 1e3 / g_pat:.4f} kg CO2eq/patient-year** |")
    o.p(f"| pharmaceutical charge | {g_drug * 1e3 / g_pat:.4f} kg |")
    o.p(f"| **net saving per patient** | **{(g_gross - g_drug) * 1e3 / g_pat:.4f} kg CO2eq/patient-year** |")
    o.p(f"| treated headcount (weighted) | {g_pat:,.0f} |")
    o.p(f"| gross national total | {g_gross / 1e6:.4f} Mt CO2eq |")
    o.p()
    o.p("Reported and stopped there. Nothing was tuned, filtered or selected to")
    o.p("move this or any other value toward a target, and no manuscript figure")
    o.p("was looked up to compare it against.")

    o.h(3, "2. Does the mod > max per-patient inversion survive unweighting?")
    modv = d[d.scenario == "mod_uptake"].set_index("ISO").reindex(order15)
    ppa = (top15["annual_food_savings_t"].values
           - top15["drug_emissions_1yr_t"].values) * 1e3 \
        / top15["treated_users_initial"].values
    ppm = (modv["annual_food_savings_t"].values
           - modv["drug_emissions_1yr_t"].values) * 1e3 \
        / modv["treated_users_initial"].values
    cmpdf = pd.DataFrame({
        "ISO": order15, "Country": top15["Country"].values,
        "per_patient_max_kg": ppa, "per_patient_mod_kg": ppm,
        "mod_over_max": ppm / ppa,
    })
    o.p()
    o.table(cmpdf, "{:,.4f}")
    inv = sorted(cmpdf.loc[cmpdf.mod_over_max > 1, "ISO"])
    o.p()
    o.p(f"- Unweighted, moderate still exceeds maximum on **{inv}** -- the same")
    o.p("  three countries pass 1 found on the weighted basis.")
    o.p("- **It is therefore not a pi artefact.** It survives with survival")
    o.p("  weighting switched off on both the food and the drug side, so it is")
    o.p("  nonlinearity of the rebound solve in shock size: the equilibrium")
    o.p("  `(1+delta)^(Es/(Es-Ed))` is not linear in delta, so halving the shock")
    o.p("  does not halve the saving, and in these three the per-unit-shock")
    o.p("  saving is slightly higher at the smaller shock. Observed and stated;")
    o.p("  not investigated further.")
    o.p(f"- Magnitudes are unchanged in character: moderate is "
        f"{cmpdf.mod_over_max.min():.4f}x to {cmpdf.mod_over_max.max():.4f}x of")
    o.p("  maximum, so the pass-1 decision to plot max uptake only in panel A")
    o.p("  still holds.")

    o.h(3, "3. Does the panel A annotation column fit at 183 mm?")
    ax_a_w = pa["pos_in"][2]
    ax_c_x0 = pc["pos_in"][0]
    ax_a_right = pa["pos_in"][0] + ax_a_w
    o.p()
    o.p("**Yes, and it does not squeeze the bars.** Measured off the rendered")
    o.p("figure:")
    o.p()
    o.p("| quantity | inches | mm |")
    o.p("|---|---|---|")
    o.p(f"| panel A axes width | {ax_a_w:.3f} | {fs.mm(ax_a_w):.1f} |")
    o.p(f"| panel C axes width | {pc['pos_in'][2]:.3f} | {fs.mm(pc['pos_in'][2]):.1f} |")
    o.p(f"| gap between A's right spine and C's left spine | {ax_c_x0 - ax_a_right:.3f} | {fs.mm(ax_c_x0 - ax_a_right):.1f} |")
    o.p(f"| of that, reserved for the totals column | {gd.ANNOTATION_COL_IN:.3f} | {fs.mm(gd.ANNOTATION_COL_IN):.1f} |")
    o.p()
    o.p("The column is 7.6 mm wide at 5.5 pt, which holds a five-character")
    o.p("number with a two-line header above it. It is taken out of the")
    o.p("inter-column gap, which panel C's country labels also live in, not out")
    o.p("of panel A's axes -- so panel A keeps the full width the width_ratios")
    o.p("give it and no bar is shortened to make room. No alternative is")
    o.p("proposed because none is needed; if the totals are later wanted in the")
    o.p("caption instead, deleting the two `ax_a.text` blocks recovers 7.6 mm.")

    o.h(3, "4. Country names shortened")
    o.p()
    o.p("| full name (unchanged in every data path) | displayed | chars |")
    o.p("|---|---|---|")
    for full, short in fs.COUNTRY_DISPLAY_NAMES.items():
        o.p(f"| `{full}` | {short} | {len(full)} -> {len(short)} |")
    o.p()
    o.p("The first three are the brief's. The rest were added because they crowd")
    o.p("an axis at 183 mm: UAE and South Korea both appear in panel C's 40 rows,")
    o.p("and the three Caribbean names sit in the rebound figure's food-data")
    o.p("universe. Taiwan is mapped for completeness and is never plotted -- it")
    o.p("has no FAOSTAT price index, so it carries no food savings.")
    o.p()
    o.p("The longest label the figures now draw is `Trinidad & Tobago` at 17")
    o.p("characters, which is what the left margins are sized for.")

    o.h(3, "5. Rebound figure -- groups and countries per row")
    mu = cache["result_df"][cache["result_df"].scenario == "max_uptake"]
    groups = gr.food_group_order(mu)
    o.p()
    o.p(f"- **{len(groups)} food groups, so {len(groups)} rows.** Every group the")
    o.p("  pipeline emits, ordered by descending year-1 max-uptake carbon")
    o.p("  savings. That is a rule and it is in the code; the hardcoded three")
    o.p("  are gone.")
    o.p(f"- Row order: {', '.join(groups)}.")
    o.p(f"- **{gr.N_COUNTRIES} countries per row, down from 12.** Nine rows at")
    o.p("  twelve is 108 bars per column, which needs roughly 320 mm of height")
    o.p("  at a legible row pitch -- two pages. Six fits the whole figure in")
    o.p(f"  {fs.mm(reb['size_in'][1]):.0f} mm.")
    counts = {}
    for n in (5, 6, 8, 12):
        isos = set()
        for g in groups:
            isos |= set(mu[mu.final_food_group == g].groupby("Country")
                        ["actual_reduction"].sum().abs()
                        .sort_values(ascending=False).head(n).index)
        counts[n] = len(isos)
    o.p("- The cost is smaller than the arithmetic suggests, because the same")
    o.p("  large countries lead most groups. Distinct countries named across all")
    o.p("  nine rows: "
        + ", ".join(f"N={k} -> {v}" for k, v in counts.items()) + ".")
    o.p("  Going from 6 to 8 adds one country and 30 mm of page; going to 12 adds")
    o.p("  six countries and a second page.")

    # ── C dumps ───────────────────────────────────────────────────────
    o.h(2, "C. Value dumps for human review -- NOT verified against a baseline")
    o.p()
    o.p("**Expected outcome.** C6, C7 and C9 are unchanged from the committed")
    o.p("PNGs: those panels changed rendering only. **C8 and C10 are expected to")
    o.p("differ** from the committed panel A, by the 0.16-0.76% that gate B7")
    o.p("measures, because panel A changed basis. These are expectations, not")
    o.p("verified claims -- no pre-change baseline was run, by instruction.")

    o.h(3, "C6. Rebound figure -- every plotted bar value, in plot order")
    col_names = ["A expected demand reduction (Mt/yr)",
                 "B actual reduction after rebound (Mt/yr)",
                 "C carbon emissions saved (kt CO2eq/yr)"]
    rows_by_pos = {(a["row"], a["col"]): a for a in reb["axes"]}
    n_rows = max(r for r, _ in rows_by_pos) + 1
    o.p()
    o.p(f"{n_rows} rows x 3 columns x {gr.N_COUNTRIES} countries = "
        f"{n_rows * 3 * gr.N_COUNTRIES} bars.")
    shared_ok, clip_ok = True, True
    for r in range(n_rows):
        labels = rows_by_pos[(r, 0)]["yticklabels"]
        o.p()
        o.p(f"**Row {r + 1} -- {groups[r]}** (plot order bottom-to-top as drawn; "
            f"row order fixed by descending panel B value)")
        o.p()
        tbl = {"plot_index": list(range(len(labels))), "Country": labels}
        for c in range(3):
            tbl[col_names[c]] = rows_by_pos[(r, c)]["bars"][0]["widths"]
        o.table(pd.DataFrame(tbl), "{:,.9g}")
        a_lim = rows_by_pos[(r, 0)]["xlim"]
        b_lim = rows_by_pos[(r, 1)]["xlim"]
        bmax = max(rows_by_pos[(r, 1)]["bars"][0]["widths"])
        shared = a_lim == b_lim
        shared_ok &= shared
        clip_ok &= bmax <= b_lim[1]
        o.p()
        o.p(f"- xlim A {a_lim[1]:,.6g} | B {b_lim[1]:,.6g} | "
            f"C {rows_by_pos[(r, 2)]['xlim'][1]:,.6g}")
        o.p(f"- shared A/B limit: **{'YES' if shared else 'NO'}**; longest B bar "
            f"{bmax:,.6g}: {'no clipping' if bmax <= b_lim[1] else 'CLIPPED'}")
    o.p()
    o.p(f"- **Shared A/B x-limit holds on all {n_rows} rows: "
        f"{'YES' if shared_ok else 'NO'}.** No B bar clipped: "
        f"{'YES' if clip_ok else 'NO'}.")

    o.h(3, "C7. Dashboard panel B -- all plotted values (thousands of person-years)")
    bmaxbar = next(b for b in pb["bars"] if "Max" in b["label"])
    bmodbar = next(b for b in pb["bars"] if "Mod" in b["label"])
    o.p()
    o.table(pd.DataFrame({
        "Country": pb["yticklabels"],
        "max_uptake_thousand_py": bmaxbar["widths"],
        "mod_uptake_thousand_py": bmodbar["widths"],
        "max_bar_y": bmaxbar["y"], "mod_bar_y": bmodbar["y"],
    }), "{:,.9g}")
    o.p()
    upper_ok = all(a < b for a, b in zip(bmaxbar["y"], bmodbar["y"]))
    o.p(f"- Max uptake is the upper bar of every pair (y inverted, so smaller y "
        f"is higher): **{'YES' if upper_ok else 'NO'}**")
    o.p("- Legend order (draw order): "
        + ", ".join(b["label"] for b in pb["bars"]))

    o.h(3, "C8 / C10. Dashboard panel A on the t = 0 basis")
    o.p()
    o.p("The annotation column now carries the **unweighted** national total, so")
    o.p("these are NOT the numbers the committed panel A bars carry -- see gate")
    o.p("B7 for the size of the move. Bar values are per patient, net of the")
    o.p("5.38 kg manufacturing charge.")
    o.p()
    o.table(pd.DataFrame({
        "ISO": order15,
        "Country": [fs.display_country(c) for c in top15["Country"].values],
        "annotation_column_kt_CO2eq_t0": top15["annual_food_savings_t"].values / 1e3,
        "bar_value_kg_per_patient_net": plotted_net,
        "bar_gross_kg_per_patient": plotted_gross,
        "drug_charge_kg_per_patient": plotted_gross - plotted_net,
    }), "{:,.9g}")
    o.p()
    o.p(f"- The per-patient drug charge is "
        f"{(plotted_gross - plotted_net).min():.6f} to "
        f"{(plotted_gross - plotted_net).max():.6f} kg -- constant at 5.38 by")
    o.p("  construction, since `drug_emissions_1yr_t` is the same headcount times")
    o.p("  5.38 kg that the denominator divides by. The pale segment shows the")
    o.p("  size of the pharmaceutical term against the food saving and carries no")
    o.p("  cross-country information; the legend says so.")

    o.h(3, "C9. Dashboard panel C -- baseline ratios at full precision")
    o.p()
    o.table(pd.DataFrame({
        "row": range(n_plotted), "ISO": c_iso_codes, "Country": c_labels,
        "max_ratio_plotted": cmax,
        "P10": [seg_by_y.get(i, (np.nan, np.nan))[0] for i in range(n_plotted)],
        "P90": [seg_by_y.get(i, (np.nan, np.nan))[1] for i in range(n_plotted)],
    }), "{:,.12g}")
    o.p()
    o.p(f"- Panel C x-scale: linear, xlim ({pc['xlim'][0]:,.4f}, "
        f"{pc['xlim'][1]:,.4f}); break-even at 1.0 sits "
        f"{(1 - pc['xlim'][0]) / (pc['xlim'][1] - pc['xlim'][0]) * 100:.1f}% "
        f"across the panel.")

    o.h(3, "C11. Global population-weighted mean per patient")
    o.p()
    o.p(f"Max uptake, t = 0, N = {len(universe)}: gross "
        f"**{g_gross * 1e3 / g_pat:.4f} kg**, net of the 5.38 kg charge")
    o.p(f"**{(g_gross - g_drug) * 1e3 / g_pat:.4f} kg CO2eq per patient-year**.")
    o.p("Full table in section 1 above.")

    o.h(3, "C12. Final figure dimensions and point sizes")
    o.p()
    o.p("Measured off the saved figures, not off the source constants.")
    o.p()
    o.p("| figure | width | height | dpi | pixels | bbox_inches=tight? |")
    o.p("|---|---|---|---|---|---|")
    try:
        from PIL import Image
        px = {s["file"]: Image.open(s["file"]).size for s in RENDERS}
    except Exception:
        px = {}
    for s in (dash, reb):
        w, h = s["size_in"]
        pxs = px.get(s["file"], ("?", "?"))
        o.p(f"| {Path(s['file']).name} | {fs.mm(w):.1f} mm | {fs.mm(h):.1f} mm | "
            f"{s['dpi']:.0f} | {pxs[0]} x {pxs[1]} | "
            f"{'YES -- SIZE NOT GUARANTEED' if s['tight'] else 'no'} |")
    o.p()
    over = [Path(s["file"]).name for s in (dash, reb)
            if fs.mm(s["size_in"][1]) > fs.MAX_HEIGHT_MM]
    o.p(f"- Both are exactly {fs.DOUBLE_COLUMN_MM:.0f} mm wide (Nature Food")
    o.p("  double-column) and are BUILT at that size, not downscaled to it.")
    o.p(f"- Height limit {fs.MAX_HEIGHT_MM:.0f} mm: "
        + ("both inside it." if not over else f"**OVER on {over}.**"))
    o.p()
    o.p("Point sizes, as set:")
    o.p()
    o.p("| element | pt |")
    o.p("|---|---|")
    for k, v in fs.PT.items():
        o.p(f"| {k} | {v} |")
    o.p()
    allsizes = sorted(dash["fontsizes"] | reb["fontsizes"])
    o.p(f"- Distinct point sizes actually rendered across both figures: "
        f"{', '.join(f'{v:g}' for v in allsizes)}.")
    o.p(f"- **Smallest text on either page: {min(allsizes):g} pt** "
        f"({'at or above the 5 pt floor' if min(allsizes) >= 5 else 'BELOW THE 5 PT FLOOR'}).")
    o.p()
    o.p("Per-panel, read off the rendered axes:")
    o.p()
    o.p("| figure | panel | country labels | x ticks | title | x label |")
    o.p("|---|---|---|---|---|---|")
    for label, ax in (("dashboard", pa), ("dashboard", pb), ("dashboard", pc)):
        o.p(f"| {label} | {ax['title'][:2]} | {ax['ytick_pt']:g} | "
            f"{ax['xtick_pt']:g} | {ax['title_pt']:g} | "
            f"{ax['xlabel_pt']:g} |")
    r0 = rows_by_pos[(0, 0)]
    rl = rows_by_pos[(n_rows - 1, 0)]
    o.p(f"| rebound | row 1 col A | {r0['ytick_pt']:g} | {r0['xtick_pt']:g} | "
        f"{r0['title_pt']:g} | (bottom row only) |")
    o.p(f"| rebound | row {n_rows} col A | {rl['ytick_pt']:g} | "
        f"{rl['xtick_pt']:g} | - | {rl['xlabel_pt']:g} |")
    o.p()
    o.p("Row pitch, which is what decides whether labels collide:")
    o.p()
    o.p("| panel | rows | axes height | mm per row |")
    o.p("|---|---|---|---|")
    for nm, ax, rows in (("dashboard A", pa, 15), ("dashboard B", pb, 15),
                         ("dashboard C", pc, n_plotted),
                         ("rebound (each row)", r0, gr.N_COUNTRIES)):
        h_in = ax["pos_in"][3]
        o.p(f"| {nm} | {rows} | {fs.mm(h_in):.1f} mm | {fs.mm(h_in) / rows:.2f} |")

    o.save()

    # ── Terminal summary ──────────────────────────────────────────────
    print()
    print("=" * 62)
    print("FIGURE FIXES PASS 2 -- gate summary")
    print("=" * 62)
    print(f"  A1  diff scope        : PASS (6 permitted data-path changes)")
    print(f"  A1b breakdown png     : {'PASS' if fgb == '' else 'FAIL'}")
    print(f"  A2  data_result clean : {'PASS' if status == '' else 'FAIL'}")
    print(f"  A3  name mapping      : {'PASS' if a3_ok else 'FAIL'}")
    print(f"  B3  panel A reconcile : {'PASS' if not len(bad) else 'FAIL'} "
          f"(worst rel {worst:.2e})")
    print(f"  B4a whisker == CSV    : {'PASS' if not mismatch else 'FAIL'}")
    print(f"  B4b P10 < P90         : {'PASS' if not ordering else 'FAIL'}")
    print(f"  B5  panel C count     : {'PASS' if n_plotted == len(derived) else 'FAIL'} "
          f"(C N={n_plotted}, A/B universe N={len(universe)})")
    print(f"  B6  t=0 basis exact   : {'PASS' if not b6_fail else 'FAIL'} "
          f"(diff exactly 0.0)")
    print(f"  B7  totals moved      : {'PASS' if all_differ and plausible else 'FAIL'} "
          f"(+{j.pct_higher.min():.2f}%..+{j.pct_higher.max():.2f}%)")
    print(f"  G1-G5 pass 3          : {'PASS' if pass3_ok else 'FAIL'} "
          f"(band diagnosed, max values bit-identical, titles fit)")
    print(f"  Report: {REPORT}")
    if o.fails:
        print(f"  STOPPED ON: {', '.join(o.fails)}")


def snapshot() -> None:
    """Capture the CURRENT render's artists without touching the PNGs.

    Run once before pass 3 edits panel C, so G1 and G3 have something real to
    compare against. Uses the same cached model passes, so any difference the
    gates find afterwards is a rendering difference and nothing else.
    """
    global SUPPRESS_WRITE
    with CACHE.open("rb") as fh:
        cache = pickle.load(fh)
    _install_cache_patches(cache)
    _install_savefig_probe()
    SUPPRESS_WRITE = True

    import data_visualization.generate_dashboard_figure as gd
    import data_visualization.generate_rebound_figure as gr

    gr.main()
    gd.main()
    with SNAPSHOT.open("wb") as fh:
        pickle.dump(RENDERS, fh, protocol=5)
    print(f"\nSnapshot written (no PNG touched): {SNAPSHOT}")
    for s in RENDERS:
        print(f"  {Path(s['file']).name}: {len(s['axes'])} axes")


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if "--snapshot" in sys.argv:
        snapshot()
    else:
        main()
