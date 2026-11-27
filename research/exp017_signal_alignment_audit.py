#!/usr/bin/env python3
"""Audit actual MEAFLOW-72 rebalance timestamps and order sizes for execution alignment.

This is an execution-data alignment audit, not a profitability test. It replays
the frozen causal MEAFLOW-72 policy on its established OOS window and emits
only actual rebalance order deltas. Raw Binance archives stay in research-output.
"""
import json, math
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import funding_carry_liquidation_causal as sim

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull": "both", "bear": "short_only", "sideways": "flat", "unknown": "flat"}
OOS_START = "2025-09-06T18:24:00+00:00"
OOS_END = "2026-10-31T16:00:00+00:00"
SAMPLE_DATES = {f"{y:04d}-{m:02d}-01" for y, m in
                [(2025, m) for m in range(10, 13)] + [(2026, m) for m in range(1, 11)]}
L2_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}

def ms(iso):
    return int(datetime.fromisoformat(iso).timestamp() * 1000)

def percentile(values, p):
    if not values:
        return None
    a = sorted(values)
    return round(a[min(len(a)-1, max(0, int(math.ceil(p*len(a))-1)))], 8)

def main():
    months = list(sim.months_between("2023-01", "2026-10"))
    data, errors = {}, {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(sim.load_symbol, s, months, Path("research-output")): s for s in SYMBOLS}
        for f in as_completed(futures):
            symbol = futures[f]
            try:
                _, funding, marks = f.result()
                data[symbol] = {"fund": funding, "marks": marks}
                print("LOADED", symbol, len(funding), len(marks), flush=True)
            except Exception as exc:
                errors[symbol] = str(exc)
                print("SKIP", symbol, str(exc), flush=True)
    if len(data) < 8 or "BTCUSDT" not in data:
        raise RuntimeError("Insufficient usable symbols: " + json.dumps(errors))
    data = {s: data[s] for s in sorted(data)}
    event_times = sorted(t for s in data for t in data[s]["fund"]
                         if sum(t in data[z]["fund"] for z in data) >= math.ceil(.8*len(data)))
    if len(event_times) < 100:
        raise RuntimeError("Insufficient aligned funding events")
    start, end = ms(OOS_START), ms(OOS_END)
    result = sim.run(data, (start, end), 1.0, 5, slip_bp=2,
                     lookback_days=7, rebalance_days=7, tail_fraction=.20,
                     regime_policy=POLICY, regime_threshold_pct=5.0,
                     sideways_action="hold")
    log = result["rebalance_log"]
    all_orders = [o for event in log for o in event["orders"]]
    sample_events = [e for e in log if e["time_utc"][:10] in SAMPLE_DATES]
    sample_orders = [o for e in sample_events for o in e["orders"]]
    per_symbol = {}
    for symbol in sorted(data):
        vals = [o["notional_usdt"] for o in all_orders if o["symbol"] == symbol]
        sample_vals = [o["notional_usdt"] for o in sample_orders if o["symbol"] == symbol]
        per_symbol[symbol] = {
            "oos_order_count": len(vals),
            "oos_order_notional_usdt": {"min": min(vals) if vals else None,
                "median": percentile(vals, .5), "p90": percentile(vals, .9),
                "max": max(vals) if vals else None},
            "first_of_month_sample_order_count": len(sample_vals),
            "first_of_month_sample_notional_usdt": {"min": min(sample_vals) if sample_vals else None,
                "median": percentile(sample_vals, .5), "max": max(sample_vals) if sample_vals else None}
        }
    report = {
        "experiment": "EXP-017-MEAFLOW72-REAL-REBALANCE-SIGNAL-ALIGNMENT-AUDIT",
        "purpose": "Identify actual frozen MEAFLOW-72 OOS rebalance timestamps and per-symbol order sizes before any L2 execution replay.",
        "strategy_branch": "MEAFLOW-72",
        "audit_branch": "research/meaflow-exp017-signal-alignment-audit-v1",
        "source": "Official free Binance Vision monthly fundingRate and 1h markPriceKlines",
        "oos_period_utc": {"start": OOS_START, "end": OOS_END},
        "configuration": {"capital_usdt": 100, "leverage": 1,
            "lookback_days": 7, "rebalance_days": 7, "tail_fraction": .20,
            "regime": "BTC trailing 30d mark-price return, +/-5%, last completed hourly candle",
            "policy": POLICY, "sideways_action": "hold",
            "fee_bp_one_way": 5, "slippage_bp_one_way": 2},
        "data_errors": errors,
        "loaded_symbols": list(data),
        "strategy_replay_metrics": {k: result[k] for k in
            ("start_equity_usdt", "end_equity_usdt", "net_return_pct",
             "max_drawdown_pct", "rebalance_count", "hourly_adverse_checks",
             "liquidated", "trading_fees_usdt", "slippage_usdt")},
        "rebalance_event_count": len(log),
        "rebalance_events_with_orders": sum(bool(e["orders"]) for e in log),
        "total_order_delta_count": len(all_orders),
        "monthly_l2_sample_dates_in_oos": sorted(SAMPLE_DATES),
        "matched_first_of_month_rebalance_events": len(sample_events),
        "matched_first_of_month_order_count": len(sample_orders),
        "matched_first_of_month_events": sample_events,
        "per_symbol_order_size_summary": per_symbol,
        "l2_symbol_coverage": sorted(L2_SYMBOLS),
        "interpretation_limits": [
            "The order deltas are target changes at the simulator's funding-event mark, not exchange fills.",
            "The audit uses the already-inspected MEAFLOW-72 OOS window; it is not a new unseen profitability result.",
            "Only BTC, ETH and SOL have been covered by the EXP-015 event-level L2 pilot; other strategy symbols have no L2 replay coverage here.",
            "A first-of-month L2 sample is useful only when an actual rebalance occurs on that UTC date; no date/time matching is assumed.",
            "Actual order sizes must replace EXP-015's fixed 100 USDT probes before any fill-rate transfer is attempted.",
            "No strategy files on MEAFLOW-72 or MEAFLOW-52 are modified."
        ]
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp017_signal_alignment_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT research-results/exp017_signal_alignment_audit.json", flush=True)

if __name__ == "__main__":
    main()
