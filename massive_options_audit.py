#!/usr/bin/env python3
import os, sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse
import requests

BASE = "https://api.massive.com"
API_KEY = os.environ.get("MASSIVE_API_KEY", "").strip()
SYMBOL = os.environ.get("AUDIT_SYMBOL", "AAPL").strip().upper() or "AAPL"

if not API_KEY:
    print("ERROR: Environment variable MASSIVE_API_KEY is missing.")
    sys.exit(2)

session = requests.Session()
session.headers.update({"User-Agent": "BCI-CSP-Massive-Audit/1.0"})

def safe_url(url):
    p = urlparse(url)
    q = [(k, "***") if k.lower() == "apikey" else (k, v)
         for k, v in parse_qsl(p.query, keep_blank_values=True)]
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), p.fragment))

def add_api_key(url):
    p = urlparse(url)
    q = parse_qsl(p.query, keep_blank_values=True)
    if not any(k.lower() == "apikey" for k, _ in q):
        q.append(("apiKey", API_KEY))
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), p.fragment))

def request_json(url, params=None):
    params = dict(params or {})
    params["apiKey"] = API_KEY
    r = session.get(url, params=params, timeout=30)
    print(f"HTTP {r.status_code}  {safe_url(r.url)}")
    try:
        data = r.json()
    except Exception:
        print("Non-JSON response:", r.text[:500])
        return r.status_code, None
    return r.status_code, data

def msg(data):
    if not isinstance(data, dict):
        return ""
    for k in ("message", "error", "status"):
        v = data.get(k)
        if isinstance(v, str) and v:
            return v
    return ""

def pct(n, d):
    return f"{(100*n/d):.1f}%" if d else "n/a"

print("=" * 72)
print("MASSIVE OPTIONS AUDIT — BCI-CSP")
print("=" * 72)
print(f"Underlying: {SYMBOL}")
print(f"UTC run time: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
print("API key: present (not printed)")
print()

print("[1/3] Authentication / reference endpoint")
status, data = request_json(
    f"{BASE}/v3/reference/options/contracts",
    {
        "underlying_ticker": SYMBOL,
        "contract_type": "put",
        "limit": 1,
        "order": "asc",
        "sort": "expiration_date",
    },
)
if status == 200 and isinstance(data, dict):
    results = data.get("results") or []
    print(f"Reference endpoint OK; results returned: {len(results)}")
    if results:
        d = results[0]
        print("Reference sample fields:",
              {k: d.get(k) for k in ("ticker","contract_type","strike_price","expiration_date")})
else:
    print("Reference endpoint not usable:", msg(data))
print()

print("[2/3] Option Chain Snapshot — required BCI-CSP data")
today = datetime.now(timezone.utc).date()
dte_min = today + timedelta(days=7)
dte_max = today + timedelta(days=45)

params = {
    "contract_type": "put",
    "expiration_date.gte": dte_min.isoformat(),
    "expiration_date.lte": dte_max.isoformat(),
    "limit": 250,
    "order": "asc",
    "sort": "expiration_date",
}

url = f"{BASE}/v3/snapshot/options/{SYMBOL}"
all_rows = []
pages = 0
chain_error = None

while url and pages < 20:
    if pages == 0:
        status, page = request_json(url, params)
    else:
        full = add_api_key(url if url.startswith("http") else urljoin(BASE, url))
        r = session.get(full, timeout=30)
        print(f"HTTP {r.status_code}  {safe_url(r.url)}")
        status = r.status_code
        try:
            page = r.json()
        except Exception:
            page = None

    if status != 200 or not isinstance(page, dict):
        chain_error = f"HTTP {status}"
        if isinstance(page, dict):
            chain_error += f" — {msg(page)}"
        break

    rows = page.get("results") or []
    all_rows.extend(rows)
    pages += 1
    url = page.get("next_url")
    if not url:
        break

if chain_error:
    print("\nCHAIN SNAPSHOT NOT AVAILABLE.")
    print("Reason returned by API:", chain_error)
    low = chain_error.lower()
    if any(x in low for x in ("upgrade", "subscription", "entitle", "plan", "not authorized", "forbidden")):
        print("Classification: likely PLAN/ENTITLEMENT restriction, not a script failure.")
    elif "401" in chain_error:
        print("Classification: authentication/key issue.")
    else:
        print("Classification: endpoint unavailable or other API error; inspect message above.")
else:
    print(f"\nChain snapshot OK: {len(all_rows)} contracts across {pages} page(s).")
    print(f"Requested expiration window: {dte_min} through {dte_max} (7–45 calendar days)")

    def get_nested(row, *path):
        cur = row
        for key in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    tests = {
        "strike": lambda r: get_nested(r, "details", "strike_price"),
        "expiration": lambda r: get_nested(r, "details", "expiration_date"),
        "bid": lambda r: get_nested(r, "last_quote", "bid"),
        "ask": lambda r: get_nested(r, "last_quote", "ask"),
        "open_interest": lambda r: r.get("open_interest"),
        "implied_volatility": lambda r: r.get("implied_volatility"),
        "delta": lambda r: get_nested(r, "greeks", "delta"),
    }

    total = len(all_rows)
    coverage = {}
    for name, fn in tests.items():
        vals = []
        for row in all_rows:
            try:
                vals.append(fn(row))
            except Exception:
                vals.append(None)
        present = sum(v is not None for v in vals)
        coverage[name] = (present, total)

    print("\nFIELD COVERAGE")
    print("-" * 52)
    for name, (present, total) in coverage.items():
        print(f"{name:20s} {present:5d}/{total:<5d}  {pct(present,total):>7s}")

    required = ["strike","expiration","bid","ask","open_interest","implied_volatility","delta"]
    complete_rows = sum(
        1 for row in all_rows
        if all(tests[k](row) is not None for k in required)
    )

    print("-" * 52)
    print(f"Rows complete for ALL 7 required fields: {complete_rows}/{total} ({pct(complete_rows,total)})")

    if all_rows:
        r = all_rows[0]
        sample = {
            "ticker": get_nested(r, "details", "ticker"),
            "strike": tests["strike"](r),
            "expiration": tests["expiration"](r),
            "bid": tests["bid"](r),
            "ask": tests["ask"](r),
            "open_interest": tests["open_interest"](r),
            "implied_volatility": tests["implied_volatility"](r),
            "delta": tests["delta"](r),
            "underlying_price": get_nested(r, "underlying_asset", "price"),
        }
        print("\nSanitized first-contract sample:")
        print(sample)

    print("\nAUDIT VERDICT")
    if total == 0:
        print("INCONCLUSIVE: endpoint works but returned no contracts in the requested 7–45 DTE window.")
    elif complete_rows > 0:
        print("PASS: Massive returned at least one option with every BCI-CSP compulsory field.")
        if complete_rows < total:
            print("NOTE: Some contracts have missing fields; use per-contract DATA_INCOMPLETE handling.")
    else:
        missing_everywhere = [k for k,(n,_) in coverage.items() if n == 0]
        print("FAIL/INCOMPLETE: no contract contained all compulsory fields.")
        print("Fields absent from every returned row:", ", ".join(missing_everywhere) or "none")
        print("This may be a plan entitlement issue rather than a Massive data-quality failure.")

print()
print("[3/3] Interpretation")
print("For development, delayed data are sufficient if bid/ask/OI/IV/delta are returned together")
print("for a consistent snapshot. Realtime is needed later for live trade execution.")
print("Keep the API key only in GitHub Actions Secrets.")
