import pandas as pd
from django.test import SimpleTestCase

from analytics.services import data_cleaning as dc
from analytics.services.csv_safety import sanitize_cell
from analytics.services.data_import import map_columns, read_table

from .helpers import BAD_ROWS, GOOD_ROWS, csv_text


def prepared(rows):
    raw = read_table(csv_text(rows).encode(), ".csv")
    mapped, _ = map_columns(raw)
    return dc.standardise_text(mapped)


class QualityReportTests(SimpleTestCase):
    def test_counts_each_problem(self):
        report = dc.build_quality_report(prepared(GOOD_ROWS + list(BAD_ROWS.values())))
        self.assertEqual(report["rows"], 15)
        self.assertEqual(report["duplicate_rows"], 1)
        self.assertEqual(report["invalid_dates"], 1)
        self.assertEqual(report["invalid_quantity"], 1)
        self.assertEqual(report["invalid_price"], 1)
        self.assertEqual(report["zero_price"], 1)
        self.assertEqual(report["negative_price"], 1)
        self.assertEqual(report["zero_quantity"], 1)
        self.assertEqual(report["negative_quantity_cancellations"], 1)
        self.assertEqual(report["negative_quantity_other"], 1)
        # the good "536400" row and the negative-price adjustment row have no customer
        self.assertEqual(report["missing_customer_id"], 2)

    def test_report_does_not_modify_the_data(self):
        df = prepared(GOOD_ROWS + list(BAD_ROWS.values()))
        before = df.copy()
        dc.build_quality_report(df)
        pd.testing.assert_frame_equal(df, before)


class CleaningRuleTests(SimpleTestCase):
    def setUp(self):
        self.result = dc.clean(prepared(GOOD_ROWS + list(BAD_ROWS.values())))
        self.dropped = self.result.report["cleaning"]["dropped"]

    def test_each_rule_removes_exactly_its_row(self):
        for rule in BAD_ROWS:
            with self.subTest(rule=rule):
                self.assertEqual(self.dropped[rule], 1)

    def test_good_rows_are_kept_and_counts_reconcile(self):
        cleaning = self.result.report["cleaning"]
        self.assertEqual(cleaning["rows_kept"], len(GOOD_ROWS))
        self.assertEqual(cleaning["rows_in"] - cleaning["rows_removed"], cleaning["rows_kept"])
        self.assertEqual(sum(self.dropped.values()), cleaning["rows_removed"])

    def test_cancellations_are_flagged_not_deleted(self):
        cleaned = self.result.cleaned
        cancel = cleaned[cleaned["is_cancellation"]]
        self.assertEqual(len(cancel), 1)
        self.assertEqual(cancel.iloc[0]["quantity"], -1)
        self.assertAlmostEqual(cancel.iloc[0]["line_total"], -27.5)
        self.assertEqual(self.result.report["clean"]["cancellation_rows"], 1)

    def test_missing_customer_rows_are_kept(self):
        self.assertEqual(self.result.report["clean"]["rows_without_customer"], 1)

    def test_customer_ids_lose_float_suffix(self):
        ids = set(self.result.cleaned["customer_id"].dropna())
        self.assertIn("13047", ids)
        self.assertNotIn("13047.0", ids)

    def test_line_total_is_quantity_times_price(self):
        row = self.result.cleaned.query("invoice_no == '536365' and stock_code == '85123A'").iloc[0]
        self.assertAlmostEqual(row["line_total"], 6 * 2.55)

    def test_dates_are_month_first_and_utc(self):
        first = self.result.cleaned.iloc[0]["invoice_date"]
        self.assertEqual((first.year, first.month, first.day, first.hour, first.minute), (2010, 12, 1, 8, 26))
        self.assertEqual(str(first.tzinfo), "UTC")

    def test_all_bad_input_gives_empty_result_not_crash(self):
        result = dc.clean(prepared(list(BAD_ROWS.values())[1:]))
        self.assertTrue(result.cleaned.empty)


class CsvSafetyTests(SimpleTestCase):
    def test_formula_prefixes_are_neutralised(self):
        for dangerous in ["=SUM(A1)", "+1+1", "-2+3", "@cmd", "\tTAB"]:
            with self.subTest(value=dangerous):
                self.assertTrue(sanitize_cell(dangerous).startswith("'"))

    def test_safe_values_are_untouched(self):
        for safe in ["WHITE HEART", "17850", "", 5, -3, None]:
            self.assertEqual(sanitize_cell(safe), safe)

    def test_cleaned_csv_export_sanitises_text_but_not_numbers(self):
        rows = GOOD_ROWS[:1] + ["536777,X1,=HYPERLINK(\"http://evil\"),-2,12/5/2010 9:00,1.50,17850,United Kingdom"]
        # a negative quantity without a C prefix is dropped, so use a cancellation for the numeric check
        rows.append("C536778,X2,@bad,-2,12/5/2010 9:00,1.50,17850,United Kingdom")
        result = dc.clean(prepared(rows))
        text = dc.cleaned_to_csv_bytes(result.cleaned).decode()
        self.assertIn("'@bad", text)
        self.assertNotIn(",@bad", text)
        self.assertIn(",-2,", text)  # the numeric quantity stays numeric
