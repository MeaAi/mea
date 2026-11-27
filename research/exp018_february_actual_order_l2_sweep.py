#!/usr/bin/env python3
"""EXP-018 actual MEAFLOW-72 order market-sweep replay against Tardis L2.

Scope is deliberately limited to two OOS first-of-month dates whose exact
rebalance events generated orders: 2025-10-01 and 2026-06-01. It uses the
actual signed order deltas from the frozen EXP-017 audit, reconstructs the
market-by-price book, and sweeps displayed depth on the correct side.

This is an immediate taker-cost estimate at the first completed L2 message
after the strategy timestamp. It is not a full execution simulator: no
network latency, hidden liquidity, exchange matching-engine queue, impact
after the snapshot, or fees are inferred from the L2 data.
"""
import csv, gzip, hashlib, json, math, os, urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE = "https://datasets.tardis.dev/v1/binance-futures"
SOURCE_REPORT = Path("research-results/exp017_signal_alignment_audit.json")
OUT = Path("research-results/exp018_february_actual_order_l2_sweep.json")
DATES = {"2026-02-01"}
FEE_BP_ONE_WAY = 5.0
MODEL_SLIPPAGE_BP_ONE_WAY = 2.0

def to_us(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1_000_000)

def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "MEAFLOW-research/1.0"})
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(req, timeout=180) as response, open(path, "wb") as f:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {url}")
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            f.write(block)
            digest.update(block)
            total += len(block)
    return total, digest.hexdigest()

def top_levels(book, side, limit=100):
    if side == "bid":
        vals = sorted(((p, q) for p, q in book.items() if q > 0), reverse=True)
    else:
        vals = sorted(( (p, q) for p, q in book.items() if q > 0), key=lambda x: x[0])
    return vals[:limit]

def sweep(levels, quantity):
    remaining = quantity
    notional = 0.0
    filled = 0.0
    for price, available in levels:
        take = min(remaining, available)
        if take > 0:
            filled += take
            notional += take * price
            remaining -= take
        if remaining <= max(1e-12, quantity * 1e-10):
            remaining = 0.0
            break
    return {
        "filled_qty": filled,
        "remaining_qty": max(0.0, remaining),
        "vwap": notional / filled if filled > 0 else None,
        "execution_notional_usdt": notional,
    }

