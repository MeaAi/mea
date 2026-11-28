#!/usr/bin/env python3
"""EXP-019: stratified, actual-order MEAFLOW-72 L2 execution-cost sample.

Replays the frozen OOS policy without changing strategy code. It selects
three time-spread order-bearing rebalance events from each available regime,
then sweeps the exact order quantities against Tardis incremental L2 books.
Sideways/hold events are reported separately because they generate no orders.
"""
import json, math
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import funding_carry_liquidation_causal as sim
import exp018_actual_order_l2_sweep as l2

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull": "both", "bear": "short_only", "sideways": "flat", "unknown": "flat"}
OOS_START = "2025-09-06T18:24:00+00:00"
OOS_END = "2026-10-31T16:00:00+00:00"
OUT = Path("research-results/exp019_stratified_l2_sweep.json")
QUANTILES = (0.20, 0.50, 0.80)

def to_ms(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)

def percentile(values, p):
    if not values:
        return None
    a = sorted(values)
    return round(a[min(len(a)-1, max(0, math.ceil(p*len(a))-1))], 6)

def select_events(log):
    by_regime = {}
    for regime in ("bull", "bear", "sideways", "unknown"):
        events = [e for e in log if e.get("regime") == regime and e.get("orders")]
        events.sort(key=lambda e: e["time_utc"])
        if not events:
            by_regime[regime] = []
            continue
        chosen = []
        used = set()
        for q in QUANTILES:
            ix = round(q * (len(events)-1))
            if ix not in used:
                chosen.append(events[ix])
                used.add(ix)
        by_regime[regime] = chosen
    return by_regime

