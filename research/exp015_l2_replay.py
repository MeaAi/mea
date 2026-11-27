#!/usr/bin/env python3
"""EXP-015 sampled-day Binance Futures L2/trade replay.

This is an execution-calibration probe, not a strategy backtest. It uses a
100 USDT notional passive order at each side's observed best quote once per
minute. It reports conservative trade-volume queue bounds and strict
trade-through upper bounds; it does not claim exact queue position/fill odds.
Raw archives stay in /tmp and are never committed or uploaded as artifacts.
"""
import csv, gzip, heapq, hashlib, json, os, urllib.request
from pathlib import Path

DATE = "2024/07/01"
SYMBOLS = ("BTCUSDT",)
BASE = "https://datasets.tardis.dev/v1/binance-futures"
OUT = Path("exp015_l2_replay.json")
NOTIONAL = 100.0
SECONDS = 60

def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "MEAFLOW-research/1.0"})
    h = hashlib.sha256(); size = 0
    with urllib.request.urlopen(req, timeout=180) as r, open(path, "wb") as f:
        if r.status != 200: raise RuntimeError(f"HTTP {r.status}: {url}")
        while True:
            b = r.read(1024 * 1024)
            if not b: break
            f.write(b); h.update(b); size += len(b)
    return size, h.hexdigest()

def best(book, heap, sign):
    # sign=+1 for bids stored as negative prices; -1 for asks
    while heap:
        p = heap[0]
        px = -p if sign == 1 else p
        if book.get(px, 0) > 0: return px, book[px]
        heapq.heappop(heap)
    return None, 0.0

def make_quotes(path):
    bids, asks = {}, {}
    bh, ah = [], []
    quotes = []
    last_local = None
    snapshot_group = None
    current_minute = None
    rows = 0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        required = {"local_timestamp", "is_snapshot", "side", "price", "amount"}
        if not required.issubset(set(rd.fieldnames or [])):
            raise RuntimeError("L2 schema mismatch")
        for row in rd:
            rows += 1
            local = int(row["local_timestamp"])
            # The CSV's original row order is retained. Only publish a book
            # after a complete local_timestamp message has been consumed.
            if last_local is not None and local < last_local:
                raise RuntimeError("L2 local_timestamp is not monotonic")
            if last_local is not None and local != last_local:
                minute = last_local // 60_000_000
                if current_minute != minute:
                    bp, bq = best(bids, bh, 1); ap, aq = best(asks, ah, -1)
                    if bp is not None and ap is not None and bp < ap:
                        quotes.append({"minute": minute, "local": last_local,
                                       "bid": bp, "bid_qty": bq, "ask": ap, "ask_qty": aq})
                    current_minute = minute
            if row["is_snapshot"].lower() == "true":
                if snapshot_group != local:
                    bids.clear(); asks.clear(); bh.clear(); ah.clear()
                    snapshot_group = local
            side = row["side"].lower()
            px = float(row["price"]); qty = float(row["amount"])
            book, heap = (bids, bh) if side == "bid" else (asks, ah)
            if qty <= 0:
                book.pop(px, None)
            else:
                book[px] = qty
                heapq.heappush(heap, -px if side == "bid" else px)
            last_local = local
    if last_local is not None:
        minute = last_local // 60_000_000
        if current_minute != minute:
            bp, bq = best(bids, bh, 1); ap, aq = best(asks, ah, -1)
            if bp is not None and ap is not None and bp < ap:
                quotes.append({"minute": minute, "local": last_local,
                               "bid": bp, "bid_qty": bq, "ask": ap, "ask_qty": aq})
    return quotes, rows

