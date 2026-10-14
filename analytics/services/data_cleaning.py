"""Data quality report and cleaning rules.

Input: a DataFrame whose columns already use the internal names
(invoice_no, stock_code, description, quantity, invoice_date, unit_price,
customer_id, country) and whose values are still text.

Two separate steps, on purpose:

1. `build_quality_report` only *measures* problems. Counts can overlap
   (one row can have both a bad date and a zero price).
2. `clean` applies the rules in a fixed order and records how many rows each
   rule removed. A row is counted once, under the FIRST rule that removes it,
   so these counts add up exactly to rows_in - rows_kept.

The rules are listed in CLEANING_RULES, which the UI shows to the user, so the
documentation can never drift away from what the code does.
"""
import warnings
from dataclasses import dataclass

import pandas as pd

from .csv_safety import sanitize_text_columns

INTERNAL_COLUMNS = [
    "invoice_no",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
]
MISSING_TOKENS = {"", "nan", "none", "null", "na", "n/a", "nat"}
CANCELLATION_PREFIX = "C"

# Shown to the user on the dataset page. Order = order the rules are applied.
CLEANING_RULES = [
    {
        "id": "standardise",
        "title": "Standardise text",
        "description": "Leading/trailing spaces are trimmed. Empty cells and the words NA, N/A, null, none and nan count as missing.",
    },
    {
        "id": "missing_invoice_no",
        "title": "Remove rows with no invoice number",
        "description": "Without an invoice number a line cannot be assigned to an order.",
    },
    {
        "id": "duplicate_rows",
        "title": "Remove exact duplicate rows",
        "description": "Rows identical in every column are treated as double-entered; the first copy is kept.",
    },
    {
        "id": "invalid_quantity",
        "title": "Remove rows with an invalid quantity",
        "description": "Quantity must be a whole number.",
    },
    {
        "id": "invalid_price",
        "title": "Remove rows with an invalid unit price",
        "description": "Unit price must be a number.",
    },
    {
        "id": "invalid_date",
        "title": "Remove rows with an invalid date",
        "description": "The invoice date must be readable as a date and time. Dates written like 12/1/2010 are read month-first. Times are stored as given (treated as UTC).",
    },
    {
        "id": "zero_quantity",
        "title": "Remove rows with a quantity of zero",
        "description": "A line with nothing sold carries no information.",
    },
    {
        "id": "negative_price",
        "title": "Remove rows with a negative unit price",
        "description": "Negative prices are accounting adjustments (for example bad-debt write-offs), not sales.",
    },
    {
        "id": "zero_price",
        "title": "Remove rows with a unit price of zero",
        "description": "Free items and stock adjustments would distort revenue and average order value.",
    },
    {
        "id": "negative_quantity_not_cancellation",
        "title": "Remove negative quantities that are not cancellations",
        "description": "A negative quantity on an invoice that does not start with 'C' is a stock adjustment (damaged, lost, sample), not a customer return.",
    },
    {
        "id": "cancellation_with_positive_quantity",
        "title": "Remove inconsistent cancellation rows",
        "description": "An invoice starting with 'C' must have a negative quantity; otherwise the row contradicts itself.",
    },
    {
        "id": "keep_cancellations",
        "title": "KEEP cancellations and returns (flagged)",
        "description": "Invoices starting with 'C' with a negative quantity are real customer returns. They are kept and flagged is_cancellation=True, with negative quantity and line total. Later phases subtract them from net revenue and exclude them from purchase counts, instead of silently deleting them.",
    },
    {
        "id": "keep_missing_customer",
        "title": "KEEP rows with no customer ID",
        "description": "These are guest purchases. They count towards revenue and orders but are excluded from customer-level analysis such as RFM, because they cannot be attributed to a person.",
    },
]

