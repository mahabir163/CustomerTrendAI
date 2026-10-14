"""Upload → validate → read → map columns → clean → save.

`process_upload` is the single entry point used by the view. It either returns a
fully imported dataset or raises `DatasetImportError` with a message that is safe
to show to the user. Nothing is left half-saved if something fails.
"""
import io
import re
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from ..models import Customer, Transaction, UploadedDataset
from . import data_cleaning

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
XLSX_MAGIC = b"PK\x03\x04"  # .xlsx files are zip archives
PREVIEW_ROWS = 20
DB_CHUNK = 5000

# Internal field -> header names we recognise (compared after normalising).
COLUMN_ALIASES = {
    "invoice_no": ["invoiceno", "invoice", "invoicenumber", "invoiceid", "orderid", "orderno", "ordernumber"],
    "stock_code": ["stockcode", "sku", "productcode", "productid", "itemcode"],
    "description": ["description", "productname", "product", "itemdescription", "itemname"],
    "quantity": ["quantity", "qty", "units"],
    "invoice_date": ["invoicedate", "orderdate", "transactiondate", "date", "datetime", "timestamp"],
    "unit_price": ["unitprice", "price", "priceperunit", "sellingprice"],
    "customer_id": ["customerid", "customer", "customerno", "custid", "clientid", "userid"],
    "country": ["country", "customercountry"],
}
REQUIRED_COLUMNS = ["invoice_no", "stock_code", "quantity", "invoice_date", "unit_price", "customer_id"]
OPTIONAL_COLUMNS = ["description", "country"]

_ALIAS_LOOKUP = {
    alias: internal
    for internal, aliases in COLUMN_ALIASES.items()
    for alias in [internal.replace("_", ""), *aliases]
}


class DatasetImportError(Exception):
    """A problem with the uploaded file that the user can understand and fix."""


# --- 1. check the file itself ---------------------------------------------------
def validate_upload_file(upload) -> str:
    """Check extension, size and content type. Returns the lower-case extension."""
    ext = Path(upload.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DatasetImportError("Unsupported file type. Please upload a .csv or .xlsx file.")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if upload.size > max_bytes:
        raise DatasetImportError(f"File is too large. The limit is {settings.MAX_UPLOAD_SIZE_MB} MB.")
    if upload.size == 0:
        raise DatasetImportError("The file is empty.")

    # Never trust the extension alone: check the first bytes really match.
    upload.seek(0)
    head = upload.read(4096)
    upload.seek(0)
    if ext == ".xlsx" and not head.startswith(XLSX_MAGIC):
        raise DatasetImportError("This file has an .xlsx extension but is not a valid Excel workbook.")
    if ext == ".csv" and (b"\x00" in head or head.startswith(XLSX_MAGIC)):
        raise DatasetImportError("This file has a .csv extension but does not look like a text CSV file.")
    return ext


# --- 2. read it ----------------------------------------------------------------
def _read_csv(data: bytes) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 never fails
        raise DatasetImportError("Could not decode the file. Please save it as UTF-8 CSV.")

    first_line = text.split("\n", 1)[0]
    delimiter = max([",", ";", "\t", "|"], key=first_line.count)
    return pd.read_csv(
        io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False, skip_blank_lines=True
    )


def read_table(data: bytes, ext: str) -> pd.DataFrame:
    """Read the file into a DataFrame where every value is still text."""
    try:
        if ext == ".csv":
            df = _read_csv(data)
        else:
            df = pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False, engine="openpyxl")
    except DatasetImportError:
        raise
    except Exception as exc:
        raise DatasetImportError(
            "The file could not be read. Check that it is a valid, uncorrupted CSV or Excel file."
        ) from exc

    if df.empty:
        raise DatasetImportError("The file has a header but no data rows.")
    if len(df) > settings.MAX_UPLOAD_ROWS:
        raise DatasetImportError(
            f"The file has {len(df):,} rows; the limit is {settings.MAX_UPLOAD_ROWS:,}."
        )
    return df


# --- 3. map column names -------------------------------------------------------
def normalise_header(header) -> str:
    """'Invoice No.' -> 'invoiceno', so 'InvoiceNo' and 'invoice_no' match."""
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


