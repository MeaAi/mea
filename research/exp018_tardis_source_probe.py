#!/usr/bin/env python3
"""EXP-018: probe Tardis public L2/trade files for actual MEAFLOW-72 OOS orders.

Only a 4 KiB ranged prefix is requested per file. No raw market data is saved
or committed. This is source-availability QA, not an execution or PnL result.
"""
import json, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://datasets.tardis.dev/v1/binance-futures"
EVENTS = {
    "2025-10-01": ["ADAUSDT", "SOLUSDT", "TRXUSDT", "XRPUSDT"],
    "2026-02-01": ["BTCUSDT", "ETHUSDT", "LINKUSDT"],
    "2026-06-01": ["ADAUSDT", "BTCUSDT", "ETHUSDT", "LINKUSDT"],
}
KINDS = ("incremental_book_L2", "trades")

def probe(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "MEAFLOW-research/1.0",
        "Range": "bytes=0-4095",
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            prefix = r.read(4096)
            return {
                "http_status": r.status,
                "content_type": r.headers.get("Content-Type"),
                "content_length": r.headers.get("Content-Length"),
                "content_range": r.headers.get("Content-Range"),
                "range_honored": r.status == 206,
                "gzip_magic": prefix[:2].hex() == "1f8b",
                "prefix_bytes_read": len(prefix),
                "usable_prefix": len(prefix) >= 2 and prefix[:2] == b"\x1f\x8b",
            }
    except urllib.error.HTTPError as e:
        return {"http_status": e.code, "error": str(e)}
    except Exception as e:
        return {"error": repr(e)}

def main():
    out = {
        "experiment": "EXP-018-TARDIS-ACTUAL-SIGNAL-SOURCE-PROBE",
        "purpose": "Check unauthenticated Tardis L2/trade archive availability at exact dates and symbols where frozen MEAFLOW-72 OOS replay generated actual order deltas.",
        "strategy_oos": "2025-09-06T18:24:00+00:00/2026-10-31T16:00:00+00:00",
        "source": "Tardis public Binance Futures CSV archives; 4 KiB HTTP Range probe only",
        "actual_order_dates": EVENTS,
        "files": {},
        "limitations": [
            "A successful prefix probe proves only archive reachability and gzip prefix, not full-file integrity or complete day coverage.",
            "No execution replay, fill rate, slippage, PnL, fees, or strategy change is performed.",
            "Order timestamps and sizes come from the existing EXP-017 report; no strategy code is modified.",
            "No raw data is persisted."
        ],
    }
    for date, symbols in EVENTS.items():
        y, m, d = date.split("-")
        for symbol in symbols:
            for kind in KINDS:
                key = f"{date}/{symbol}/{kind}"
                url = f"{BASE}/{kind}/{y}/{m}/{d}/{symbol}.csv.gz"
                item = probe(url)
                item["url"] = url
                out["files"][key] = item
                print(key, json.dumps(item), flush=True)
                time.sleep(0.15)
    tested = list(out["files"].values())
    out["summary"] = {
        "files_tested": len(tested),
        "http_200_or_206": sum(x.get("http_status") in (200, 206) for x in tested),
        "range_supported": sum(x.get("range_honored") is True for x in tested),
        "valid_gzip_prefix": sum(x.get("usable_prefix") is True for x in tested),
        "http_401": sum(x.get("http_status") == 401 for x in tested),
        "http_404": sum(x.get("http_status") == 404 for x in tested),
        "other_errors": sum("error" in x and "http_status" not in x for x in tested),
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp018_tardis_source_probe.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(out["summary"]), flush=True)

if __name__ == "__main__":
    main()
