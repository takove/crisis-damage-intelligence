#!/usr/bin/env python3
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR884"
BASE = Path(__file__).resolve().parent
STATE = BASE / "emsr884_monitor_state.json"
LOG = BASE / "emsr884_monitor_log.csv"
DOWNLOADS = BASE / "emsr884_downloads"
DOWNLOADS.mkdir(exist_ok=True)


STATUS_MEANING = {
    "F": "Final/downloadable",
    "I": "In production",
    "W": "Waiting",
    "N": "Not produced/not available",
}

CRITICAL_AOIS = {
    12: "La Guaira / Caraballeda coastal damage gap",
    7: "Puerto Cabello pending damage assessment",
    1: "Petare pending damage assessment",
    8: "San Felipe pending damage assessment",
    9: "Valencia pending damage assessment",
}


def fetch_activation():
    return json.loads(urlopen(API, timeout=45).read().decode("utf-8"))["results"][0]


def row_for(aoi, product, checked_at):
    images = []
    for image in product.get("images", []):
        images.append(
            " ".join(
                str(x)
                for x in [
                    image.get("sensorName") or "unknown_sensor",
                    image.get("acquisitionTime") or "unknown_time",
                    image.get("fileName") or "",
                ]
                if x
            )
        )
    return {
        "checked_at_utc": checked_at,
        "aoi_number": aoi["number"],
        "aoi_name": aoi["name"],
        "critical_reason": CRITICAL_AOIS.get(aoi["number"], ""),
        "product_type": product["type"],
        "status": product["version"]["statusCode"],
        "status_meaning": STATUS_MEANING.get(product["version"]["statusCode"], "Unknown"),
        "delivery_time": product["version"].get("deliveryTime") or "",
        "expected_delivery": product.get("expectedDelivery") or "",
        "download_path": product.get("downloadPath") or "",
        "images": " ; ".join(images),
    }


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"seen_downloads": [], "last_status": {}}


def save_state(state):
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True))


def append_log(rows):
    exists = LOG.exists()
    fields = [
        "checked_at_utc",
        "aoi_number",
        "aoi_name",
        "critical_reason",
        "product_type",
        "status",
        "status_meaning",
        "delivery_time",
        "expected_delivery",
        "download_path",
        "images",
    ]
    with LOG.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def download_new(row, state):
    url = row["download_path"]
    if not url or url in state["seen_downloads"]:
        return None
    name = f"AOI{int(row['aoi_number']):02d}_{row['aoi_name'].replace(' ', '_')}_{row['product_type']}_latest.zip"
    target = DOWNLOADS / name
    subprocess.run(["curl", "-L", "--fail", "--retry", "2", "-o", str(target), url], check=True)
    state["seen_downloads"].append(url)
    return str(target)


def main():
    checked_at = datetime.now(timezone.utc).isoformat()
    activation = fetch_activation()
    state = load_state()
    rows = []
    downloaded = []
    changes = []

    for aoi in activation["aois"]:
        for product in aoi.get("products", []):
            row = row_for(aoi, product, checked_at)
            rows.append(row)
            key = f"AOI{row['aoi_number']:02d}:{row['product_type']}:{product['id']}"
            prev = state["last_status"].get(key)
            current = row["status"]
            if prev and prev != current:
                changes.append(f"{key} {prev}->{current} {row['aoi_name']}")
            state["last_status"][key] = current
            if row["download_path"]:
                downloaded_path = download_new(row, state)
                if downloaded_path:
                    downloaded.append(downloaded_path)

    append_log(rows)
    save_state(state)

    print(f"Checked EMSR884 at {checked_at}")
    if changes:
        print("Status changes:")
        for change in changes:
            print(f"  {change}")
    else:
        print("No status changes since last saved state.")
    if downloaded:
        print("New downloads:")
        for path in downloaded:
            print(f"  {path}")
    else:
        print("No new downloadable products.")

    print("Critical AOIs:")
    for row in rows:
        if row["critical_reason"]:
            print(
                f"  AOI{int(row['aoi_number']):02d} {row['aoi_name']}: "
                f"{row['status']} {row['status_meaning']} expected={row['expected_delivery']}"
            )


if __name__ == "__main__":
    main()
