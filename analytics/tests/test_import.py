import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from analytics.models import Customer, Transaction, UploadedDataset
from analytics.services.data_import import (
    DatasetImportError,
    map_columns,
    normalise_header,
    process_upload,
    read_table,
    validate_upload_file,
)

from .helpers import HEADER, csv_text, csv_upload, xlsx_upload

User = get_user_model()


class ColumnMappingTests(SimpleTestCase):
    def test_header_normalisation(self):
        self.assertEqual(normalise_header("Invoice No."), "invoiceno")
        self.assertEqual(normalise_header("unit_price"), "unitprice")

    def test_uci_headers_map_to_internal_names(self):
        raw = read_table(csv_text([]).encode() + b"1,A,d,1,2010-01-01,1,1,UK\n", ".csv")
        _, mapping = map_columns(raw)
        self.assertEqual(mapping["invoice_no"], "InvoiceNo")
        self.assertEqual(mapping["unit_price"], "UnitPrice")
        self.assertEqual(len(mapping), 8)

    def test_alternative_headers_are_recognised(self):
        header = "order_id,sku,product,qty,order date,price,customer,region_x"
        raw = read_table((header + "\n1,A,d,1,2010-01-01,1,1,UK\n").encode(), ".csv")
        _, mapping = map_columns(raw)
        self.assertEqual(mapping["invoice_no"], "order_id")
        self.assertEqual(mapping["invoice_date"], "order date")
        self.assertNotIn("country", mapping)  # optional, and 'region_x' is not recognised

    def test_missing_required_columns_gives_helpful_error(self):
        header = "InvoiceNo,StockCode,Quantity,InvoiceDate,CustomerID"  # no UnitPrice
        raw = read_table((header + "\n1,A,1,2010-01-01,1\n").encode(), ".csv")
        with self.assertRaises(DatasetImportError) as ctx:
            map_columns(raw)
        self.assertIn("unit_price", str(ctx.exception))
        self.assertIn("InvoiceNo", str(ctx.exception))  # lists what it did find

    def test_two_columns_for_one_field_is_rejected(self):
        header = HEADER + ",Price"
        raw = read_table((header + "\n1,A,d,1,2010-01-01,1,1,UK,2\n").encode(), ".csv")
        with self.assertRaises(DatasetImportError):
            map_columns(raw)

    def test_semicolon_delimiter_and_latin1_encoding(self):
        text = "InvoiceNo;StockCode;Description;Quantity;InvoiceDate;UnitPrice;CustomerID;Country\n1;A;Café;1;2010-01-01;1,0;1;UK\n"
        df = read_table(text.encode("cp1252"), ".csv")
        self.assertEqual(list(df["Description"]), ["Café"])


