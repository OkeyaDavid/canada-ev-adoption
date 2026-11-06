"""Run every query in sql/02_analysis.sql, print it, and save each result as a CSV.

Run:  python src/run_sql.py        (all)
      python src/run_sql.py 3      (one)
"""
import re, sqlite3, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed" / "queries"
pd.set_option("display.width", 170); pd.set_option("display.max_rows", 120)

def queries(path=ROOT / "sql" / "02_analysis.sql"):
    blocks = re.split(r"^-- name:\s*", path.read_text(), flags=re.M)[1:]
    return [(b.split("\n", 1)[0].strip(), b.split("\n", 1)[1].strip()) for b in blocks]

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    OUT.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ROOT / "data" / "ev.db") as con:
        for name, sql in queries():
            n = name.split(".")[0]
            if only and n != only:
                continue
            df = pd.read_sql_query(sql, con)
            print(f"\n=== {name} ===")
            print(df.to_string(index=False))
            df.to_csv(OUT / f"query_{n}.csv", index=False)
