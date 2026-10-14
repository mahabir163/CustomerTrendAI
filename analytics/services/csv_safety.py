"""Protection against CSV formula injection.

If a text cell in a CSV starts with `=`, `+`, `-` or `@`, Excel and Google
Sheets may treat it as a formula and execute it (for example `=HYPERLINK(...)`).
Because customers' own data ends up in files that users download and open in
Excel, every exported text cell passes through `sanitize_cell` first.

The standard defence (OWASP) is to prefix such cells with a single quote so the
spreadsheet shows them as plain text. Numeric columns are never touched,
otherwise a legitimate quantity of -3 would be changed into text.
"""
import pandas as pd

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def sanitize_text_columns(df: pd.DataFrame, text_columns) -> pd.DataFrame:
    out = df.copy()
    for col in text_columns:
        if col in out.columns:
            out[col] = out[col].map(sanitize_cell)
    return out