def replay_symbol_day(date, symbol, orders):
    y, m, d = date.split("-")
    url = f"{BASE}/incremental_book_L2/{y}/{m}/{d}/{symbol}.csv.gz"
    path = Path(f"/tmp/exp018_{date}_{symbol}_l2.csv.gz")
    size, sha = download(url, path)
    targets = sorted(
        [{"target_us": to_us(o["time_utc"]), "order": o} for o in orders],
        key=lambda x: x["target_us"]
    )
    captured = []
    bids, asks = {}, {}
    last_local = None
    snapshot_group = None
    saw_snapshot = False
    rows = 0
    snapshots = 0
    timestamp_order_issues = 0
    target_index = 0

    def capture_ready(completed_local):
        nonlocal target_index
        while target_index < len(targets) and completed_local >= targets[target_index]["target_us"]:
            if not saw_snapshot:
                captured.append({"order": targets[target_index]["order"], "error": "no_snapshot_before_signal"})
            else:
                captured.append({
                    "order": targets[target_index]["order"],
                    "local_timestamp_us": completed_local,
                    "delay_ms": (completed_local - targets[target_index]["target_us"]) / 1000.0,
                    "bids": top_levels(bids, "bid"),
                    "asks": top_levels(asks, "ask"),
                })
            target_index += 1

    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"local_timestamp", "timestamp", "is_snapshot", "side", "price", "amount"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise RuntimeError(f"L2 schema mismatch for {symbol} {date}: {reader.fieldnames}")
            for row in reader:
                rows += 1
                local = int(row["local_timestamp"])
                if last_local is not None and local < last_local:
                    timestamp_order_issues += 1
                    raise RuntimeError(f"non-monotonic local_timestamp: {symbol} {date}")
                if last_local is not None and local != last_local:
                    capture_ready(last_local)
                if row["is_snapshot"].lower() == "true":
                    if snapshot_group != local:
                        bids.clear()
                        asks.clear()
                        snapshot_group = local
                        snapshots += 1
                        saw_snapshot = True
                side = row["side"].lower()
                price = float(row["price"])
                amount = float(row["amount"])
                book = bids if side == "bid" else asks
                if amount <= 0:
                    book.pop(price, None)
                else:
                    book[price] = amount
                last_local = local
        if last_local is not None:
            capture_ready(last_local)
    finally:
        path.unlink(missing_ok=True)

    while target_index < len(targets):
        captured.append({"order": targets[target_index]["order"], "error": "signal_after_last_l2_update"})
        target_index += 1

    results = []
    for item in captured:
        order = item["order"]
        if "error" in item:
            results.append({
                "time_utc": order["time_utc"], "symbol": symbol, "side": order["side"],
                "order_qty": abs(float(order["quantity_delta"])),
                "reference_price": order["reference_price"],
                "notional_usdt": order["notional_usdt"], "status": item["error"],
            })
            continue
        side = order["side"]
        qty = abs(float(order["quantity_delta"]))
        levels = item["asks"] if side == "BUY" else item["bids"]
        opposite = item["bids"] if side == "BUY" else item["asks"]
        execution = sweep(levels, qty)
        best_bid = item["bids"][0][0] if item["bids"] else None
        best_ask = item["asks"][0][0] if item["asks"] else None
        mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
        vwap = execution["vwap"]
        ref = float(order["reference_price"])
        if vwap is not None and mid:
            cost_mid_bp = ((vwap / mid - 1) if side == "BUY" else (mid / vwap - 1)) * 10000
            cost_mark_bp = ((vwap / ref - 1) if side == "BUY" else (ref - vwap) / ref) * 10000
        else:
            cost_mid_bp = cost_mark_bp = None
        spread_bp = ((best_ask - best_bid) / mid * 10000) if mid else None
        full = execution["remaining_qty"] <= max(1e-12, qty * 1e-10)
        results.append({
            "time_utc": order["time_utc"], "symbol": symbol, "side": side,
            "order_qty": qty, "reference_price": ref,
            "strategy_order_notional_usdt": float(order["notional_usdt"]),
            "book_local_timestamp_us": item["local_timestamp_us"],
            "book_delay_ms": round(item["delay_ms"], 4),
            "best_bid": best_bid, "best_ask": best_ask, "mid": mid,
            "spread_bp": round(spread_bp, 4) if spread_bp is not None else None,
            "vwap": vwap,
            "filled_qty": execution["filled_qty"],
            "remaining_qty": execution["remaining_qty"],
            "full_displayed_depth_fill": full,
            "execution_notional_usdt": execution["execution_notional_usdt"],
            "market_cost_vs_mid_bp": round(cost_mid_bp, 4) if cost_mid_bp is not None else None,
            "market_cost_vs_mark_reference_bp": round(cost_mark_bp, 4) if cost_mark_bp is not None else None,
            "model_slippage_assumption_bp": MODEL_SLIPPAGE_BP_ONE_WAY,
            "model_fee_assumption_bp": FEE_BP_ONE_WAY,
            "status": "full_depth_sweep" if full else "insufficient_displayed_depth",
        })

    return {
        "date_utc": date, "symbol": symbol, "archive_bytes": size,
        "archive_sha256": sha, "l2_rows": rows, "snapshot_groups": snapshots,
        "timestamp_order_issues": timestamp_order_issues,
        "orders": results,
    }

