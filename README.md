# CustomerTrend AI

Customer Trend Intelligence & Analytics Platform (Django, Pandas, Scikit-learn, Chart.js, Tailwind CSS, LLM assistant).

Status: **Phase 2 of 7** complete (project setup, accounts, dataset upload, cleaning and data-quality report).

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
```

Build the CSS (download `tailwindcss-windows-x64.exe` from the Tailwind CSS GitHub releases into `tools\`):

```powershell
.\tools\tailwindcss-windows-x64.exe -i .\static\src\input.css -o .\static\css\tailwind.css --watch
```

In a second terminal: `python manage.py runserver` and open http://127.0.0.1:8000/

## Using it (Phase 2)

1. Register at `/account/register/` (or `python manage.py createsuperuser`), then sign in.
2. Download the UCI *Online Retail* dataset from the UCI Machine Learning Repository (dataset 352) and unzip it. It is an Excel file, `Online Retail.xlsx` (~540,000 rows).
3. Open **Data Upload**, choose the file and upload. Excel files take roughly 2 minutes at that size; keep the page open.
4. You land on the dataset page: data-quality report, rows removed per rule, the rules themselves, column mapping, a preview, and downloads for the original and cleaned files.

No internet or dataset yet? Generate a **synthetic** file in the same layout (not real data, for testing only):

```powershell
python scripts\generate_sample_retail.py --rows 50000 --out sample_retail.csv
```

### Security notes

- Every page requires login by default (`LoginRequiredMiddleware`); only login, register and password reset are exempt.
- Datasets are scoped to their owner. Another user's dataset returns 404.
- Uploads are validated for extension, size, real file content and required columns. Uploaded files are stored under random folder names and are never served from `/media/`.
- Text in downloaded CSVs is protected against spreadsheet formula injection.
- Set `ALLOW_REGISTRATION=False` to close public sign-up on a deployed instance.

### Data cleaning rules

The exact rules are shown on every dataset page and defined in `analytics/services/data_cleaning.py` (`CLEANING_RULES`). In short: rows with no invoice number, exact duplicates, invalid quantity/price/date, zero quantity, zero or negative price, and negative quantities that are *not* cancellations are removed. **Cancellations** (invoice starts with `C`) and rows with **no customer ID** are kept and flagged, not deleted. Each removed row is counted once, under the first rule that removed it.

### Known limits

Import runs inside the web request (about 70 s for 540k CSV rows, ~2 min for the Excel file, ~570 MB RAM). Fine for local use; moving it to a background worker is planned for Phase 7.

## Tests

```powershell
python manage.py test
```

## Troubleshooting

- **Template edits don't show up:** Django caches templates. Run `runserver` without `--noreload` (the default) so it restarts on changes, or restart it by hand.
- **A Tailwind class has no effect:** keep the Tailwind CLI running (or re-run it once) after adding new classes to templates.
