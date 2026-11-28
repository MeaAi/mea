#!/usr/bin/env python3
"""EXP-029: exploratory bull-flat regime policy screen on the 2021-2022 historical window.

Loads 2021-09 context plus 2021-10..2022-12 monthly Binance Vision
fundingRate and 1h markPriceKlines for the frozen 13-symbol universe.
No strategy files or live endpoints are used.
"""
import json, math, hashlib, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import exp025_forward_simulator as sim

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull": "both", "bear": "short_only", "sideways": "hold", "unknown": "flat"}
BULL_FLAT_POLICY = {"bull": "flat", "bear": "short_only", "sideways": "hold", "unknown": "flat"}
START = "2021-10-01T00:00:00+00:00"
END = "2022-12-31T23:00:00+00:00"
CONTEXT_START_MONTH = "2021-09"
END_MONTH = "2022-12"
OUT = Path("research-results/exp029_bull_flat_policy_screen.json")
DAY = 86400000

def ms(v):
    return int(datetime.fromisoformat(v).timestamp() * 1000)

def regime_at(data, btc_times, ts):
    j = __import__("bisect").bisect_right(btc_times, ts) - 1
    k = __import__("bisect").bisect_right(btc_times, ts - 30 * DAY) - 1
    if j < 0 or k < 0:
        return "unknown"
    btc = data["BTCUSDT"]["marks"]
    ret = btc[btc_times[j]][3] / btc[btc_times[k]][3] - 1
    return "bull" if ret > .05 else ("bear" if ret < -.05 else "sideways")

def supplement_daily_mark(symbol, date, root):
    name = f"{symbol}-1h-{date}.zip"
    url = sim.BASE.replace("/monthly", "/daily") + f"/markPriceKlines/{symbol}/1h/{name}"
    path = root / "cache" / symbol / "mark_daily" / name
    sim.download(url, path)
    checksum_path = Path(str(path) + ".CHECKSUM")
    sim.download(url + ".CHECKSUM", checksum_path)
    tokens = checksum_path.read_text(encoding="utf-8").strip().split()
    if not tokens:
        raise RuntimeError(f"Empty SHA-256 sidecar for {name}")
    expected = tokens[0].lower()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError(f"SHA-256 mismatch for daily supplement {name}: {digest} != {expected}")
    rows = sim.readzip(path, "mark")
    return rows, {"archive": name, "sha256": digest, "bytes": path.stat().st_size, "rows": len(rows)}

def metrics(v):
    keys = ("start_equity_usdt", "end_equity_usdt", "net_return_pct",
            "max_drawdown_pct", "liquidated", "liquidation_time_utc",
            "trading_fees_usdt", "slippage_usdt", "rebalance_count",
            "hourly_adverse_checks", "hourly_sideways_exits")
    return {k: v[k] for k in keys}

