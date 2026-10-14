"""Generate a SYNTHETIC dataset in the UCI "Online Retail" layout.

This is NOT real data. It exists so the upload and cleaning pipeline can be
tested (and demonstrated) without downloading anything. It deliberately
contains the kinds of dirt the real file has:

  - duplicate rows
  - cancellations (invoice numbers starting with "C", negative quantities)
  - stock adjustments (negative quantity without "C")
  - zero and negative prices
  - missing customer IDs and descriptions
  - a few unreadable dates and quantities

Usage:
    python scripts/generate_sample_retail.py --rows 50000 --out sample_retail.csv
    python scripts/generate_sample_retail.py --rows 50000 --out sample_retail.xlsx
"""
import argparse

import numpy as np
import pandas as pd

COUNTRIES = ["United Kingdom", "Germany", "France", "EIRE", "Spain", "Netherlands", "Australia"]
COUNTRY_P = [0.84, 0.04, 0.035, 0.03, 0.02, 0.02, 0.015]


def generate(rows: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n_customers = max(50, rows // 120)
    n_products = max(40, rows // 250)

    customers = rng.integers(12000, 12000 + n_customers, size=rows).astype(float)
    cust_country = {c: rng.choice(COUNTRIES, p=COUNTRY_P) for c in np.unique(customers)}
    products = np.array([f"{rng.integers(10000, 99999)}{rng.choice(list('ABCD'))}" for _ in range(n_products)])
    product_price = rng.uniform(0.4, 25, size=n_products).round(2)
    product_name = np.array([f"SYNTHETIC PRODUCT {i:03d}" for i in range(n_products)])

    start = pd.Timestamp("2010-12-01 08:00:00")
    days = rng.integers(0, 373, size=rows)
    seconds = rng.integers(0, 10 * 3600, size=rows)
    dates = start + pd.to_timedelta(days, unit="D") + pd.to_timedelta(seconds, unit="s")

    # ~4 lines per invoice
    invoice_no = (536000 + np.arange(rows) // 4).astype(str)
    pidx = rng.integers(0, n_products, size=rows)
    qty = rng.choice([1, 2, 3, 4, 6, 8, 12, 24], size=rows, p=[0.3, 0.2, 0.12, 0.1, 0.1, 0.08, 0.07, 0.03])

    df = pd.DataFrame(
        {
            "InvoiceNo": invoice_no,
            "StockCode": products[pidx],
            "Description": product_name[pidx],
            "Quantity": qty.astype(object),
            "InvoiceDate": dates.strftime("%m/%d/%Y %H:%M"),
            "UnitPrice": product_price[pidx],
            "CustomerID": customers,
            "Country": [cust_country[c] for c in customers],
        }
    )
    # keep each invoice to one customer/date, like real data
    first = df.groupby("InvoiceNo").transform("first")
    for col in ["InvoiceDate", "CustomerID", "Country"]:
        df[col] = first[col]

    pick = lambda frac: rng.choice(rows, size=int(rows * frac), replace=False)

    df.loc[pick(0.25), "CustomerID"] = np.nan  # guest purchases
    df.loc[pick(0.01), "Description"] = np.nan
    cancel = pick(0.02)
    df.loc[cancel, "InvoiceNo"] = "C" + df.loc[cancel, "InvoiceNo"]
    df.loc[cancel, "Quantity"] = -df.loc[cancel, "Quantity"].astype(int)
    adj = pick(0.004)
    df.loc[adj, "Quantity"] = -rng.integers(1, 200, size=len(adj))  # adjustment, no "C"
    df.loc[pick(0.003), "UnitPrice"] = 0.0
    df.loc[pick(0.0005), "UnitPrice"] = -rng.uniform(1000, 9000)
    df.loc[pick(0.0005), "InvoiceDate"] = "not a date"
    df.loc[pick(0.0005), "Quantity"] = "abc"
    dupes = df.sample(int(rows * 0.01), random_state=seed)
    df = pd.concat([df, dupes], ignore_index=True)
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=50000)
    ap.add_argument("--out", default="sample_retail.csv")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    data = generate(args.rows, args.seed)
    if args.out.lower().endswith(".xlsx"):
        data.to_excel(args.out, index=False)
    else:
        data.to_csv(args.out, index=False, encoding="cp1252")
    print(f"Wrote {len(data):,} synthetic rows to {args.out}")
