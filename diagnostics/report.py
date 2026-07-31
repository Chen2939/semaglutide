"""Write diagnostic output to a markdown file instead of the terminal.

Wide tables printed to a Windows console have arrived mangled repeatedly: the
console falls back to cp1252, box-drawing and other non-ASCII characters are
replaced or dropped, and long pandas frames wrap at the terminal width so columns
no longer line up with their headers. Reviewing a mangled table costs more than
writing a file does.

So diagnostics build a markdown report and print only its path. The file is
UTF-8, the tables are pipe-delimited markdown that renders anywhere, and nothing
depends on the console encoding.

    from diagnostics.report import Report

    rep = Report("my_check", "What this check establishes")
    rep.h2("A section")
    rep.text("A sentence.")
    rep.table(df)
    rep.kv({"cells compared": 1890, "differing": 0})
    rep.save()          # prints the path

Reports go to diagnostics/reports/<name>.md, which is gitignored: the script is
the record, its output is regenerable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

REPORT_DIR = Path(__file__).resolve().parent / "reports"


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        if v != v:  # NaN
            return "n/a"
        if v == 0:
            return "0"
        if abs(v) < 1e-4 or abs(v) >= 1e7:
            return f"{v:.4e}"
        return f"{v:,.6f}".rstrip("0").rstrip(".")
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


class Report:
    """Accumulates markdown, then writes it in one go."""

    def __init__(self, name: str, subtitle: str = "") -> None:
        self.name = name
        self._lines: list[str] = [f"# {name}", ""]
        if subtitle:
            self._lines += [subtitle, ""]

    # ── structure ────────────────────────────────────────────────────────
    def h2(self, title: str) -> "Report":
        self._lines += ["", f"## {title}", ""]
        return self

    def h3(self, title: str) -> "Report":
        self._lines += ["", f"### {title}", ""]
        return self

    def text(self, body: str) -> "Report":
        self._lines += [body, ""]
        return self

    def bullet(self, body: str) -> "Report":
        self._lines.append(f"- {body}")
        return self

    def code(self, body: str, lang: str = "") -> "Report":
        self._lines += [f"```{lang}", body.rstrip("\n"), "```", ""]
        return self

    def verdict(self, label: str, ok: bool) -> "Report":
        self._lines.append(f"- **{'PASS' if ok else 'FAIL'}** — {label}")
        return self

    # ── data ─────────────────────────────────────────────────────────────
    def kv(self, mapping: Mapping[str, Any], header=("quantity", "value")) -> "Report":
        self._lines += [f"| {header[0]} | {header[1]} |", "|---|--:|"]
        for k, v in mapping.items():
            self._lines.append(f"| {k} | {_fmt(v)} |")
        self._lines.append("")
        return self

    def table(self, df: pd.DataFrame, index: bool = False) -> "Report":
        """Render a DataFrame as a markdown table. No width, no wrapping."""
        d = df.reset_index() if index else df
        cols = [str(c) for c in d.columns]
        numeric = [
            pd.api.types.is_numeric_dtype(d[c]) and not pd.api.types.is_bool_dtype(d[c])
            for c in d.columns
        ]
        self._lines.append("| " + " | ".join(cols) + " |")
        self._lines.append("|" + "|".join("--:" if n else "---" for n in numeric) + "|")
        for _, row in d.iterrows():
            self._lines.append("| " + " | ".join(_fmt(row[c]) for c in d.columns) + " |")
        self._lines.append("")
        return self

    # ── output ───────────────────────────────────────────────────────────
    def save(self, quiet: bool = False) -> Path:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / f"{self.name}.md"
        path.write_text("\n".join(self._lines).rstrip("\n") + "\n", encoding="utf-8")
        if not quiet:
            # The only thing that goes to the console: an ASCII path.
            print(f"Report written to: {path.relative_to(REPORT_DIR.parent.parent)}")
        return path