def summarize(results):
    valid = [x for x in results if x.get("status") == "full_depth_sweep" and x.get("market_cost_vs_mark_reference_bp") is not None]
    costs = sorted(x["market_cost_vs_mark_reference_bp"] for x in valid)
    def pct(p):
        if not costs: return None
        return costs[min(len(costs)-1, max(0, math.ceil(p*len(costs))-1))]
    total_notional = sum(x["strategy_order_notional_usdt"] for x in valid)
    weighted_cost = (
        sum(x["strategy_order_notional_usdt"] * x["market_cost_vs_mark_reference_bp"] for x in valid) / total_notional
        if total_notional else None
    )
    return {
        "orders_total": len(results),
        "orders_with_full_displayed_depth": len(valid),
        "orders_partial_or_missing": len(results)-len(valid),
        "median_market_cost_vs_mark_bp": pct(.5),
        "p90_market_cost_vs_mark_bp": pct(.9),
        "max_market_cost_vs_mark_bp": max(costs) if costs else None,
        "notional_weighted_market_cost_vs_mark_bp": round(weighted_cost, 4) if weighted_cost is not None else None,
        "orders_exceeding_2bp_model_slippage": sum(x["market_cost_vs_mark_reference_bp"] > MODEL_SLIPPAGE_BP_ONE_WAY for x in valid),
        "orders_exceeding_2bp_and_5bp_fee_combined": sum(x["market_cost_vs_mark_reference_bp"] + FEE_BP_ONE_WAY > MODEL_SLIPPAGE_BP_ONE_WAY + FEE_BP_ONE_WAY for x in valid),
        "mean_book_delay_ms": round(sum(x["book_delay_ms"] for x in valid) / len(valid), 4) if valid else None,
    }

def main():
    source = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    events = [e for e in source["matched_first_of_month_events"]
              if e["time_utc"][:10] in DATES and e.get("orders")]
    grouped = defaultdict(list)
    for event in events:
        for order in event["orders"]:
            grouped[(event["time_utc"][:10], order["symbol"])].append({
                **order, "time_utc": event["time_utc"], "regime": event["regime"],
                "active_mode": event["active_mode"],
            })
    report = {
        "experiment": "EXP-018B-FEBRUARY-ACTUAL-MEAFLOW72-ORDER-L2-MARKET-SWEEP",
        "status": "running",
        "strategy_source": "EXP-017 frozen MEAFLOW-72 OOS signal-alignment audit",
        "scope_dates_utc": sorted(DATES),
        "scope_note": "Only actual order deltas on 2026-02-01; extends EXP-018 to the third actual sampled OOS rebalance date.",
        "execution_method": "At the first completed Tardis incremental_book_L2 local_timestamp at or after each actual strategy signal timestamp, sweep the displayed asks for BUY or bids for SELL using the exact absolute strategy quantity delta.",
        "assumptions": {
            "initial_capital_usdt": 100,
            "strategy_reference_price": "EXP-017 mark-price reference at signal",
            "one_way_fee_bp_assumed": FEE_BP_ONE_WAY,
            "one_way_slippage_bp_assumed": MODEL_SLIPPAGE_BP_ONE_WAY,
            "latency": "No added network latency; first complete L2 message after signal is used",
        },
        "limitations": [
            "Tardis incremental_book_L2 is market-by-price aggregated depth, not market-by-order FIFO queue.",
            "This is an immediate taker sweep of displayed depth, not a maker fill model.",
            "No hidden liquidity, exchange matching-engine behavior, additional network latency, market impact after the snapshot, or funding/PnL is modeled.",
            "The two sampled dates are a subset of actual OOS order events; results cannot be extrapolated to all 268 order deltas or to other symbols/dates.",
            "A full displayed-depth sweep is a snapshot estimate, not a guarantee of live execution.",
        ],
        "files": [],
    }
    for (date, symbol), orders in sorted(grouped.items()):
        print("START", date, symbol, "orders", len(orders), flush=True)
        item = replay_symbol_day(date, symbol, orders)
        report["files"].append(item)
        print("DONE", date, symbol, "rows", item["l2_rows"],
              "orders", len(item["orders"]), flush=True)
    all_orders = [o for f in report["files"] for o in f["orders"]]
    report["order_results"] = all_orders
    report["summary"] = summarize(all_orders)
    report["status"] = "completed"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(report["summary"]), flush=True)

if __name__ == "__main__":
    main()