def main():
    months = list(sim.months_between(CONTEXT_START_MONTH, END_MONTH))
    root = Path("research-output")
    data, errors, monthly_meta = {}, {}, {}
    with ThreadPoolExecutor(max_workers=13) as pool:
        futures = {pool.submit(sim.load_symbol, s, months, root): s for s in SYMBOLS}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                _, funding_raw, marks = future.result()
                # Binance fundingTime can carry millisecond serialization offsets
                # from the exact hourly settlement boundary. Normalize only within 10 ms.
                funding = {}
                offset_hist = {}
                for ts, rate in funding_raw.items():
                    hour_ts = round(ts / 3600000) * 3600000
                    offset = ts - hour_ts
                    if abs(offset) > 100:
                        raise RuntimeError(f"Funding timestamp offset exceeds 100 ms: {symbol} {ts} offset={offset}")
                    offset_hist[str(offset)] = offset_hist.get(str(offset), 0) + 1
                    if hour_ts in funding:
                        raise RuntimeError(f"Funding timestamp collision after hourly normalization: {symbol} {hour_ts}")
                    funding[hour_ts] = rate
                data[symbol] = {"fund": funding, "marks": marks}
                monthly_meta[symbol] = {
                    "raw_funding_records": len(funding_raw),
                    "funding_records": len(funding),
                    "funding_timestamp_offset_ms_histogram": offset_hist,
                    "hourly_mark_bars": len(marks),
                    "first_funding_utc": datetime.fromtimestamp(min(funding)/1000, timezone.utc).isoformat() if funding else None,
                    "last_funding_utc": datetime.fromtimestamp(max(funding)/1000, timezone.utc).isoformat() if funding else None,
                    "first_mark_utc": datetime.fromtimestamp(min(marks)/1000, timezone.utc).isoformat() if marks else None,
                    "last_mark_utc": datetime.fromtimestamp(max(marks)/1000, timezone.utc).isoformat() if marks else None,
                }
                print("LOADED", symbol, "funding", len(funding), "mark_bars", len(marks), flush=True)
            except Exception as exc:
                errors[symbol] = str(exc)
                print("FAILED", symbol, str(exc), flush=True)

    if len(data) != len(SYMBOLS) or "BTCUSDT" not in data:
        raise RuntimeError("BLOCKED: not all 13 frozen-universe symbols loaded: " + json.dumps(errors))
    data = {s: data[s] for s in sorted(data)}
    first, last = ms(START), ms(END)
    expected_hours = list(range(first, last + 1, 3600000))
    daily_supplements = {}
    supplement_errors = {}
    for symbol in sorted(data):
        actual = set(data[symbol]["marks"])
        missing_before = [t for t in expected_hours if t not in actual]
        dates_to_supplement = sorted({datetime.fromtimestamp(t/1000, timezone.utc).strftime("%Y-%m-%d") for t in missing_before})
        daily_supplements[symbol] = {}
        for date in dates_to_supplement:
            try:
                rows, meta = supplement_daily_mark(symbol, date, root)
                data[symbol]["marks"].update(rows)
                daily_supplements[symbol][date] = meta
            except Exception as exc:
                supplement_errors.setdefault(symbol, []).append({"date": date, "error": str(exc)})
        actual = set(data[symbol]["marks"])
        missing = [t for t in expected_hours if t not in actual]
        gap_ranges = []
        gap_start = gap_prev = None
        for ts in missing:
            if gap_start is None:
                gap_start = gap_prev = ts
            elif ts == gap_prev + 3600000:
                gap_prev = ts
            else:
                gap_ranges.append({
                    "start_utc": datetime.fromtimestamp(gap_start/1000, timezone.utc).isoformat(),
                    "end_utc_inclusive": datetime.fromtimestamp(gap_prev/1000, timezone.utc).isoformat(),
                    "missing_hours": int((gap_prev-gap_start)/3600000)+1
                })
                gap_start = gap_prev = ts
        if gap_start is not None:
            gap_ranges.append({
                "start_utc": datetime.fromtimestamp(gap_start/1000, timezone.utc).isoformat(),
                "end_utc_inclusive": datetime.fromtimestamp(gap_prev/1000, timezone.utc).isoformat(),
                "missing_hours": int((gap_prev-gap_start)/3600000)+1
            })
        monthly_meta[symbol]["evaluation_expected_hourly_bars"] = len(expected_hours)
        monthly_meta[symbol]["evaluation_actual_hourly_bars"] = len(expected_hours)-len(missing)
        monthly_meta[symbol]["evaluation_missing_hourly_bars"] = len(missing)
        monthly_meta[symbol]["evaluation_mark_coverage_pct"] = round(100*(len(expected_hours)-len(missing))/len(expected_hours),4)
        monthly_meta[symbol]["evaluation_missing_hour_ranges"] = gap_ranges
        monthly_meta[symbol]["daily_supplements"] = daily_supplements[symbol]
    if supplement_errors:
        raise RuntimeError("BLOCKED: daily mark supplements failed checksum/download: " + json.dumps(supplement_errors))
    unresolved = {s: monthly_meta[s]["evaluation_missing_hourly_bars"] for s in data if monthly_meta[s]["evaluation_missing_hourly_bars"]}
    if unresolved:
        raise RuntimeError("BLOCKED: hourly mark gaps remain after daily supplements: " + json.dumps(unresolved))
    all_times = sorted(set(t for s in data for t in data[s]["fund"] if first <= t <= last))
    required = math.ceil(.8 * len(data))
    coverage = {t: sum(t in data[s]["fund"] and t in data[s]["marks"] for s in data) for t in all_times}
    usable_events = [t for t in all_times if coverage[t] >= 1]
    aligned_80pct = [t for t in all_times if coverage[t] >= required]
    full_coverage_events = [t for t in all_times if coverage[t] == len(data)]
    if len(usable_events) < 100:
        raise RuntimeError("BLOCKED: fewer than 100 usable per-symbol funding events: " + str(len(usable_events)))

    period = (first, last)
    baseline = sim.run(data, period, 1.0, 5, slip_bp=2,
        lookback_days=7, rebalance_days=7, tail_fraction=.20,
        regime_policy=POLICY, regime_threshold_pct=5.0, sideways_action="hold")
    flat_control = sim.run(data, period, 1.0, 5, slip_bp=2,
        lookback_days=7, rebalance_days=7, tail_fraction=.20,
        regime_policy=POLICY, regime_threshold_pct=5.0, sideways_action="flat")
    unfiltered = sim.run(data, period, 1.0, 5, slip_bp=2,
        lookback_days=7, rebalance_days=7, tail_fraction=.20,
        side_mode="both", regime_policy=None, regime_threshold_pct=5.0,
        sideways_action="flat")
    bull_flat = sim.run(data, period, 1.0, 5, slip_bp=2,
        lookback_days=7, rebalance_days=7, tail_fraction=.20,
        regime_policy=BULL_FLAT_POLICY, regime_threshold_pct=5.0,
        sideways_action="hold")

    fee_sensitivity = {}
    for fee in (2, 5, 8):
        v = sim.run(data, period, 1.0, fee, slip_bp=2,
            lookback_days=7, rebalance_days=7, tail_fraction=.20,
            regime_policy=POLICY, regime_threshold_pct=5.0, sideways_action="hold")
        fee_sensitivity[f"fee_{fee}bp_one_way"] = metrics(v)

    btc_times = sorted(data["BTCUSDT"]["marks"])
    occupancy = {k: 0 for k in ("bull", "bear", "sideways", "unknown")}
    for t in btc_times:
        if first <= t <= last:
            occupancy[regime_at(data, btc_times, t - 3600000)] += 1
    total_hours = sum(occupancy.values())
    occupancy_pct = {k: round(v / total_hours * 100, 3) if total_hours else 0 for k, v in occupancy.items()}

    bull_flat_fee_sensitivity = {}
    for fee in (2, 5, 8):
        v = sim.run(data, period, 1.0, fee, slip_bp=2,
            lookback_days=7, rebalance_days=7, tail_fraction=.20,
            regime_policy=BULL_FLAT_POLICY, regime_threshold_pct=5.0,
            sideways_action="hold")
        bull_flat_fee_sensitivity[f"fee_{fee}bp_one_way"] = metrics(v)

    rebalance_events = {}
    for regime in ("bull", "bear", "sideways", "unknown"):
        events = [x for x in baseline["rebalance_log"] if x["regime"] == regime]
        rebalance_events[regime] = {
            "rebalance_count": len(events),
            "order_deltas": sum(len(x["orders"]) for x in events),
            "turnover_usdt": round(sum(x["turnover_usdt"] for x in events), 6)
        }

    comparison = {
        "bull_flat_vs_frozen_baseline_return_delta_pp": round(bull_flat["net_return_pct"] - baseline["net_return_pct"], 4),
        "bull_flat_vs_frozen_baseline_dd_delta_pp": round(bull_flat["max_drawdown_pct"] - baseline["max_drawdown_pct"], 4),
        "bull_flat_vs_frozen_baseline_joint_gate_passed": bull_flat["net_return_pct"] > baseline["net_return_pct"] and bull_flat["max_drawdown_pct"] > baseline["max_drawdown_pct"],
        "bull_flat_vs_unfiltered_return_delta_pp": round(bull_flat["net_return_pct"] - unfiltered["net_return_pct"], 4),
        "bull_flat_vs_unfiltered_dd_delta_pp": round(bull_flat["max_drawdown_pct"] - unfiltered["max_drawdown_pct"], 4),
        "bull_flat_vs_unfiltered_joint_gate_passed": bull_flat["net_return_pct"] > unfiltered["net_return_pct"] and bull_flat["max_drawdown_pct"] > unfiltered["max_drawdown_pct"]
    }

    bull_flat_rebalance_events = {}
    for regime in ("bull", "bear", "sideways", "unknown"):
        selected = [x for x in bull_flat["rebalance_log"] if x["regime"] == regime]
        bull_flat_rebalance_events[regime] = {
            "rebalance_count": len(selected),
            "order_deltas": sum(len(x["orders"]) for x in selected),
            "turnover_usdt": round(sum(x["turnover_usdt"] for x in selected), 6)
        }

    report = {
        "experiment": "EXP-029-MEAFLOW72-BULL-FLAT-REGIME-POLICY-SCREEN",
        "status": "completed",
        "research_branch": "research/exp029-bull-flat-regime-policy-v1",
        "strategy_branch": "MEAFLOW-72 frozen read-only",
        "data_source": "Binance Vision USD-M monthly fundingRate + 1h markPriceKlines; 2021-09 lookback context; 2021-10-01 through 2022-12-31 UTC evaluation",
        "period_utc": {"start": START, "end": END},
        "configuration": {
            "initial_capital_usdt": 100, "leverage": 1,
            "lookback_days": 7, "rebalance_days": 7, "tail_fraction": .20,
            "regime": "BTC trailing 30d mark-price return +/-5%, last completed hourly candle",
            "regime_policy": POLICY, "sideways_action": "hold",
            "fee_bp_one_way": 5, "slippage_bp_one_way": 2,
            "symbols": SYMBOLS
        },
        "data_quality": {
            "symbols_requested": SYMBOLS, "symbols_loaded": list(data),
            "monthly_archives_per_symbol": len(months) * 2,
            "context_months": months,
            "funding_events_in_window": len(all_times),
            "usable_funding_events_any_symbol": len(usable_events),
            "events_with_80pct_symbol_coverage": len(aligned_80pct),
            "events_with_full_13_symbol_coverage": len(full_coverage_events),
            "daily_mark_supplement_archive_count": sum(len(v) for v in daily_supplements.values()),
            "required_symbols_per_event": required,
            "event_coverage_histogram": {str(n): sum(v == n for v in coverage.values()) for n in range(len(data)+1) if any(v == n for v in coverage.values())},
            "errors": errors, "per_symbol": monthly_meta
        },
        "hypothesis": "Bull-regime net contribution was negative in EXP-028; setting bull exposure to flat may improve both net return and hourly adverse-mark max DD.",
        "variant_policy": BULL_FLAT_POLICY,
        "frozen_meaflow72_metrics": metrics(baseline),
        "bull_flat_variant_metrics": metrics(bull_flat),
        "unfiltered_control_metrics": metrics(unfiltered),
        "sideways_flat_control_metrics": metrics(flat_control),
        "comparisons": comparison,
        "fee_sensitivity_frozen_policy": fee_sensitivity,
        "fee_sensitivity_bull_flat_variant": bull_flat_fee_sensitivity,
        "hourly_market_regime_occupancy": {
            "hours": occupancy, "percent": occupancy_pct, "total_hours": total_hours
        },
        "rebalance_events_by_regime_frozen_policy": rebalance_events,
        "rebalance_events_by_regime_bull_flat_variant": bull_flat_rebalance_events,
        "market_regime_attribution_frozen_policy": baseline["market_regime_attribution"],
        "market_regime_attribution_bull_flat_variant": bull_flat["market_regime_attribution"],
        "entry_regime_attribution_bull_flat_variant": bull_flat["entry_regime_attribution"],
        "symbol_attribution_frozen_policy": baseline["symbol_attribution"],
        "symbol_attribution_bull_flat_variant": bull_flat["symbol_attribution"],
        "rebalance_log_frozen_policy": baseline["rebalance_log"],
        "rebalance_log_bull_flat_variant": bull_flat["rebalance_log"],
        "limitations": [
            "This is a hypothesis screen on the same 2021-2022 window that motivated the bull-flat idea; it is not independent confirmation or a future/live forward test.",
            "Monthly archive ZIP CRC is checked by the shared loader; SHA-256 sidecar checksums are not required by this evaluator. FundingTime timestamps are normalized to the nearest hour only when the offset is <=100 ms; any larger offset or collision blocks the run. The simulator processes each symbol settlement independently whenever that symbol has a matching mark, including 4-hour funding schedules; it does not discard symbol-specific events merely because other symbols do not settle simultaneously.",
            "Hourly OHLC adverse-mark DD and liquidation remain approximations, not Binance's exact portfolio margin engine.",
            "Fixed 2 bp one-way slippage; no event-level L2 fills, partial fills, market impact, or dynamic funding execution costs.",
            "Historical listing dates and universe composition can introduce survivorship/availability bias; report per-symbol data coverage."
        ]
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("EXP029 BASELINE", json.dumps(metrics(baseline)), flush=True)
    print("EXP029 BULL_FLAT", json.dumps(metrics(bull_flat)), flush=True)
    print("EXP029 REGIMES", json.dumps({"occupancy": occupancy, "frozen": rebalance_events, "bull_flat": bull_flat_rebalance_events}), flush=True)
    print("EXP029 COMPARISON", json.dumps(comparison), flush=True)

if __name__ == "__main__":
    main()
