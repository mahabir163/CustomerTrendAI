from django.urls import path

from config.views import placeholder_view

app_name = "reports"

urlpatterns = [
    path(
        "",
        placeholder_view,
        {
            "title": "Reports",
            "phase": 7,
            "description": "Export filtered customers and download a summary report for a reporting period.",
        },
        name="index",
    ),
]