def summarize(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(row.get(key, "unknown"), []).append(row)
    out = {}
    for name, items in sorted(groups.items()):
        valid = [x for x in items if x.get("full_displayed_depth_fill") and x.get("market_cost_vs_mid_bp") is not None]
        costs = [x["market_cost_vs_mid_bp"] for x in valid]
        notionals = [x.get("strategy_order_notional_usdt", 0.0) for x in valid]
        total = sum(notionals)
        weighted = sum(n*c for n,c in zip(notionals,costs))/total if total else None
        out[name] = {
            "orders_selected": len(items),
            "full_depth_fills": len(valid),
            "partial_or_missing": len(items)-len(valid),
            "median_mid_cost_bp": percentile(costs, .5),
            "p90_mid_cost_bp": percentile(costs, .9),
            "max_mid_cost_bp": round(max(costs), 6) if costs else None,
            "notional_weighted_mid_cost_bp": round(weighted, 6) if weighted is not None else None,
            "orders_over_2bp_mid_cost": sum(c > 2.0 for c in costs),
            "notional_usdt_full_depth": round(total, 6),
        }
    return out

def main():
    # 30-day BTC regime lookback + 7-day funding score lookback; no need to
    # reload pre-OOS history because the first OOS timestamp is Sep 2025.
    months = list(sim.months_between("2025-08", "2026-10"))
    data, errors = {}, {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(sim.load_symbol, s, months, Path("research-output")): s for s in SYMBOLS}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                _, funding, marks = future.result()
                data[symbol] = {"fund": funding, "marks": marks}
                print("LOADED", symbol, len(funding), len(marks), flush=True)
            except Exception as exc:
                errors[symbol] = str(exc)
                print("SKIP", symbol, str(exc), flush=True)
    if len(data) < 8 or "BTCUSDT" not in data:
        raise RuntimeError("Insufficient usable symbols: " + json.dumps(errors))
    data = {s: data[s] for s in sorted(data)}
    start, end = to_ms(OOS_START), to_ms(OOS_END)
    result = sim.run(
        data, (start, end), 1.0, 5, slip_bp=2,
        lookback_days=7, rebalance_days=7, tail_fraction=.20,
        regime_policy=POLICY, regime_threshold_pct=5.0,
        sideways_action="hold",
    )
    log = result["rebalance_log"]
    selected_by_regime = select_events(log)
    selected = [e for regime in selected_by_regime for e in selected_by_regime[regime]]

    grouped = {}
    for event in selected:
        date = event["time_utc"][:10]
        for order in event["orders"]:
            key = (date, order["symbol"])
            grouped.setdefault(key, []).append({
                **order, "time_utc": event["time_utc"],
                "regime": event["regime"], "active_mode": event["active_mode"],
            })

    report = {
        "experiment": "EXP-019-MEAFLOW72-STRATIFIED-ACTUAL-ORDER-L2-SWEEP",
        "status": "running",
        "strategy_branch": "MEAFLOW-72 (read-only replay; no strategy changes)",
        "research_branch": "research/meaflow-exp019-stratified-l2-sweep-v1",
        "source": "Official free Binance Vision fundingRate + 1h markPriceKlines; Tardis public Binance Futures incremental_book_L2",
        "oos_period_utc": {"start": OOS_START, "end": OOS_END},
        "configuration": {
            "capital_usdt": 100, "leverage": 1, "lookback_days": 7,
            "rebalance_days": 7, "tail_fraction": .20,
            "regime": "BTC trailing 30d mark-price return, +/-5%, last completed hourly candle",
            "regime_policy": POLICY, "sideways_action": "hold",
            "fee_bp_one_way_model": 5, "slippage_bp_one_way_model": 2,
        },
        "data_errors": errors,
        "loaded_symbols": list(data),
        "strategy_replay_metrics": {k: result[k] for k in (
            "start_equity_usdt", "end_equity_usdt", "net_return_pct",
            "max_drawdown_pct", "rebalance_count", "hourly_adverse_checks",
            "liquidated", "trading_fees_usdt", "slippage_usdt")},
        "rebalance_events_by_regime": {},
        "selected_event_timestamps": {},
        "selection_quantiles": list(QUANTILES),
        "selected_event_count": len(selected),
        "selected_order_count": sum(len(e["orders"]) for e in selected),
        "files": [],
        "limitations": [
            "L2 sweep is a snapshot taker-cost estimate at the first completed local_timestamp group at/after the signal.",
            "No extra network latency, hidden liquidity, matching-engine queue, post-snapshot impact, or live fill guarantee is modeled.",
            "Only order-bearing events are sampled; sideways/hold events intentionally generate zero order delta and are reported as such.",
            "The selected events are stratified across the existing OOS period, not an unseen profitability holdout.",
            "A successful displayed-depth sweep does not establish maker execution or full live execution quality.",
        ],
    }
    for regime in ("bull", "bear", "sideways", "unknown"):
        regime_events = [e for e in log if e.get("regime") == regime]
        with_orders = [e for e in regime_events if e.get("orders")]
        report["rebalance_events_by_regime"][regime] = {
            "rebalance_events": len(regime_events),
            "events_with_orders": len(with_orders),
            "order_deltas": sum(len(e["orders"]) for e in with_orders),
            "selected_events": len(selected_by_regime[regime]),
        }
        report["selected_event_timestamps"][regime] = [
            {"time_utc": e["time_utc"], "order_count": len(e["orders"]),
             "turnover_usdt": e["turnover_usdt"], "active_mode": e["active_mode"]}
            for e in selected_by_regime[regime]
        ]

    for (date, symbol), orders in sorted(grouped.items()):
        print("START L2", date, symbol, "orders", len(orders), flush=True)
        try:
            item = l2.replay_symbol_day(date, symbol, orders)
            for row in item["orders"]:
                row["regime"] = next((o["regime"] for o in orders if o["time_utc"] == row["time_utc"]), "unknown")
                row["active_mode"] = next((o["active_mode"] for o in orders if o["time_utc"] == row["time_utc"]), "unknown")
            report["files"].append(item)
            print("DONE L2", date, symbol, "orders", len(item["orders"]), flush=True)
        except Exception as exc:
            report["files"].append({"date_utc": date, "symbol": symbol, "error": str(exc), "orders": []})
            print("L2 ERROR", date, symbol, str(exc), flush=True)

    all_rows = [row for item in report["files"] for row in item.get("orders", [])]
    report["order_results"] = all_rows
    report["summary_by_regime"] = summarize(all_rows, "regime")
    report["summary_by_symbol"] = summarize(all_rows, "symbol")
    report["summary_overall"] = summarize(all_rows, "status") if False else summarize(all_rows, "regime").get("bull", {})
    # A single combined summary, preserving each actual order as the observation.
    valid = [x for x in all_rows if x.get("full_displayed_depth_fill") and x.get("market_cost_vs_mid_bp") is not None]
    costs = [x["market_cost_vs_mid_bp"] for x in valid]
    notionals = [x.get("strategy_order_notional_usdt", 0.0) for x in valid]
    total = sum(notionals)
    report["summary_overall"] = {
        "orders_selected": len(all_rows), "full_depth_fills": len(valid),
        "partial_or_missing": len(all_rows)-len(valid),
        "median_mid_cost_bp": percentile(costs, .5),
        "p90_mid_cost_bp": percentile(costs, .9),
        "max_mid_cost_bp": round(max(costs), 6) if costs else None,
        "notional_weighted_mid_cost_bp": round(sum(n*c for n,c in zip(notionals,costs))/total, 6) if total else None,
        "orders_over_2bp_mid_cost": sum(c > 2.0 for c in costs),
        "notional_usdt_full_depth": round(total, 6),
    }
    report["status"] = "completed_with_errors" if errors or any("error" in f for f in report["files"]) else "completed"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(report["summary_overall"]), flush=True)

if __name__ == "__main__":
    main()
