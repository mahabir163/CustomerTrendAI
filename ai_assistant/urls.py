from django.urls import path

from config.views import placeholder_view

app_name = "ai_assistant"

urlpatterns = [
    path(
        "",
        placeholder_view,
        {
            "title": "AI Business Assistant",
            "phase": 5,
            "description": "Ask business questions in plain language. Answers are grounded in metrics calculated from your data.",
        },
        name="chat",
    ),
]
