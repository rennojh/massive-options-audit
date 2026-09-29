#!/usr/bin/env python3
"""
Audit Massive Options Flat Files access and schema without downloading whole datasets.

Required env vars:
  MASSIVE_S3_ACCESS_KEY
  MASSIVE_S3_SECRET_KEY

It checks the four documented OPRA option flat-file datasets:
  day_aggs_v1, minute_aggs_v1, trades_v1, quotes_v1

For each accessible dataset it:
- lists objects,
- finds the newest CSV.GZ,
- streams only enough data to read the header + a few rows,
- reports the exact columns,
- checks whether BCI-CSP-required fields appear.

No credentials are printed.
"""

import csv
import gzip
import io
import os
import sys
from botocore.config import Config
import boto3
from botocore.exceptions import ClientError

ENDPOINT = "https://files.massive.com"
BUCKET = "flatfiles"

ACCESS = os.environ.get("MASSIVE_S3_ACCESS_KEY", "").strip()
SECRET = os.environ.get("MASSIVE_S3_SECRET_KEY", "").strip()

if not ACCESS or not SECRET:
    print("ERROR: Missing MASSIVE_S3_ACCESS_KEY or MASSIVE_S3_SECRET_KEY.")
    sys.exit(2)

session = boto3.Session(
    aws_access_key_id=ACCESS,
    aws_secret_access_key=SECRET,
)

s3 = session.client(
    "s3",
    endpoint_url=ENDPOINT,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

datasets = {
    "day_aggregates": "us_options_opra/day_aggs_v1/",
    "minute_aggregates": "us_options_opra/minute_aggs_v1/",
    "trades": "us_options_opra/trades_v1/",
    "quotes": "us_options_opra/quotes_v1/",
}

required = {
    "strike": {"strike", "strike_price"},
    "expiration": {"expiration", "expiration_date"},
    "bid": {"bid", "bid_price"},
    "ask": {"ask", "ask_price"},
    "open_interest": {"open_interest", "oi"},
    "implied_volatility": {"implied_volatility", "iv"},
    "delta": {"delta"},
}

def latest_csv_key(prefix):
    paginator = s3.get_paginator("list_objects_v2")
    newest = None
    newest_dt = None
    count = 0
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".csv.gz"):
                continue
            count += 1
            lm = obj.get("LastModified")
            if newest is None or (lm is not None and (newest_dt is None or lm > newest_dt)):
                newest = key
                newest_dt = lm
    return newest, count, newest_dt

def read_head_gzip(key, max_lines=5):
    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
    gz = gzip.GzipFile(fileobj=body)
    txt = io.TextIOWrapper(gz, encoding="utf-8", newline="")
    rows = []
    for _ in range(max_lines):
        line = txt.readline()
        if not line:
            break
        rows.append(line.rstrip("\n"))
    try:
        txt.detach()
    except Exception:
        pass
    try:
        body.close()
    except Exception:
        pass
    return rows

print("=" * 78)
print("MASSIVE OPTIONS FLAT FILES AUDIT — BCI-CSP")
print("=" * 78)
print("S3 credentials: present (not printed)")
print(f"Endpoint: {ENDPOINT}")
print(f"Bucket: {BUCKET}")
print()

accessible = 0

for label, prefix in datasets.items():
    print(f"\n[{label}] {prefix}")
    print("-" * 78)
    try:
        key, count, modified = latest_csv_key(prefix)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "UNKNOWN")
        msg = e.response.get("Error", {}).get("Message", "")
        print(f"ACCESS ERROR: {code} — {msg}")
        continue
    except Exception as e:
        print(f"ERROR while listing: {type(e).__name__}: {e}")
        continue

    print(f"CSV.GZ objects visible: {count}")
    if not key:
        print("No downloadable CSV.GZ found.")
        continue

    print(f"Newest visible file: {key}")
    if modified:
        print(f"Last modified: {modified.isoformat()}")

    try:
        lines = read_head_gzip(key, max_lines=4)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "UNKNOWN")
        msg = e.response.get("Error", {}).get("Message", "")
        print(f"DOWNLOAD/READ ERROR: {code} — {msg}")
        continue
    except Exception as e:
        print(f"READ ERROR: {type(e).__name__}: {e}")
        continue

    if not lines:
        print("File readable but empty.")
        continue

    accessible += 1
    header = next(csv.reader([lines[0]]))
    normalized = {h.strip().lower() for h in header}
    print("Columns:")
    print(", ".join(header))

    print("\nBCI-CSP REQUIRED FIELD CHECK")
    for logical, aliases in required.items():
        hit = sorted(normalized.intersection(aliases))
        print(f"{logical:20s}: {'YES — ' + ', '.join(hit) if hit else 'NO'}")

    print("\nFirst data row (sanitized market data only):")
    if len(lines) > 1:
        print(lines[1][:1000])
    else:
        print("(none)")

print("\n" + "=" * 78)
print("FINAL")
print("=" * 78)
if accessible:
    print(f"Readable option flat-file datasets: {accessible}/{len(datasets)}")
else:
    print("No option flat-file dataset could be read.")

print("""
Interpretation:
- Flat Files are useful for bulk historical raw market data.
- They can only replace the Chain Snapshot for BCI-CSP if the actual file columns
  contain ALL fields we require.
- In particular, inspect whether implied_volatility, delta and open_interest exist.
- Missing fields here are a dataset-schema limitation, not a script failure.
""")
