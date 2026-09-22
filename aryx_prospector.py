"""
Aryx Prospector - Lead email extraction script.

Reads "Business OutReaches - Sheet1(7).csv", filters for eligible targets,
visits each business's website, extracts an email address, and writes
"Aryx_Prospector_Leads.csv" with Business Name / URL / Email columns.

No paid APIs are used - only pandas, requests, and BeautifulSoup4.
"""

import time

import pandas as pd

from scraper import normalize_url, scrape_email

# --- Config ---------------------------------------------------------------

INPUT_CSV = "Business OutReaches - Sheet1(7).csv"
OUTPUT_CSV = "Aryx_Prospector_Leads.csv"

NAME_COL = "Redstone Pizza"
URL_COL = "Website / URL"
STATUS_COL = "Status"

EXCLUDED_STATUSES = {"no deal", "awaiting response", "dead"}
INCLUDED_STATUS = "to contact"

REQUEST_DELAY_SECONDS = 1  # be polite between requests


def filter_eligible_rows(df: pd.DataFrame) -> pd.DataFrame:
    website = df[URL_COL].fillna("").astype(str).str.strip()
    has_website = website.ne("")
    not_no_website = website.str.lower() != "no website"

    status = df[STATUS_COL].fillna("").astype(str).str.strip().str.lower()
    is_blank_status = status.eq("")
    is_to_contact = status.eq(INCLUDED_STATUS)
    is_excluded = status.isin(EXCLUDED_STATUSES)

    status_ok = (is_to_contact | is_blank_status) & ~is_excluded

    return df[has_website & not_no_website & status_ok].copy()


def main():
    df = pd.read_csv(INPUT_CSV)

    eligible = filter_eligible_rows(df)
    print(f"Found {len(eligible)} eligible rows out of {len(df)} total rows.")

    results = []
    for i in range(1, len(eligible) + 1):
        business_name = eligible.iloc[i - 1][NAME_COL]
        raw_url = eligible.iloc[i - 1][URL_COL]
        url = normalize_url(raw_url)

        print(f"[{i}/{len(eligible)}] Scraping {business_name} -> {url}")
        email, error = scrape_email(url)
        if email:
            print(f"  -> Found: {email}")
        else:
            print(f"  -> No email found.{' (' + error + ')' if error else ''}")

        results.append({
            "Business Name": business_name,
            "URL": url,
            "Email": email,
        })

        time.sleep(REQUEST_DELAY_SECONDS)

    output_df = pd.DataFrame(results, columns=["Business Name", "URL", "Email"])
    output_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nDone. Wrote {len(output_df)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
