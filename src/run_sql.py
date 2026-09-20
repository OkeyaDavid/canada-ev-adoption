"""Step 4 - Run every query in sql/02_analysis.sql and print the results.

Run:  python src/run_sql.py            (all queries)
      python src/run_sql.py 3          (only query 3)
Results are also saved as CSVs in data/processed/queries/ for your README.
"""
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 160)
pd.set_option("display.max_rows", 100)

OUT_DIR = Path("data/processed/queries")


def load_queries(path="sql/02_analysis.sql"):
    text = Path(path).read_text()
    blocks = re.split(r"^-- name:\s*", text, flags=re.M)[1:]
    queries = []
    for b in blocks:
        name, _, sql = b.partition("\n")
        queries.append((name.strip(), sql.strip()))
    return queries


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect("data/ev.db") as con:
        for name, sql in load_queries():
            number = name.split(".")[0]
            if only and number != only:
                continue
            df = pd.read_sql_query(sql, con)
            print(f"\n=== {name} ===")
            print(df.to_string(index=False))
            df.to_csv(OUT_DIR / f"query_{number}.csv", index=False)
