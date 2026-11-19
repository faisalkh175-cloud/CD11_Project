import argparse
import csv
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("system", choices=["ayurveda", "siddha", "unani"])
parser.add_argument("code")
parser.add_argument("--release", default="2026-01")
args = parser.parse_args()

csv_path = Path(__file__).with_name("verified_mappings.csv")
required = {"system", "namaste_code", "icd11_code", "icd11_release", "source", "status"}
matches = []

try:
    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not required.issubset(reader.fieldnames or []):
            parser.exit(1, "Error: Check the CSV header.\n")

        for row in reader:
            if (
                (row["system"] or "").strip().casefold() == args.system
                and (row["namaste_code"] or "").strip().casefold() == args.code.strip().casefold()
                and (row["icd11_release"] or "").strip() == args.release
                and (row["status"] or "").strip().casefold() == "verified"
                and (row["icd11_code"] or "").strip()
                and (row["source"] or "").strip()
            ):
                matches.append(row)
except FileNotFoundError:
    parser.exit(1, "Error: Create verified_mappings.csv beside mapping.py.\n")

print(json.dumps({
    "status": "mapped" if matches else "no_verified_mapping",
    "matches": matches,
}, indent=2))
