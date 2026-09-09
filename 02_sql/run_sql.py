#!/usr/bin/env python3
"""
Run the SQL files in this directory against db/restaurant_saas.db, print a
preview of every result, and export each query to outputs/sql_results/.

Queries are separated by markers in the form "-- >>> query_name".

Run: python 02_sql/run_sql.py            (all files)
     python 02_sql/run_sql.py 04         (files whose names begin with 04)
"""
from pathlib import Path
import sqlite3
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "restaurant_saas.db"
OUT = ROOT / "outputs" / "sql_results"
OUT.mkdir(parents=True, exist_ok=True)

prefix = sys.argv[1] if len(sys.argv) > 1 else ""
files = sorted(p for p in Path(__file__).parent.glob("*.sql") if p.name.startswith(prefix))
con = sqlite3.connect(DB)
pd.set_option("display.width", 160, "display.max_columns", 40)

total = 0
for f in files:
    text = f.read_text()
    blocks = []
    current_name, current_sql = None, []
    for line in text.splitlines():
        if line.startswith("-- >>> "):
            if current_name:
                blocks.append((current_name, "\n".join(current_sql)))
            current_name, current_sql = line.replace("-- >>> ", "").strip(), []
        elif current_name is not None:
            current_sql.append(line)
    if current_name:
        blocks.append((current_name, "\n".join(current_sql)))

    for name, sql in blocks:
        sql = sql.strip().rstrip(";")
        if not sql:
            continue
        df = pd.read_sql_query(sql, con)
        path = OUT / f"{f.stem}__{name}.csv"
        df.to_csv(path, index=False)
        total += 1
        print(f"\n{'=' * 100}\n{f.name}  >>>  {name}   ({len(df):,} rows)\n{'=' * 100}")
        print(df.head(12).to_string(index=False))

con.close()
print(f"\n\nExecuted {total} queries. Results saved to {OUT}")
