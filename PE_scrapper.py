"""
Fixed/modernized version of naveen7v/PE-ratio's PE_scrapper.py.

MoneyControl's Terms of Use (https://www.moneycontrol.com/cdata/termsofuse.php)
explicitly prohibit automated scraping/bots without prior written permission.
This is a technical fix to the existing repo's broken approach, not a
statement that this use is permitted - get written permission from
MoneyControl, or use an official/licensed data source, before any real or
production use.

What changed from the original and why:
  1. Two real syntax errors fixed: `stock_list.items` -> `stock_list.items()`,
     `count+ = 1` -> `count += 1`.
  2. The hardcoded 40-company dict of guessed URL slugs is replaced by
     MoneyControl's own search API (api.moneycontrol.com/mcapi/v1/stock/search),
     which resolves a company name/symbol to its real internal code ("did").
     A search can return several similarly-named companies (e.g. searching
     "reliance" also returns Reliance Chemotex, Reliance Communications,
     Reliance Infra on BSE) - this picks the entry whose full_name/short_name
     best matches the query, not just the first result.
  3. The old regex scrape ("find a line containing 'P/E', parse the next
     line for a number") no longer matches MoneyControl's current page and
     is replaced with direct lookup of `id="{did}_<fieldname>"` HTML elements,
     confirmed against a real fetched page.
  4. Confirmed empirically: the URL's descriptive path segments (e.g.
     "refineries/relianceindustries") don't need to be correct - MoneyControl
     redirects any slug to the canonical URL as long as the trailing `did` is
     right, so this script never needs to guess a slug.
"""
import csv
import os
import re
import time
from datetime import date

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

SEARCH_URL = "https://api.moneycontrol.com/mcapi/v1/stock/search"
QUOTE_URL = "https://www.moneycontrol.com/india/stockpricequote/x/x/{did}"

FIELDS = ["companyName", "lastPrice", "perChange", "marketCap",
          "scTtm", "priceBook", "roe", "debtEquity", "netProfit", "netSales"]
# scTtm = Stock P/E (TTM), priceBook = P/B ratio

CSV_HEADER = ["date", "query", "did"] + FIELDS


def resolve_did(query, session=None):
    """Look up a company name/symbol via MoneyControl's search API and return
    its internal 'did' code, or None if no confident match is found."""
    s = session or requests
    try:
        r = s.get(SEARCH_URL, params={"query": query, "type": "all"}, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])
    except (requests.RequestException, ValueError):
        return None

    if not data:
        return None

    q = query.strip().lower()
    # exact (case-insensitive) match on full_name or short_name first
    for item in data:
        if item.get("full_name", "").strip().lower() == q or item.get("short_name", "").strip().lower() == q:
            return item["did"]
    # otherwise the closest substring match - prefer full_name starting with the query
    for item in data:
        if item.get("full_name", "").strip().lower().startswith(q):
            return item["did"]
    return None


def fetch_fundamentals(did, session=None):
    """Fetch a company's MoneyControl page by did and extract the confirmed
    id="{did}_<fieldname>" fields. Returns a dict of field -> float|None."""
    s = session or requests
    url = QUOTE_URL.format(did=did)
    r = s.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    html = r.text
    return parse_fundamentals(html, did)


def parse_fundamentals(html, did):
    result = {}
    for field in FIELDS:
        m = re.search(rf'id="{re.escape(did)}_{field}"[^>]*>([^<]*)<', html)
        if not m:
            result[field] = None
            continue
        raw = m.group(1).strip()
        if field == "companyName":
            result[field] = raw or None
            continue
        cleaned = raw.replace(",", "")
        try:
            result[field] = float(cleaned)
        except ValueError:
            result[field] = None
    return result


def main(stock_queries, out_csv_path="moneycontrol_fundamentals.csv", sleep_between=0.5):
    today = str(date.today())
    write_header = not os.path.exists(out_csv_path)
    session = requests.Session()

    with open(out_csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(CSV_HEADER)

        for query in stock_queries:
            did = resolve_did(query, session=session)
            if did is None:
                print(f"[skip] no confident match for '{query}'")
                continue
            try:
                data = fetch_fundamentals(did, session=session)
            except requests.RequestException as e:
                print(f"[failed] {query} ({did}): {e}")
                continue
            row = [today, query, did] + [data.get(f) for f in FIELDS]
            writer.writerow(row)
            print(f"[ok] {query} -> {did}: P/E={data.get('scTtm')}, P/B={data.get('priceBook')}")
            time.sleep(sleep_between)


if __name__ == "__main__":
    # Example list - replace with whatever companies you want, searched by name or symbol
    stock_queries = ["Reliance Industries", "TCS", "HDFC Bank", "Infosys"]
    main(stock_queries)