class FileValidationTests(SimpleTestCase):
    def check(self, name, content):
        return validate_upload_file(SimpleUploadedFile(name, content))

    def test_accepts_csv_and_xlsx(self):
        self.assertEqual(self.check("a.csv", b"a,b\n1,2\n"), ".csv")
        self.assertEqual(self.check("a.XLSX", b"PK\x03\x04rest"), ".xlsx")

    def test_rejects_unsupported_extensions(self):
        for name in ["a.txt", "a.exe", "a.xls", "a.csv.php", "a"]:
            with self.subTest(name=name), self.assertRaises(DatasetImportError):
                self.check(name, b"a,b\n")

    def test_rejects_empty_file(self):
        with self.assertRaises(DatasetImportError):
            self.check("a.csv", b"")

    def test_rejects_fake_xlsx(self):
        with self.assertRaises(DatasetImportError):
            self.check("a.xlsx", b"just text pretending")

    def test_rejects_binary_csv(self):
        with self.assertRaises(DatasetImportError):
            self.check("a.csv", b"abc\x00\x01\x02binary")

    def test_rejects_xlsx_renamed_to_csv(self):
        with self.assertRaises(DatasetImportError):
            self.check("a.csv", b"PK\x03\x04rest")

    @override_settings(MAX_UPLOAD_SIZE_MB=0)
    def test_rejects_oversized_file(self):
        with self.assertRaises(DatasetImportError) as ctx:
            self.check("a.csv", b"a,b\n1,2\n")
        self.assertIn("too large", str(ctx.exception))

    @override_settings(MAX_UPLOAD_ROWS=2)
    def test_rejects_too_many_rows(self):
        with self.assertRaises(DatasetImportError):
            read_table(b"a,b\n1,2\n3,4\n5,6\n", ".csv")

    def test_header_only_file_is_rejected(self):
        with self.assertRaises(DatasetImportError):
            read_table(b"a,b\n", ".csv")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProcessUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@example.com", "pass12345!")

    def test_csv_import_creates_dataset_customers_and_transactions(self):
        ds = process_upload(owner=self.user, upload=csv_upload(), name="Test set")
        self.assertEqual(ds.status, UploadedDataset.Status.READY)
        self.assertEqual(ds.name, "Test set")
        self.assertEqual(ds.raw_row_count, 15)
        self.assertEqual(ds.clean_row_count, 5)
        self.assertEqual(Transaction.objects.filter(dataset=ds).count(), 5)
        self.assertEqual(set(Customer.objects.filter(dataset=ds).values_list("external_id", flat=True)), {"17850", "13047", "14527"})

    def test_guest_lines_have_no_customer_and_cancellations_are_negative(self):
        ds = process_upload(owner=self.user, upload=csv_upload())
        self.assertEqual(Transaction.objects.filter(dataset=ds, customer__isnull=True).count(), 1)
        cancel = Transaction.objects.get(dataset=ds, is_cancellation=True)
        self.assertEqual(cancel.quantity, -1)
        self.assertLess(cancel.line_total, 0)

    def test_name_defaults_to_file_name(self):
        ds = process_upload(owner=self.user, upload=csv_upload(name="my_sales.csv"))
        self.assertEqual(ds.name, "my_sales")

    def test_original_and_cleaned_files_are_kept_separately(self):
        ds = process_upload(owner=self.user, upload=csv_upload())
        self.assertNotEqual(ds.original_file.name, ds.cleaned_file.name)
        self.assertIn("InvoiceNo", ds.original_file.read().decode())  # untouched headers
        cleaned_text = ds.cleaned_file.read().decode()
        self.assertTrue(cleaned_text.startswith("invoice_no,"))
        self.assertNotIn("not a date", cleaned_text)
        self.assertNotIn(" BAD", cleaned_text)

    def test_excel_import_handles_float_ids_and_real_dates(self):
        ds = process_upload(owner=self.user, upload=xlsx_upload())
        self.assertEqual(ds.clean_row_count, 3)
        self.assertTrue(Customer.objects.filter(dataset=ds, external_id="17850").exists())
        first = Transaction.objects.filter(dataset=ds).order_by("invoice_date").first()
        self.assertEqual((first.invoice_date.year, first.invoice_date.hour), (2010, 8))

    def test_two_datasets_do_not_mix(self):
        a = process_upload(owner=self.user, upload=csv_upload(), name="A")
        b = process_upload(owner=self.user, upload=csv_upload(), name="B")
        self.assertEqual(Customer.objects.filter(dataset=a).count(), 3)
        self.assertEqual(Customer.objects.filter(dataset=b).count(), 3)
        self.assertEqual(Transaction.objects.count(), 10)

    def test_preview_and_report_are_stored(self):
        ds = process_upload(owner=self.user, upload=csv_upload())
        self.assertEqual(ds.preview["columns"][0], "invoice_no")
        self.assertEqual(len(ds.preview["rows"]), 15)
        self.assertEqual(ds.quality_report["raw"]["rows"], 15)
        self.assertEqual(ds.quality_report["cleaning"]["rows_kept"], 5)
        self.assertEqual(ds.column_mapping["unit_price"], "UnitPrice")

    def test_nothing_usable_raises_and_saves_nothing(self):
        upload = csv_upload(rows=["536503,22002,BAD,1,not a date,2.00,17850,UK"])
        with self.assertRaises(DatasetImportError):
            process_upload(owner=self.user, upload=upload)
        self.assertEqual(UploadedDataset.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_database_failure_leaves_nothing_behind(self):
        from unittest import mock

        with mock.patch("analytics.services.data_import.persist", side_effect=RuntimeError("boom")):
            with self.assertRaises(DatasetImportError):
                process_upload(owner=self.user, upload=csv_upload())
        self.assertEqual(UploadedDataset.objects.count(), 0)