def replay_trades(path, quotes):
    # For each minute's quote, inspect only subsequent trade events until the
    # next quote minute. Aggressor side is the taker side in Tardis trade data.
    stats = {s: {"orders": 0, "exact_touch": 0, "queue_lower_fills": 0,
                 "strict_through_upper_fills": 0, "no_fill": 0,
                 "exact_trade_qty": 0.0, "initial_queue_qty": 0.0,
                 "quote_mid_move_bp_abs": 0.0} for s in ("passive_buy", "passive_sell")}
    qidx = 0; active = None; last_local = -1; trade_rows = 0
    def activate(q):
        nonlocal active
        active = {
            "minute": q["minute"], "end": (q["minute"] + 1) * 60_000_000,
            "buy_px": q["bid"], "buy_queue": q["bid_qty"],
            "buy_qty": NOTIONAL / q["bid"], "buy_trade": 0.0, "buy_through": False,
            "sell_px": q["ask"], "sell_queue": q["ask_qty"],
            "sell_qty": NOTIONAL / q["ask"], "sell_trade": 0.0, "sell_through": False,
        }
        for side, key in (("passive_buy", "buy_queue"), ("passive_sell", "sell_queue")):
            stats[side]["orders"] += 1
            stats[side]["initial_queue_qty"] += active[key]
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        required = {"local_timestamp", "side", "price", "amount"}
        if not required.issubset(set(rd.fieldnames or [])):
            raise RuntimeError("trades schema mismatch")
        for row in rd:
            trade_rows += 1
            local = int(row["local_timestamp"])
            if local < last_local: raise RuntimeError("trade local_timestamp is not monotonic")
            last_local = local
            while qidx < len(quotes) and quotes[qidx]["local"] < local:
                if active is not None:
                    for s, pkey, qkey, tkey, xkey in (
                        ("passive_buy","buy_px","buy_queue","buy_trade","buy_through"),
                        ("passive_sell","sell_px","sell_queue","sell_trade","sell_through")):
                        a = active
                        if a[tkey] > 0: stats[s]["exact_touch"] += 1
                        if a[tkey] >= a[qkey] + a["buy_qty" if s=="passive_buy" else "sell_qty"]:
                            stats[s]["queue_lower_fills"] += 1
                        elif a[xkey]:
                            stats[s]["strict_through_upper_fills"] += 1
                        else:
                            stats[s]["no_fill"] += 1
                        stats[s]["exact_trade_qty"] += a[tkey]
                activate(quotes[qidx]); qidx += 1
            if active is None or local >= active["end"]: continue
            px = float(row["price"]); qty = float(row["amount"]); taker = row["side"].lower()
            if taker == "sell":
                if px == active["buy_px"]: active["buy_trade"] += qty
                if px < active["buy_px"]: active["buy_through"] = True
            elif taker == "buy":
                if px == active["sell_px"]: active["sell_trade"] += qty
                if px > active["sell_px"]: active["sell_through"] = True
    # Close the final active quote window.
    if active is not None:
        for s in ("passive_buy", "passive_sell"):
            a = active; is_buy = s == "passive_buy"
            traded = a["buy_trade" if is_buy else "sell_trade"]
            queue = a["buy_queue" if is_buy else "sell_queue"]
            own = a["buy_qty" if is_buy else "sell_qty"]
            through = a["buy_through" if is_buy else "sell_through"]
            if traded > 0: stats[s]["exact_touch"] += 1
            if traded >= queue + own: stats[s]["queue_lower_fills"] += 1
            elif through: stats[s]["strict_through_upper_fills"] += 1
            else: stats[s]["no_fill"] += 1
            stats[s]["exact_trade_qty"] += traded
    for s, d in stats.items():
        n = d["orders"]
        d["exact_touch_rate_pct"] = 100*d["exact_touch"]/n if n else None
        d["queue_lower_fill_rate_pct"] = 100*d["queue_lower_fills"]/n if n else None
        d["strict_through_upper_fill_rate_pct"] = 100*(d["queue_lower_fills"]+d["strict_through_upper_fills"])/n if n else None
        d["no_fill_rate_pct"] = 100*d["no_fill"]/n if n else None
    return stats, trade_rows

def main():
    report = {"experiment":"EXP-015-L2-REPLAY-PILOT","date_utc":"2024-07-01",
              "exchange":"binance-futures","probe_order_notional_usdt":NOTIONAL,
              "symbols":{},"raw_data_committed":False,
              "method_limits":["L2 market-by-price, not market-by-order; exact FIFO queue position unavailable.",
                "Lower bound assumes all displayed quantity at quote is ahead and only observed same-price taker volume consumes it; later cancellations ahead are not credited.",
                "Upper bound requires a subsequent aggressive trade strictly through the quote while the one-minute order is live.",
                "Orders are analytical probes placed at the first valid L2 quote per minute, not MEAFLOW signals or a portfolio backtest.",
                "No fees, funding, portfolio PnL, partial-fill path reconstruction, or market impact in this calibration pilot."]}
    for sym in SYMBOLS:
        l2 = Path(f"/tmp/{sym}-l2.csv.gz"); tr = Path(f"/tmp/{sym}-trades.csv.gz")
        base = f"{BASE}/"
        l2_url = f"{base}incremental_book_L2/{DATE}/{sym}.csv.gz"
        tr_url = f"{base}trades/{DATE}/{sym}.csv.gz"
        l2_size,l2_sha = download(l2_url,l2); tr_size,tr_sha = download(tr_url,tr)
        quotes,l2_rows = make_quotes(l2)
        if len(quotes) < 1000: raise RuntimeError(f"Insufficient valid minute quotes for {sym}: {len(quotes)}")
        stats,trade_rows = replay_trades(tr,quotes)
        report["symbols"][sym] = {"l2":{"download_bytes":l2_size,"sha256":l2_sha,"rows":l2_rows},
            "trades":{"download_bytes":tr_size,"sha256":tr_sha,"rows":trade_rows},
            "valid_minute_quotes":len(quotes),"passive_order_results":stats}
        print(sym,"L2 rows",l2_rows,"trade rows",trade_rows,"quotes",len(quotes),flush=True)
        l2.unlink(missing_ok=True); tr.unlink(missing_ok=True)
    OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT",OUT,"bytes",OUT.stat().st_size,flush=True)

if __name__ == "__main__": main()
