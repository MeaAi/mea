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

DATE = "2024/12/01"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
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
    # Do not emit the final minute quote: there is no following full minute
    # of trade data available to evaluate its 60-second lifetime.
    return quotes, rows

def replay_trades(path, quotes):
    # Each probe remains live until its own quote_timestamp + 60 seconds.
    # Minute quotes can be offset from the minute boundary, so orders may
    # overlap; keep all live probes instead of closing one at the next quote.
    stats = {s: {"orders": 0, "exact_price_trade_hit": 0, "queue_lower_fills": 0,
                 "strict_through_only_fills": 0, "no_fill": 0,
                 "exact_trade_qty": 0.0, "initial_queue_qty": 0.0}
             for s in ("passive_buy", "passive_sell")}
    qidx = 0
    active = []
    last_local = -1
    trade_rows = 0

    def activate(q):
        order = {
            "end": q["local"] + 60_000_000,
            "buy_px": q["bid"], "buy_queue": q["bid_qty"],
            "buy_qty": NOTIONAL / q["bid"], "buy_trade": 0.0, "buy_through": False,
            "sell_px": q["ask"], "sell_queue": q["ask_qty"],
            "sell_qty": NOTIONAL / q["ask"], "sell_trade": 0.0, "sell_through": False,
        }
        for side, key in (("passive_buy", "buy_queue"), ("passive_sell", "sell_queue")):
            stats[side]["orders"] += 1
            stats[side]["initial_queue_qty"] += order[key]
        active.append(order)

    def finalize(order):
        for side in ("passive_buy", "passive_sell"):
            is_buy = side == "passive_buy"
            traded = order["buy_trade" if is_buy else "sell_trade"]
            queue = order["buy_queue" if is_buy else "sell_queue"]
            own = order["buy_qty" if is_buy else "sell_qty"]
            through = order["buy_through" if is_buy else "sell_through"]
            if traded > 0:
                stats[side]["exact_price_trade_hit"] += 1
            if traded >= queue + own:
                stats[side]["queue_lower_fills"] += 1
            elif through:
                stats[side]["strict_through_only_fills"] += 1
            else:
                stats[side]["no_fill"] += 1
            stats[side]["exact_trade_qty"] += traded

    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        required = {"local_timestamp", "side", "price", "amount"}
        if not required.issubset(set(rd.fieldnames or [])):
            raise RuntimeError("trades schema mismatch")
        for row in rd:
            trade_rows += 1
            local = int(row["local_timestamp"])
            if local < last_local:
                raise RuntimeError("trade local_timestamp is not monotonic")
            last_local = local

            # Activate every quote strictly before this trade event.
            while qidx < len(quotes) and quotes[qidx]["local"] < local:
                activate(quotes[qidx])
                qidx += 1

            # Expire orders at their individual 60-second deadline before
            # processing a trade at/after that deadline.
            still_live = []
            for order in active:
                if local >= order["end"]:
                    finalize(order)
                else:
                    still_live.append(order)
            active = still_live

            if not active:
                continue
            px = float(row["price"])
            qty = float(row["amount"])
            taker = row["side"].lower()
            if taker == "sell":
                for order in active:
                    if px == order["buy_px"]:
                        order["buy_trade"] += qty
                    if px < order["buy_px"]:
                        order["buy_through"] = True
            elif taker == "buy":
                for order in active:
                    if px == order["sell_px"]:
                        order["sell_trade"] += qty
                    if px > order["sell_px"]:
                        order["sell_through"] = True

    # Finalize any orders whose full windows fit in the available trade file.
    for order in active:
        finalize(order)

    for side, data in stats.items():
        n = data["orders"]
        data["exact_price_trade_hit_rate_pct"] = 100 * data["exact_price_trade_hit"] / n if n else None
        data["queue_lower_fill_rate_pct"] = 100 * data["queue_lower_fills"] / n if n else None
        data["upper_bound_fill_rate_pct"] = 100 * (
            data["queue_lower_fills"] + data["strict_through_only_fills"]) / n if n else None
        data["no_fill_rate_pct"] = 100 * data["no_fill"] / n if n else None
    return stats, trade_rows

def main():
    report = {"experiment":"EXP-015-L2-REPLAY-PILOT","date_utc":"2024-12-01",
              "exchange":"binance-futures","probe_order_notional_usdt":NOTIONAL,
              "symbols":{},"raw_data_committed":False,
              "method_limits":["L2 market-by-price, not market-by-order; exact FIFO queue position unavailable.",
                "Lower bound assumes all displayed quantity at quote is ahead and only observed same-price taker volume consumes it; later cancellations ahead are not credited.",
                "Upper bound requires a subsequent aggressive trade strictly through the quote while the full 60-second order window is live.",
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
