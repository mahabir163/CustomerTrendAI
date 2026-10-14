"""Thin views: read the request, call a service, render a template.

All views are private by default (LoginRequiredMiddleware). Every dataset lookup
filters on `owner=request.user`, so another user's dataset returns 404, exactly
as if it did not exist.
"""
from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST

from .forms import DatasetUploadForm
from .models import UploadedDataset
from .services import data_cleaning
from .services.data_import import DatasetImportError, process_upload


def _own_dataset(request, pk: int) -> UploadedDataset:
    return get_object_or_404(UploadedDataset, pk=pk, owner=request.user)


def overview(request):
    """Overview dashboard.

    Until Phase 3 this shows an honest empty state or a pointer to the user's
    datasets. No sample numbers are ever displayed.
    """
    datasets = request.user.datasets.filter(status=UploadedDataset.Status.READY)
    return render(
        request,
        "analytics/overview.html",
        {"page_title": "Overview", "datasets": datasets[:5], "dataset_count": datasets.count()},
    )


@require_http_methods(["GET", "POST"])
def upload(request):
    form = DatasetUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            dataset = process_upload(
                owner=request.user,
                upload=form.cleaned_data["file"],
                name=form.cleaned_data["name"],
            )
        except DatasetImportError as exc:
            form.add_error("file", str(exc))
        else:
            messages.success(
                request,
                f"“{dataset.name}” imported: {dataset.clean_row_count:,} of {dataset.raw_row_count:,} rows kept.",
            )
            return redirect(dataset)
    return render(
        request,
        "analytics/upload.html",
        {"page_title": "Data Upload", "form": form, "datasets": request.user.datasets.all()},
    )


def dataset_detail(request, pk: int):
    dataset = _own_dataset(request, pk)
    report = dataset.quality_report
    return render(
        request,
        "analytics/dataset_detail.html",
        {
            "page_title": dataset.name,
            "dataset": dataset,
            "report": report,
            "issues": data_cleaning.describe_quality_issues(report),
            "dropped": data_cleaning.describe_dropped(report),
            "rules": data_cleaning.CLEANING_RULES,
            "mapping": dataset.column_mapping.items(),
        },
    )


def dataset_download(request, pk: int, kind: str):
    """Download the original upload or the cleaned CSV (owner only)."""
    dataset = _own_dataset(request, pk)
    if kind == "cleaned":
        stored, filename = dataset.cleaned_file, f"{slugify(dataset.name) or 'dataset'}_cleaned.csv"
    elif kind == "original":
        stored, filename = dataset.original_file, dataset.original_filename
    else:
        return redirect(dataset)
    return FileResponse(stored.open("rb"), as_attachment=True, filename=filename)


@require_POST
def dataset_delete(request, pk: int):
    dataset = _own_dataset(request, pk)
    name = dataset.name
    dataset.delete_files()
    dataset.delete()
    messages.success(request, f"“{name}” and all of its data were deleted.")
    return redirect("analytics:upload")