def map_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Rename recognised columns to internal names; return (table, mapping)."""
    mapping: dict[str, str] = {}
    for original in df.columns:
        internal = _ALIAS_LOOKUP.get(normalise_header(original))
        if internal is None:
            continue
        if internal in mapping:
            raise DatasetImportError(
                f"Columns '{mapping[internal]}' and '{original}' both look like '{internal}'. "
                "Please keep only one of them."
            )
        mapping[internal] = original

    missing = [c for c in REQUIRED_COLUMNS if c not in mapping]
    if missing:
        hints = "; ".join(f"{c} (e.g. {COLUMN_ALIASES[c][0]})" for c in missing)
        raise DatasetImportError(
            f"Missing required column(s): {', '.join(missing)}. Expected something like: {hints}. "
            f"Columns found in your file: {', '.join(map(str, df.columns))}."
        )

    mapped = df[[mapping[c] for c in mapping]].copy()
    mapped.columns = list(mapping)
    for optional in OPTIONAL_COLUMNS:
        if optional not in mapped.columns:
            mapped[optional] = pd.NA
    return mapped[data_cleaning.INTERNAL_COLUMNS], mapping


def _build_preview(df: pd.DataFrame) -> dict:
    head = df.head(PREVIEW_ROWS).fillna("").astype(str)
    return {"columns": list(head.columns), "rows": head.values.tolist()}


# --- 4. save to the database -----------------------------------------------------
def persist(dataset: UploadedDataset, cleaned: pd.DataFrame) -> None:
    """Write customers and transactions for one dataset (all-or-nothing)."""
    with transaction.atomic():
        known = cleaned.dropna(subset=["customer_id"])
        # A customer's country = the country they bought from most often.
        home = (
            known.groupby(["customer_id", "country"]).size().reset_index(name="n")
            .sort_values(["customer_id", "n"], ascending=[True, False])
            .drop_duplicates("customer_id")
        )
        Customer.objects.bulk_create(
            [
                Customer(dataset=dataset, external_id=cid, country=country)
                for cid, country in zip(home["customer_id"], home["country"])
            ],
            batch_size=DB_CHUNK,
        )
        id_lookup = dict(Customer.objects.filter(dataset=dataset).values_list("external_id", "id"))

        customer_pk = cleaned["customer_id"].map(id_lookup)
        for start in range(0, len(cleaned), DB_CHUNK):
            part = cleaned.iloc[start : start + DB_CHUNK]
            pks = customer_pk.iloc[start : start + DB_CHUNK]
            Transaction.objects.bulk_create(
                [
                    Transaction(
                        dataset=dataset,
                        customer_id=None if pd.isna(pk) else int(pk),
                        invoice_no=row.invoice_no,
                        stock_code=row.stock_code[:40],
                        description=row.description[:255],
                        quantity=int(row.quantity),
                        invoice_date=row.invoice_date.to_pydatetime(),
                        unit_price=row.unit_price,
                        line_total=row.line_total,
                        country=row.country[:80],
                        is_cancellation=bool(row.is_cancellation),
                    )
                    for row, pk in zip(part.itertuples(index=False), pks)
                ]
            )


# --- the entry point -------------------------------------------------------------
def process_upload(*, owner, upload, name: str = "") -> UploadedDataset:
    ext = validate_upload_file(upload)
    data = upload.read()

    raw = read_table(data, ext)
    mapped, mapping = map_columns(raw)
    standard = data_cleaning.standardise_text(mapped)

    quality = {"raw": data_cleaning.build_quality_report(standard)}
    result = data_cleaning.clean(standard)
    if result.cleaned.empty:
        raise DatasetImportError(
            "No usable rows remain after cleaning. Check that quantities, prices and dates are valid."
        )
    quality.update(result.report)

    dataset = UploadedDataset(
        owner=owner,
        name=(name.strip() or Path(upload.name).stem)[:120],
        original_filename=Path(upload.name).name[:255],
        raw_row_count=len(raw),
        clean_row_count=len(result.cleaned),
        column_mapping=mapping,
        preview=_build_preview(standard),
        quality_report=quality,
        status=UploadedDataset.Status.PROCESSING,
    )
    try:
        dataset.original_file.save(f"original{ext}", ContentFile(data), save=False)
        dataset.cleaned_file.save("cleaned.csv", ContentFile(data_cleaning.cleaned_to_csv_bytes(result.cleaned)), save=False)
        dataset.save()
        persist(dataset, result.cleaned)
        dataset.status = UploadedDataset.Status.READY
        dataset.save(update_fields=["status", "updated_at"])
    except Exception as exc:
        # Leave nothing behind: remove files and any partial rows.
        if dataset.pk:
            dataset.delete()
        dataset.delete_files()
        raise DatasetImportError("Saving the dataset failed. Nothing was imported; please try again.") from exc
    return dataset
