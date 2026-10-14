"""Database models.

Three tables hold everything a dataset contains:

    UploadedDataset  one uploaded file (owner, status, quality report)
        |-- Customer     one row per customer *within that dataset*
        |-- Transaction  one row per invoice line *within that dataset*

Every Customer and Transaction points at its dataset, and every query in later
phases filters on `dataset`. That is what keeps two uploads from mixing, and
`owner` on the dataset is what keeps two users from seeing each other's data.
"""
import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import reverse


def _dataset_dir(instance) -> str:
    # Folder name comes from a random UUID, never from user-supplied text.
    return f"datasets/{instance.owner_id}/{instance.storage_key.hex}"


def original_upload_path(instance, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"{_dataset_dir(instance)}/original{suffix}"


def cleaned_upload_path(instance, filename: str) -> str:
    return f"{_dataset_dir(instance)}/cleaned.csv"


class UploadedDataset(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="datasets"
    )
    name = models.CharField(max_length=120)
    storage_key = models.UUIDField(default=uuid.uuid4, editable=False)
    original_filename = models.CharField(max_length=255)
    # The untouched upload is preserved; the cleaned copy is a separate file.
    original_file = models.FileField(upload_to=original_upload_path, max_length=255)
    cleaned_file = models.FileField(upload_to=cleaned_upload_path, max_length=255, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    error_message = models.TextField(blank=True)

    raw_row_count = models.PositiveIntegerField(default=0)
    clean_row_count = models.PositiveIntegerField(default=0)
    column_mapping = models.JSONField(default=dict, blank=True)  # internal name -> original header
    preview = models.JSONField(default=dict, blank=True)  # first rows of the raw upload
    quality_report = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.owner})"

    def get_absolute_url(self) -> str:
        return reverse("analytics:dataset_detail", args=[self.pk])

    @property
    def is_ready(self) -> bool:
        return self.status == self.Status.READY

    def delete_files(self) -> None:
        """Remove this dataset's folder from disk (original + cleaned file)."""
        folder = Path(settings.MEDIA_ROOT) / _dataset_dir(self)
        shutil.rmtree(folder, ignore_errors=True)


class Customer(models.Model):
    """A customer inside one dataset. `external_id` is the ID from the file."""

    dataset = models.ForeignKey(UploadedDataset, on_delete=models.CASCADE, related_name="customers")
    external_id = models.CharField(max_length=64)
    country = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dataset", "external_id"], name="uniq_customer_per_dataset")
        ]

    def __str__(self) -> str:
        return self.external_id


class Transaction(models.Model):
    """One invoice line (a product on an invoice).

    `customer` is NULL for lines with no customer ID (guest checkouts). They
    still count towards revenue and orders but cannot be attributed to a
    customer, so RFM and customer metrics skip them.
    """

    dataset = models.ForeignKey(UploadedDataset, on_delete=models.CASCADE, related_name="transactions")
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, null=True, blank=True, related_name="transactions"
    )
    invoice_no = models.CharField(max_length=32)
    stock_code = models.CharField(max_length=40)
    description = models.CharField(max_length=255, blank=True)
    quantity = models.IntegerField()
    invoice_date = models.DateTimeField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    line_total = models.DecimalField(max_digits=16, decimal_places=4)  # quantity * unit_price
    country = models.CharField(max_length=80, blank=True)
    # True for cancellation/return lines (invoice number starts with "C").
    # Their quantity and line_total are negative.
    is_cancellation = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["dataset", "invoice_date"]),
            models.Index(fields=["dataset", "customer"]),
            models.Index(fields=["dataset", "invoice_no"]),
            models.Index(fields=["dataset", "stock_code"]),
            models.Index(fields=["dataset", "country"]),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_no} / {self.stock_code}"
