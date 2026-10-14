from django.urls import path

from config.views import placeholder_view

from . import views

app_name = "analytics"


def _placeholder(route, name, title, phase, description):
    return path(route, placeholder_view, {"title": title, "phase": phase, "description": description}, name=name)


urlpatterns = [
    path("", views.overview, name="overview"),
    _placeholder(
        "customers/", "customers", "Customer Analytics", 3,
        "Customer table with search, sorting, pagination and filters.",
    ),
    _placeholder(
        "trends/", "trends", "Trend Analysis", 3,
        "Month-over-month revenue, orders, average order value and product trends.",
    ),
    _placeholder(
        "segments/", "segments", "Customer Segments", 4,
        "RFM segmentation with configurable thresholds and retention recommendations.",
    ),
    # Data upload (Phase 2)
    path("upload/", views.upload, name="upload"),
    path("datasets/<int:pk>/", views.dataset_detail, name="dataset_detail"),
    path("datasets/<int:pk>/download/<str:kind>/", views.dataset_download, name="dataset_download"),
    path("datasets/<int:pk>/delete/", views.dataset_delete, name="dataset_delete"),
]