DROP_LABELS = {
    "missing_invoice_no": "Missing invoice number",
    "duplicate_rows": "Exact duplicate rows",
    "invalid_quantity": "Invalid quantity",
    "invalid_price": "Invalid unit price",
    "invalid_date": "Invalid date",
    "zero_quantity": "Quantity of zero",
    "negative_price": "Negative unit price",
    "zero_price": "Unit price of zero",
    "negative_quantity_not_cancellation": "Negative quantity, not a cancellation",
    "cancellation_with_positive_quantity": "Cancellation with positive quantity",
}


@dataclass
class CleaningResult:
    cleaned: pd.DataFrame
    report: dict  # the "cleaning" and "clean" sections of the quality report


# --- helpers ---------------------------------------------------------------
def standardise_text(df: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace and turn empty/NA-like tokens into real missing values."""
    out = df.copy()
    for col in out.columns:
        s = out[col].astype("string").str.strip()
        out[col] = s.mask(s.str.lower().isin(MISSING_TOKENS))
    return out


def parse_numbers(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("float64")


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse dates fast when they share one format, slowly when they are mixed.

    Naive timestamps are interpreted as UTC so they are stored exactly as
    written, with no daylight-saving surprises.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
        retry = parsed.isna() & series.notna()
        if retry.any():
            parsed.loc[retry] = pd.to_datetime(series[retry], errors="coerce", utc=True, format="mixed")
    return parsed


def _is_cancellation(invoice_no: pd.Series) -> pd.Series:
    return invoice_no.str.upper().str.startswith(CANCELLATION_PREFIX).fillna(False).astype(bool)


def _count(mask) -> int:
    return int(pd.Series(mask).fillna(False).sum())


# --- 1. measure -------------------------------------------------------------
def build_quality_report(df: pd.DataFrame) -> dict:
    """Count problems in the raw data without changing it."""
    qty = parse_numbers(df["quantity"])
    price = parse_numbers(df["unit_price"])
    dates = parse_dates(df["invoice_date"])
    is_c = _is_cancellation(df["invoice_no"].fillna(""))

    return {
        "rows": int(len(df)),
        "missing_values": {col: int(df[col].isna().sum()) for col in df.columns},
        "duplicate_rows": int(df.duplicated().sum()),
        "invalid_dates": _count(dates.isna()),
        "invalid_quantity": _count(qty.isna() | (qty % 1 != 0)),
        "invalid_price": _count(price.isna()),
        "negative_quantity": _count(qty < 0),
        "negative_quantity_cancellations": _count((qty < 0) & is_c),
        "negative_quantity_other": _count((qty < 0) & ~is_c),
        "zero_quantity": _count(qty == 0),
        "zero_price": _count(price == 0),
        "negative_price": _count(price < 0),
        "missing_customer_id": int(df["customer_id"].isna().sum()),
        "cancellation_rows": _count(is_c),
    }


# --- 2. clean ---------------------------------------------------------------
def clean(df: pd.DataFrame) -> CleaningResult:
    """Apply the cleaning rules in order and return the cleaned table."""
    rows_in = len(df)
    dropped: dict[str, int] = {}
    work = df.copy()

    def drop(mask: pd.Series, key: str) -> None:
        nonlocal work
        mask = mask.fillna(False).astype(bool)
        dropped[key] = int(mask.sum())
        work = work[~mask]

    drop(work["invoice_no"].isna(), "missing_invoice_no")
    drop(work.duplicated(keep="first"), "duplicate_rows")

    work = work.assign(
        _qty=parse_numbers(work["quantity"]),
        _price=parse_numbers(work["unit_price"]),
        _date=parse_dates(work["invoice_date"]),
    )
    drop(work["_qty"].isna() | (work["_qty"] % 1 != 0), "invalid_quantity")
    drop(work["_price"].isna(), "invalid_price")
    drop(work["_date"].isna(), "invalid_date")
    drop(work["_qty"] == 0, "zero_quantity")
    drop(work["_price"] < 0, "negative_price")
    drop(work["_price"] == 0, "zero_price")

    is_c = _is_cancellation(work["invoice_no"])
    drop((work["_qty"] < 0) & ~is_c, "negative_quantity_not_cancellation")
    is_c = _is_cancellation(work["invoice_no"])
    drop(is_c & (work["_qty"] > 0), "cancellation_with_positive_quantity")

    cleaned = pd.DataFrame(
        {
            "invoice_no": work["invoice_no"].astype(str),
            "stock_code": work["stock_code"].fillna("UNKNOWN").astype(str),
            "description": work["description"].fillna("").astype(str),
            "quantity": work["_qty"].astype("int64"),
            "invoice_date": work["_date"],
            "unit_price": work["_price"].round(4),
            # Customer IDs often arrive as 17850.0 (Excel stores them as floats).
            "customer_id": work["customer_id"].str.replace(r"\.0+$", "", regex=True),
            "country": work["country"].fillna("Unknown").astype(str),
        }
    ).reset_index(drop=True)
    cleaned["is_cancellation"] = _is_cancellation(cleaned["invoice_no"])
    cleaned["line_total"] = (cleaned["quantity"] * cleaned["unit_price"]).round(4)

    report = {
        "cleaning": {
            "rows_in": int(rows_in),
            "rows_kept": int(len(cleaned)),
            "rows_removed": int(rows_in - len(cleaned)),
            "dropped": dropped,
        },
        "clean": {
            "rows": int(len(cleaned)),
            "invoices": int(cleaned["invoice_no"].nunique()),
            "customers": int(cleaned["customer_id"].nunique()),
            "stock_codes": int(cleaned["stock_code"].nunique()),
            "countries": int(cleaned["country"].nunique()),
            "cancellation_rows": int(cleaned["is_cancellation"].sum()),
            "rows_without_customer": int(cleaned["customer_id"].isna().sum()),
            "date_min": cleaned["invoice_date"].min().isoformat() if len(cleaned) else None,
            "date_max": cleaned["invoice_date"].max().isoformat() if len(cleaned) else None,
        },
    }
    return CleaningResult(cleaned=cleaned, report=report)


# --- output helpers -----------------------------------------------------------
TEXT_COLUMNS = ["invoice_no", "stock_code", "description", "customer_id", "country"]


def cleaned_to_csv_bytes(cleaned: pd.DataFrame) -> bytes:
    """Serialise the cleaned table as CSV, safe to open in Excel."""
    out = cleaned.copy()
    out["invoice_date"] = out["invoice_date"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out = sanitize_text_columns(out, TEXT_COLUMNS)
    return out.to_csv(index=False).encode("utf-8")


def describe_quality_issues(report: dict) -> list[dict]:
    """Turn the raw counts into table rows for the UI (label, count, %, handling)."""
    raw = report.get("raw", {})
    total = raw.get("rows") or 0

    def row(label, key, handling):
        count = raw.get(key, 0)
        pct = round(100 * count / total, 2) if total else 0
        return {"label": label, "count": count, "pct": pct, "handling": handling}

    return [
        row("Missing customer ID", "missing_customer_id", "Kept as guest purchases; excluded from customer-level analysis."),
        row("Exact duplicate rows", "duplicate_rows", "Removed (first copy kept)."),
        row("Invalid or missing dates", "invalid_dates", "Removed."),
        row("Invalid quantities", "invalid_quantity", "Removed."),
        row("Invalid unit prices", "invalid_price", "Removed."),
        row("Negative quantities: cancellations/returns", "negative_quantity_cancellations", "Kept and flagged as cancellations."),
        row("Negative quantities: other (stock adjustments)", "negative_quantity_other", "Removed."),
        row("Unit price of zero", "zero_price", "Removed."),
        row("Negative unit price", "negative_price", "Removed."),
        row("Quantity of zero", "zero_quantity", "Removed."),
    ]


def describe_dropped(report: dict) -> list[dict]:
    dropped = report.get("cleaning", {}).get("dropped", {})
    return [{"label": DROP_LABELS.get(k, k), "count": v} for k, v in dropped.items()]
