from django import forms

from config.forms import TailwindFormMixin

from .services.data_import import DatasetImportError, validate_upload_file


class DatasetUploadForm(TailwindFormMixin, forms.Form):
    name = forms.CharField(
        max_length=120,
        required=False,
        help_text="Optional. Defaults to the file name.",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Online Retail 2010-2011"}),
    )
    file = forms.FileField(
        label="Dataset file",
        help_text="CSV or Excel (.xlsx). Required columns: invoice number, stock code, quantity, invoice date, unit price, customer ID.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        try:
            validate_upload_file(upload)
        except DatasetImportError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return upload
