#!/usr/bin/env python3
import os, sys
from datetime import datetime, timezone
import requests

TOKEN = os.environ.get("MARKETDATA_TOKEN", "").strip()
SYMBOL = os.environ.get("AUDIT_SYMBOL", "AAPL").strip().upper() or "AAPL"

if not TOKEN:
    print("ERROR: MARKETDATA_TOKEN is missing.")
    sys.exit(2)

url = f"https://api.marketdata.app/v1/options/chain/{SYMBOL}/"
params = {"side": "put", "dte": "7-45"}
headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "BCI-CSP-MarketData-Audit/1.0",
}

print("=" * 72)
print("MARKETDATA.APP OPTIONS AUDIT — BCI-CSP")
print("=" * 72)
print(f"Underlying: {SYMBOL}")
print(f"UTC run time: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
print("Token: present (not printed)")
print("Request: puts, DTE 7–45")
print()

r = requests.get(url, params=params, headers=headers, timeout=60)
print(f"HTTP status: {r.status_code}")
print(f"Final URL: {r.url}")

for k, v in r.headers.items():
    if any(x in k.lower() for x in ("credit", "rate", "limit", "usage", "remaining")):
        print(f"{k}: {v}")

if r.status_code not in (200, 203):
    print("API ERROR:")
    try:
        print(r.json())
    except Exception:
        print(r.text[:1500])
    sys.exit(4)

data = r.json()
print(f"API status field: {data.get('s')!r}")
if data.get("errmsg"):
    print("API errmsg:", data.get("errmsg"))

fields = [
    "optionSymbol","underlying","expiration","side","strike","dte","updated",
    "bid","ask","mid","openInterest","underlyingPrice","iv","delta"
]
lengths = {f: len(data[f]) for f in fields if isinstance(data.get(f), list)}
n = max(lengths.values()) if lengths else 0

print(f"Contracts returned: {n}")
if n == 0:
    print("AUDIT VERDICT: INCONCLUSIVE — no contracts returned.")
    sys.exit(0)

def at(field, i):
    arr = data.get(field)
    return arr[i] if isinstance(arr, list) and i < len(arr) else None

required = ["strike","expiration","bid","ask","openInterest","iv","delta"]

print("\nFIELD COVERAGE")
coverage = {}
for f in required:
    present = sum(at(f, i) is not None for i in range(n))
    coverage[f] = present
    print(f"{f:20s} {present:5d}/{n:<5d} {100*present/n:6.1f}%")

complete = sum(all(at(f, i) is not None for f in required) for i in range(n))
print(f"Complete rows: {complete}/{n} ({100*complete/n:.1f}%)")

cand = []
for i in range(n):
    d = at("delta", i)
    if isinstance(d, (int, float)) and 0.10 <= abs(d) <= 0.30:
        cand.append(i)

if cand:
    cand_complete = sum(all(at(f, i) is not None for f in required) for i in cand)
    print(f"Delta 0.10–0.30 rows: {len(cand)}; complete {cand_complete}/{len(cand)} ({100*cand_complete/len(cand):.1f}%)")
else:
    print("Delta 0.10–0.30 rows: 0")

print("\nPLAUSIBILITY")
quotes = [i for i in range(n)
          if isinstance(at("bid", i), (int,float)) and isinstance(at("ask", i), (int,float))]
if quotes:
    ask_ge_bid = sum(at("ask", i) >= at("bid", i) for i in quotes)
    valid = sum(at("bid", i) > 0 and at("ask", i) > at("bid", i) for i in quotes)
    print(f"Rows with bid+ask: {len(quotes)}")
    print(f"Ask >= Bid: {ask_ge_bid}/{len(quotes)} ({100*ask_ge_bid/len(quotes):.1f}%)")
    print(f"BCI valid quote Bid>0 & Ask>Bid: {valid}/{len(quotes)} ({100*valid/len(quotes):.1f}%)")
else:
    print("No bid+ask rows.")

deltas = [i for i in range(n) if isinstance(at("delta", i), (int,float))]
if deltas:
    in_bounds = sum(-1 <= at("delta", i) <= 0 for i in deltas)
    print(f"Put delta [-1,0]: {in_bounds}/{len(deltas)} ({100*in_bounds/len(deltas):.1f}%)")

updates = [at("updated", i) for i in range(n)]
updates = [x for x in updates if isinstance(x, (int,float))]
if updates:
    def fmt(ts):
        return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")
    print("\nSNAPSHOT TIMESTAMPS")
    print("Earliest:", fmt(min(updates)))
    print("Latest:  ", fmt(max(updates)))
    print("Distinct:", len(set(updates)))

sample = cand[0] if cand else 0
print("\nSANITIZED SAMPLE")
for f in ["optionSymbol","expiration","dte","strike","bid","ask","openInterest","underlyingPrice","iv","delta","updated"]:
    print(f"{f:18s}: {at(f, sample)!r}")

print("\nAUDIT VERDICT")
if complete > 0 and all(coverage[f] > 0 for f in ("bid","ask","openInterest","iv","delta")):
    print("PASS: all seven compulsory BCI-CSP fields are available on at least one row.")
else:
    print("FAIL/INCOMPLETE: required data are not sufficiently available.")
    missing = [f for f in required if coverage[f] == 0]
    if missing:
        print("Missing on every row:", ", ".join(missing))

print("\nThis audit tests only the data source and does not change BCI-CSP methodology.")
