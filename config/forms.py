"""Shared form helpers.

Django renders form widgets without any styling. Instead of repeating Tailwind
classes in every template, this mixin adds them to every widget once, so all
forms in the project look the same.
"""
from django import forms

INPUT_CLASSES = (
    "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm "
    "text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 "
    "focus:outline-none focus:ring-2 focus:ring-brand-500/30"
)
CHECKBOX_CLASSES = "h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
FILE_CLASSES = (
    "block w-full cursor-pointer rounded-lg border border-dashed border-slate-300 bg-slate-50 "
    "p-4 text-sm text-slate-600 file:mr-4 file:rounded-md file:border-0 file:bg-brand-600 "
    "file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-brand-700"
)


class TailwindFormMixin:
    """Adds Tailwind classes to every widget when the form is created."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = CHECKBOX_CLASSES
            elif isinstance(widget, forms.FileInput):
                css = FILE_CLASSES
            else:
                css = INPUT_CLASSES
            widget.attrs["class"] = f'{widget.attrs.get("class", "")} {css}'.strip()
