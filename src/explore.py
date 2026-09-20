"""Step 2 - First look at the raw StatCan file.

Run:  python src/explore.py
Prints the columns, the values in each dimension and the date range,
so you understand the data before cleaning it.
"""
import zipfile
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")


def open_raw_csv():
    """Return a file handle to 20100025.csv, reading it straight from the ZIP if needed."""
    csv_path = RAW_DIR / "20100025.csv"
    if csv_path.exists():
        return open(csv_path, encoding="utf-8-sig")
    zip_path = RAW_DIR / "20100025-eng.zip"
    if zip_path.exists():
        z = zipfile.ZipFile(zip_path)
        return z.open("20100025.csv")
    raise FileNotFoundError(
        "Put 20100025-eng.zip (or the unzipped 20100025.csv) in data/raw/ first."
    )


if __name__ == "__main__":
    df = pd.read_csv(open_raw_csv(), low_memory=False, encoding="utf-8-sig")

    print(f"Rows: {len(df):,}   Columns: {df.shape[1]}")
    print("\nColumns:", df.columns.tolist())

    print(f"\nDate range: {df['REF_DATE'].min()} to {df['REF_DATE'].max()}")
    print(f"Distinct places (GEO): {df['GEO'].nunique():,}")

    # Every column between GEO/DGUID and UOM is a 'dimension' (fuel type, vehicle type ...)
    skip = {"REF_DATE", "GEO", "DGUID", "UOM", "UOM_ID", "SCALAR_FACTOR", "SCALAR_ID",
            "VECTOR", "COORDINATE", "VALUE", "STATUS", "SYMBOL", "TERMINATED", "DECIMALS"}
    for col in df.columns:
        if col not in skip:
            print(f"\n{col}:")
            for v in df[col].dropna().unique():
                print("   ", v)

    print("\nFirst 5 rows:")
    print(df.head().to_string())
