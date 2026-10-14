import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from analytics.context_processors import NAV_ITEMS
from analytics.models import Transaction, UploadedDataset
from analytics.services.data_import import process_upload

from .helpers import csv_upload

User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class UploadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@example.com", "pass12345!")
        self.client.force_login(self.user)

    def test_upload_page_renders(self):
        response = self.client.get(reverse("analytics:upload"))
        self.assertContains(response, "Upload a dataset")
        self.assertContains(response, "No datasets yet")

    def test_successful_upload_redirects_to_report(self):
        response = self.client.post(reverse("analytics:upload"), {"name": "Retail", "file": csv_upload()}, follow=True)
        dataset = UploadedDataset.objects.get()
        self.assertRedirects(response, dataset.get_absolute_url())
        self.assertContains(response, "Data quality report")
        self.assertContains(response, "Cleaning rules applied")
        self.assertContains(response, "imported: 5 of 15 rows kept")
        self.assertEqual(dataset.owner, self.user)

    def test_wrong_file_type_shows_form_error_and_saves_nothing(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("notes.txt", b"hello")
        response = self.client.post(reverse("analytics:upload"), {"file": bad})
        self.assertContains(response, "Unsupported file type")
        self.assertEqual(UploadedDataset.objects.count(), 0)

    def test_missing_columns_shows_meaningful_error(self):
        upload = csv_upload(rows=["1,A,2"], header="InvoiceNo,StockCode,Quantity")
        response = self.client.post(reverse("analytics:upload"), {"file": upload})
        self.assertContains(response, "Missing required column")
        self.assertEqual(UploadedDataset.objects.count(), 0)

    def test_no_file_is_rejected(self):
        response = self.client.post(reverse("analytics:upload"), {"name": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadedDataset.objects.count(), 0)

    def test_download_cleaned_and_original(self):
        dataset = process_upload(owner=self.user, upload=csv_upload(), name="Retail Q1")
        cleaned = self.client.get(reverse("analytics:dataset_download", args=[dataset.pk, "cleaned"]))
        self.assertEqual(cleaned.status_code, 200)
        self.assertIn("attachment", cleaned["Content-Disposition"])
        self.assertIn("retail-q1_cleaned.csv", cleaned["Content-Disposition"])
        self.assertTrue(b"".join(cleaned.streaming_content).startswith(b"invoice_no,"))
        original = self.client.get(reverse("analytics:dataset_download", args=[dataset.pk, "original"]))
        self.assertTrue(b"".join(original.streaming_content).startswith(b"InvoiceNo,"))

    def test_delete_removes_rows_and_files(self):
        from pathlib import Path

        dataset = process_upload(owner=self.user, upload=csv_upload())
        path = Path(dataset.original_file.path)
        self.assertTrue(path.exists())
        response = self.client.post(reverse("analytics:dataset_delete", args=[dataset.pk]), follow=True)
        self.assertRedirects(response, reverse("analytics:upload"))
        self.assertEqual(UploadedDataset.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertFalse(path.exists())

    def test_delete_requires_post(self):
        dataset = process_upload(owner=self.user, upload=csv_upload())
        response = self.client.get(reverse("analytics:dataset_delete", args=[dataset.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(UploadedDataset.objects.count(), 1)

    def test_overview_lists_ready_datasets(self):
        process_upload(owner=self.user, upload=csv_upload(), name="Retail")
        response = self.client.get(reverse("analytics:overview"))
        self.assertContains(response, "Your data is ready")
        self.assertContains(response, "Retail")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AccessControlTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", "pass12345!")
        self.bob = User.objects.create_user("bob", "bob@example.com", "pass12345!")
        self.dataset = process_upload(owner=self.alice, upload=csv_upload(), name="Alice private")

    def urls(self):
        pk = self.dataset.pk
        return [
            reverse("analytics:dataset_detail", args=[pk]),
            reverse("analytics:dataset_download", args=[pk, "cleaned"]),
            reverse("analytics:dataset_download", args=[pk, "original"]),
        ]

    def test_anonymous_users_are_sent_to_login_everywhere(self):
        paths = self.urls() + [reverse(i.url_name) for i in NAV_ITEMS] + [reverse("analytics:dataset_delete", args=[self.dataset.pk])]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("accounts:login")))

    def test_other_users_get_404_not_403(self):
        self.client.force_login(self.bob)
        for path in self.urls():
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_other_user_cannot_delete(self):
        self.client.force_login(self.bob)
        response = self.client.post(reverse("analytics:dataset_delete", args=[self.dataset.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(UploadedDataset.objects.filter(pk=self.dataset.pk).exists())

    def test_other_users_do_not_see_the_dataset_listed(self):
        self.client.force_login(self.bob)
        self.assertNotContains(self.client.get(reverse("analytics:upload")), "Alice private")
        self.assertNotContains(self.client.get(reverse("analytics:overview")), "Alice private")

    def test_owner_can_see_it(self):
        self.client.force_login(self.alice)
        self.assertContains(self.client.get(self.urls()[0]), "Alice private")

    def test_media_files_are_not_served_publicly(self):
        self.client.force_login(self.alice)
        response = self.client.get("/media/" + self.dataset.original_file.name)
        self.assertEqual(response.status_code, 404)

    def test_unknown_download_kind_redirects_safely(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("analytics:dataset_download", args=[self.dataset.pk, "bogus"]))
        self.assertRedirects(response, self.dataset.get_absolute_url())

    def test_path_traversal_in_download_kind_never_serves_files(self):
        self.client.force_login(self.alice)
        for kind in ["..%2F..%2Fetc%2Fpasswd", "../../etc/passwd"]:
            with self.subTest(kind=kind):
                response = self.client.get(f"/datasets/{self.dataset.pk}/download/{kind}/")
                self.assertIn(response.status_code, (301, 302, 404))
                self.assertNotContains(response, "root:", status_code=response.status_code)
