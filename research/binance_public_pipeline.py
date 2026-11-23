#!/usr/bin/env python3
"""Download and QA Binance USD-M public monthly klines + aggTrades.
No API keys, private endpoints, account access, or order placement.
"""
from __future__ import annotations
import argparse, csv, gzip, hashlib, io, json, re, sys, time, urllib.request, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://data.binance.vision/data/futures/um/monthly"

def months_between(start: str, end: str):
    y, m = map(int, start.split("-")); ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13: y, m = y + 1, 1

def timestamp_ms(raw: str) -> tuple[int, str]:
    n = int(raw)
    if n >= 10**17: return n // 10**6, "ns"
    if n >= 10**14: return n // 10**3, "us"
    return n, "ms"

def download(url: str, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size:
        return "cached"
    tmp = path.with_suffix(path.suffix + ".part")
    error = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 research-only"})
            with urllib.request.urlopen(req, timeout=120) as response, tmp.open("wb") as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block: break
                    out.write(block)
            tmp.replace(path)
            return "downloaded"
        except Exception as exc:
            error = str(exc)
            tmp.unlink(missing_ok=True)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Download failed: {url} ({error})")

def check_sha256(zip_path: Path, checksum_path: Path):
    tokens = checksum_path.read_text(encoding="utf-8").strip().split()
    if not tokens: raise RuntimeError(f"Empty checksum: {checksum_path}")
    expected = tokens[0].lower()
    h = hashlib.sha256()
    with zip_path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    actual = h.hexdigest()
    if actual != expected:
        raise RuntimeError(f"SHA256 mismatch for {zip_path.name}: {actual} != {expected}")
    return actual

def archive(kind: str, symbol: str, month: str, root: Path):
    if kind == "klines":
        name = f"{symbol}-1m-{month}.zip"
        url = f"{BASE}/klines/{symbol}/1m/{name}"
    else:
        name = f"{symbol}-aggTrades-{month}.zip"
        url = f"{BASE}/aggTrades/{symbol}/{name}"
    path = root / "cache" / symbol / kind / name
    status = download(url, path)
    checksum_path = Path(str(path) + ".CHECKSUM")
    checksum_status = download(url + ".CHECKSUM", checksum_path)
    digest = check_sha256(path, checksum_path)
    return path, {"file": name, "download": status, "checksum_download": checksum_status,
                  "sha256": digest, "bytes": path.stat().st_size}

def csv_stream(zip_path: Path):
    zf = zipfile.ZipFile(zip_path)
    names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not names: raise RuntimeError(f"No CSV in {zip_path}")
    return zf, io.TextIOWrapper(zf.open(names[0]), encoding="utf-8", newline="")

def load_klines(path: Path):
    bars = {}
    units = defaultdict(int)
    zf, fh = csv_stream(path)
    try:
        for row in csv.reader(fh):
            if len(row) < 11: continue
            try:
                ms, unit = timestamp_ms(row[0]); units[unit] += 1
                minute = ms // 60000
                if minute in bars: raise RuntimeError(f"Duplicate kline minute: {minute}")
                bars[minute] = {
                    "open": float(row[1]), "high": float(row[2]), "low": float(row[3]),
                    "close": float(row[4]), "volume": float(row[5]),
                    "quote_volume": float(row[7]), "trades": int(float(row[8])),
                    "taker_buy_base": float(row[9]), "taker_buy_quote": float(row[10]),
                }
            except (ValueError, IndexError): continue
    finally:
        fh.close(); zf.close()
    if not bars: raise RuntimeError(f"No valid klines in {path}")
    return bars, dict(units)

def load_aggtrades(path: Path, whale_usdt: float):
    # Per minute: aggressive buy/sell base+quote, counts, whale notionals.
    flow = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0.0, 0.0, 0.0])
    units = defaultdict(int); rows = 0; first_ms = None; last_ms = None
    zf, fh = csv_stream(path)
    try:
        for row in csv.reader(fh):
            if len(row) < 7: continue
            try:
                price, qty = float(row[1]), float(row[2])
                ms, unit = timestamp_ms(row[5]); units[unit] += 1
                minute = ms // 60000
                quote = price * qty
                buyer_maker = row[6].strip().lower() in ("true", "1")
                a = flow[minute]
                if buyer_maker:  # buyer was maker => seller was taker
                    a[1] += qty; a[3] += quote; a[5] += 1
                    if quote >= whale_usdt: a[7] += quote
                    a[8] = price if a[8] == 0.0 else min(a[8], price)  # lowest aggressive-sell trade price
                else:             # buyer was taker
                    a[0] += qty; a[2] += quote; a[4] += 1
                    if quote >= whale_usdt: a[6] += quote
                    a[9] = max(a[9], price)  # highest aggressive-buy trade price
                rows += 1
                first_ms = ms if first_ms is None else min(first_ms, ms)
                last_ms = ms if last_ms is None else max(last_ms, ms)
            except (ValueError, IndexError): continue
    finally:
        fh.close(); zf.close()
    return flow, {"rows": rows, "timestamp_units": dict(units),
                  "first_trade_utc": datetime.fromtimestamp(first_ms/1000, timezone.utc).isoformat() if first_ms else None,
                  "last_trade_utc": datetime.fromtimestamp(last_ms/1000, timezone.utc).isoformat() if last_ms else None}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01")
    ap.add_argument("--end", default="2024-01")
    ap.add_argument("--symbols", default="BTCUSDT")
    ap.add_argument("--whale-usdt", type=float, default=100000.0)
    ap.add_argument("--out", default="research-output")
    args = ap.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}", args.start) or not re.fullmatch(r"\d{4}-\d{2}", args.end):
        ap.error("start/end must be YYYY-MM")
    months = list(months_between(args.start, args.end))
    if not months or len(months) > 2:
        ap.error("Pilot workflow is limited to at most 2 months per run; expand only after validation.")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols or len(symbols) > 3: ap.error("Provide 1-3 symbols.")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    report = {"source":"Binance Vision official USD-M Futures monthly archives",
              "start":args.start,"end":args.end,"symbols":{},"limitations":[
                "This run performs data acquisition and QA, not a profitability backtest.",
                "AggTrade buyer-maker=true is classified as aggressive sell; false as aggressive buy.",
                "Whale is a configurable single aggregate-trade notional threshold, not investor identity.",
                "No historical L2 queue reconstruction or guaranteed maker fill simulation is performed."
              ]}
    for symbol in symbols:
        report["symbols"][symbol] = {}
        for month in months:
            print(f"[{symbol} {month}] downloading and validating klines...", flush=True)
            kp, km = archive("klines", symbol, month, out)
            bars, kunits = load_klines(kp)
            print(f"[{symbol} {month}] downloading and aggregating aggTrades...", flush=True)
            tp, tm = archive("aggTrades", symbol, month, out)
            flow, trade_meta = load_aggtrades(tp, args.whale_usdt)
            mins = sorted(bars)
            missing = sum(1 for a,b in zip(mins, mins[1:]) if b-a > 1)
            gaps_minutes = sum(max(0,b-a-1) for a,b in zip(mins, mins[1:]))
            feature_path = out / f"{symbol}-{month}-1m-orderflow.csv.gz"
            with gzip.open(feature_path, "wt", encoding="utf-8", newline="") as gz:
                w = csv.writer(gz)
                w.writerow(["open_time_ms","open","high","low","close","base_volume","quote_volume",
                            "trade_count","kline_taker_buy_base","kline_taker_buy_quote",
                            "agg_taker_buy_base","agg_taker_sell_base","agg_taker_buy_quote",
                            "agg_taker_sell_quote","agg_taker_buy_count","agg_taker_sell_count",
                            "whale_buy_quote","whale_sell_quote","ofi_base","ofi_quote",
                            "agg_sell_min_price","agg_buy_max_price"])
                for minute in mins:
                    k = bars[minute]; f = flow.get(minute, [0.0]*10)
                    base_den = f[0] + f[1]; quote_den = f[2] + f[3]
                    ofi_base = (f[0]-f[1])/base_den if base_den else 0.0
                    ofi_quote = (f[2]-f[3])/quote_den if quote_den else 0.0
                    w.writerow([minute*60000,k["open"],k["high"],k["low"],k["close"],k["volume"],
                                k["quote_volume"],k["trades"],k["taker_buy_base"],k["taker_buy_quote"],
                                f[0],f[1],f[2],f[3],f[4],f[5],f[6],f[7],ofi_base,ofi_quote,f[8],f[9]])
            report["symbols"][symbol][month] = {
                "klines":{"rows":len(bars),"timestamp_units":kunits,"missing_minute_gaps":missing,
                          "missing_minutes_total":gaps_minutes,"archive":km},
                "aggTrades":{"rows":trade_meta["rows"],"timestamp_units":trade_meta["timestamp_units"],
                             "first_trade_utc":trade_meta["first_trade_utc"],
                             "last_trade_utc":trade_meta["last_trade_utc"],"archive":tm},
                "features":{"path":feature_path.name,"rows":len(bars),
                            "aggtrade_minutes_with_activity":len(flow),
                            "whale_threshold_usdt":args.whale_usdt}
            }
            print(f"[{symbol} {month}] done: {len(bars):,} 1m bars, {trade_meta['rows']:,} aggTrades", flush=True)
    (out/"qa_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("QA COMPLETE — no strategy profitability claim has been made.")
    print((out/"qa_report.json").resolve())

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
