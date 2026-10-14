"""Shared test helpers: tiny datasets built in memory."""
import io

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile

HEADER = "InvoiceNo,StockCode,Description,Quantity,InvoiceDate,UnitPrice,CustomerID,Country"

# One row per cleaning rule, so each test can point at exactly one line.
GOOD_ROWS = [
    "536365,85123A,WHITE HANGING HEART,6,12/1/2010 8:26,2.55,17850,United Kingdom",
    "536365,71053,WHITE METAL LANTERN,6,12/1/2010 8:26,3.39,17850,United Kingdom",
    "536366,22633,HAND WARMER,6,12/1/2010 8:28,1.85,13047.0,United Kingdom",
    "C536379,D,Discount,-1,12/1/2010 9:41,27.50,14527,United Kingdom",  # cancellation: KEPT
    "536400,22960,JAM MAKING SET,4,12/2/2010 10:00,4.25,,France",  # no customer: KEPT
]
BAD_ROWS = {
    "duplicate_rows": "536365,85123A,WHITE HANGING HEART,6,12/1/2010 8:26,2.55,17850,United Kingdom",
    "negative_quantity_not_cancellation": "536500,22000,DAMAGED,-5,12/3/2010 9:00,1.00,17850,United Kingdom",
    "zero_price": "536501,22001,FREE GIFT,1,12/3/2010 9:05,0,17850,United Kingdom",
    "negative_price": "A536502,B,Adjust bad debt,1,12/3/2010 9:10,-100.5,,United Kingdom",
    "invalid_date": "536503,22002,BAD DATE,1,not a date,2.00,17850,United Kingdom",
    "invalid_quantity": "536504,22003,BAD QTY,abc,12/3/2010 9:20,2.00,17850,United Kingdom",
    "invalid_price": "536505,22004,BAD PRICE,1,12/3/2010 9:25,free,17850,United Kingdom",
    "zero_quantity": "536506,22005,ZERO QTY,0,12/3/2010 9:30,2.00,17850,United Kingdom",
    "missing_invoice_no": ",22006,NO INVOICE,1,12/3/2010 9:35,2.00,17850,United Kingdom",
    "cancellation_with_positive_quantity": "C536507,22007,ODD CANCEL,3,12/3/2010 9:40,2.00,17850,United Kingdom",
}


def csv_text(rows, header=HEADER):
    return "\n".join([header, *rows]) + "\n"


def csv_upload(rows=None, header=HEADER, name="retail.csv"):
    rows = list(GOOD_ROWS) + list(BAD_ROWS.values()) if rows is None else rows
    return SimpleUploadedFile(name, csv_text(rows, header).encode("utf-8"), content_type="text/csv")


def xlsx_upload(name="retail.xlsx"):
    """An Excel file where customer IDs are floats and dates are real datetimes, like the UCI file."""
    import datetime as dt

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER.split(","))
    ws.append(["536365", "85123A", "WHITE HANGING HEART", 6, dt.datetime(2010, 12, 1, 8, 26), 2.55, 17850.0, "United Kingdom"])
    ws.append(["536366", "22633", "HAND WARMER", 6, dt.datetime(2010, 12, 1, 8, 28), 1.85, 13047.0, "United Kingdom"])
    ws.append(["C536379", "D", "Discount", -1, dt.datetime(2010, 12, 1, 9, 41), 27.5, 14527.0, "United Kingdom"])
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(name, buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
