"""Part 3 review: headline shifts in key committed CSVs, regenerated vs their
pre-regeneration committed (HEAD) state. Read-only; commits nothing."""
import io
import subprocess
from pathlib import Path
import pandas as pd

ROOT = Path(r"C:\Users\sethw\repos")
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)


def head_df(path):
    r = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=str(ROOT),
                       capture_output=True)
    if r.returncode != 0:
        return None
    data = r.stdout
    if data[:40].startswith(b"version https://git-lfs"):
        s = subprocess.run(["git", "lfs", "smudge"], cwd=str(ROOT),
                           input=data, capture_output=True)
        if s.returncode != 0 or not s.stdout:
            return None
        data = s.stdout
    return pd.read_csv(io.BytesIO(data))


def show(path, cols=None, n=None):
    old = head_df(path); new = pd.read_csv(ROOT / path)
    print("\n" + "=" * 96); print(path); print("=" * 96)
    for name, df in [("PRE (HEAD)", old), ("POST (regen)", new)]:
        if df is None:
            print(f"  [{name}] (no committed version)"); continue
        d = df[cols] if cols else df
        d = d.head(n) if n else d
        print(f"  --- {name} ---")
        print(d.to_string(index=False))


# 1. Waterfalls
show("data_result/global_emissions_waterfall.csv")
show("data_result/global_emissions_waterfall_1yr.csv")

# 2. Supplement table (untracked -> compare vs pre-regen snapshot)
print("\n" + "=" * 96); print("data_result/supplement_results_table.csv (vs pre-regen snapshot)")
print("=" * 96)
snap = pd.read_csv(ROOT / "outputs/fix3/presnapshot/supplement_results_table.csv")
cur = pd.read_csv(ROOT / "data_result/supplement_results_table.csv")
print("  --- PRE (snapshot) ---"); print(snap.to_string(index=False))
print("  --- POST (regen) ---"); print(cur.to_string(index=False))

# 3. Sensitivity results
show("data_result/all_sensitivity_overview_results.csv")
show("data_result/combined_sensitivity_ratio_comparison.csv")
show("data_result/diet_sensitivity_ratio_comparison.csv")
