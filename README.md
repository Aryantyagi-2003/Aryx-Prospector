# Aryx Prospector

A local lead-generation tool: upload any CSV of businesses, map its columns,
filter to eligible rows, and scrape each business's website for a contact
email — no paid APIs involved.

## Setup

```bash
pip install -r requirements.txt
```

## Run the web app

```bash
python3 app.py
```

Then open **http://127.0.0.1:5000** in your browser.

1. Upload a CSV.
2. Map the Business Name and Website/URL columns (and optionally a Status
   column, with checkboxes to include/exclude specific status values and
   blank statuses).
3. Click **Start scraping** and watch live progress.
4. Download `Aryx_Prospector_Leads.csv` when it finishes.

Your uploaded CSVs and generated results stay in the local `uploads/` and
`outputs/` folders and are never committed to git (see `.gitignore`).

## Run the CLI version instead

`aryx_prospector.py` is a standalone script with the same scraping logic,
hard-coded to read `Business OutReaches - Sheet1(7).csv` from this folder:

```bash
python3 aryx_prospector.py
```

## How email extraction works

For each eligible site:
1. Fetches the homepage with a 5s connect / 10s read timeout, a standard
   browser User-Agent, and `verify=False` to tolerate bad SSL certs.
2. Looks for `mailto:` links first.
3. Falls back to a regex scan of the visible page text, filtering out
   image-filename false positives (`.png`, `.jpg`, `.webp`, etc.).
