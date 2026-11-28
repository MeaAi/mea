#!/usr/bin/env python3
"""EXP-033: fixed 7d relative-momentum gate robustness across prior 2023-2026 windows."""
import json, math, hashlib, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import exp025_forward_simulator as sim

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull": "both", "bear": "short_only", "sideways": "hold", "unknown": "flat"}
WINDOWS = {
    "2023": ("2023-01-01T00:00:00+00:00", "2023-12-31T23:00:00+00:00"),
    "2024": ("2024-01-01T00:00:00+00:00", "2024-12-31T23:00:00+00:00"),
    "2025_jan_sep": ("2025-01-01T08:00:00+00:00", "2025-09-06T16:00:00+00:00"),
    "late_2025_2026": ("2025-09-07T00:00:00+00:00", "2026-10-31T16:00:00+00:00"),
}
CONTEXT_START_MONTH = "2022-12"
END_MONTH = "2026-10"
OUT = Path("research-results/exp033_relative_momentum_robustness.json")
DAY = 86400000

def ms(v):
    return int(datetime.fromisoformat(v).timestamp() * 1000)

def regime_at(data, btc_times, ts):
    import bisect
    j = bisect.bisect_right(btc_times, ts) - 1
    k = bisect.bisect_right(btc_times, ts - 30 * DAY) - 1
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

def coverage_for_window(data, first, last):
    all_times = sorted(set(t for s in data for t in data[s]["fund"] if first <= t <= last))
    coverage = {t: sum(t in data[s]["fund"] and t in data[s]["marks"] for s in data) for t in all_times}
    usable = [t for t in all_times if coverage[t] >= 1]
    broad = [t for t in all_times if coverage[t] >= math.ceil(.8 * len(data))]
    full = [t for t in all_times if coverage[t] == len(data)]
    return {
        "funding_event_union": len(all_times),
        "usable_events_any_symbol": len(usable),
        "events_with_80pct_symbol_coverage": len(broad),
        "events_with_full_13_symbol_coverage": len(full),
        "coverage_histogram": {str(n): sum(v == n for v in coverage.values()) for n in range(len(data)+1) if any(v == n for v in coverage.values())}
    }

def regime_occupancy(data, first, last):
    btc_times = sorted(data["BTCUSDT"]["marks"])
    counts = {k: 0 for k in ("bull", "bear", "sideways", "unknown")}
    for t in btc_times:
        if first <= t <= last:
            counts[regime_at(data, btc_times, t - 3600000)] += 1
    total = sum(counts.values())
    return {"hours": counts, "percent": {k: round(v/total*100,3) if total else 0 for k,v in counts.items()}, "total_hours": total}

def regime_rebalances(result):
    out = {}
    for regime in ("bull", "bear", "sideways", "unknown"):
        events = [x for x in result["rebalance_log"] if x["regime"] == regime]
        out[regime] = {
            "rebalance_count": len(events),
            "order_deltas": sum(len(x["orders"]) for x in events),
            "turnover_usdt": round(sum(x["turnover_usdt"] for x in events), 6)
        }
    return out

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
                funding, offset_hist = {}, {}
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
                    "hourly_mark_bars_before_daily_supplements": len(marks),
                    "first_funding_utc": datetime.fromtimestamp(min(funding)/1000, timezone.utc).isoformat() if funding else None,
                    "last_funding_utc": datetime.fromtimestamp(max(funding)/1000, timezone.utc).isoformat() if funding else None,
                }
                print("LOADED", symbol, "funding", len(funding), "mark_bars", len(marks), flush=True)
            except Exception as exc:
                errors[symbol] = str(exc)
                print("FAILED", symbol, str(exc), flush=True)
    if len(data) != len(SYMBOLS) or "BTCUSDT" not in data:
        raise RuntimeError("BLOCKED: not all 13 frozen-universe symbols loaded: " + json.dumps(errors))
    data = {s: data[s] for s in sorted(data)}

    earliest = min(ms(v[0]) for v in WINDOWS.values())
    latest = max(ms(v[1]) for v in WINDOWS.values())
    expected_hours = list(range(earliest, latest + 1, 3600000))
    daily_supplements, supplement_errors = {}, {}
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
        missing_after = [t for t in expected_hours if t not in data[symbol]["marks"]]
        monthly_meta[symbol]["evaluation_expected_hourly_bars"] = len(expected_hours)
        monthly_meta[symbol]["evaluation_actual_hourly_bars"] = len(expected_hours)-len(missing_after)
        monthly_meta[symbol]["evaluation_missing_hourly_bars"] = len(missing_after)
        monthly_meta[symbol]["evaluation_mark_coverage_pct"] = round(100*(len(expected_hours)-len(missing_after))/len(expected_hours),4)
        monthly_meta[symbol]["daily_supplements"] = daily_supplements[symbol]
    if supplement_errors:
        raise RuntimeError("BLOCKED: daily mark supplements failed checksum/download: " + json.dumps(supplement_errors))
    unresolved = {s: monthly_meta[s]["evaluation_missing_hourly_bars"] for s in data if monthly_meta[s]["evaluation_missing_hourly_bars"]}
    if unresolved:
        raise RuntimeError("BLOCKED: hourly mark gaps remain after daily supplements: " + json.dumps(unresolved))

    results = {}
    for label, (start_text, end_text) in WINDOWS.items():
        first, last = ms(start_text), ms(end_text)
        period = (first, last)
        base = sim.run(data, period, 1.0, 5, slip_bp=2,
            lookback_days=7, rebalance_days=7, tail_fraction=.20,
            regime_policy=POLICY, regime_threshold_pct=5.0, sideways_action="hold")
        candidate = sim.run(data, period, 1.0, 5, slip_bp=2,
            lookback_days=7, rebalance_days=7, tail_fraction=.20,
            regime_policy=POLICY, regime_threshold_pct=5.0, sideways_action="hold",
            relative_momentum_gate=True)
        comp = {
            "return_delta_vs_frozen_pp": round(candidate["net_return_pct"] - base["net_return_pct"], 4),
            "max_dd_delta_vs_frozen_pp": round(candidate["max_drawdown_pct"] - base["max_drawdown_pct"], 4),
            "joint_acceptance_gate_passed": candidate["net_return_pct"] > base["net_return_pct"] and candidate["max_drawdown_pct"] > base["max_drawdown_pct"]
        }
        results[label] = {
            "period_utc": {"start": start_text, "end": end_text},
            "data_coverage": coverage_for_window(data, first, last),
            "regime_occupancy": regime_occupancy(data, first, last),
            "frozen_baseline_metrics": metrics(base),
            "relative_momentum_gate_metrics": metrics(candidate),
            "comparison": comp,
            "frozen_baseline_rebalances_by_regime": regime_rebalances(base),
            "relative_momentum_gate_rebalances_by_regime": regime_rebalances(candidate),
            "frozen_baseline_regime_attribution": base["market_regime_attribution"],
            "relative_momentum_gate_regime_attribution": candidate["market_regime_attribution"],
            "frozen_baseline_symbol_attribution": base["symbol_attribution"],
            "relative_momentum_gate_symbol_attribution": candidate["symbol_attribution"]
        }
        print("EXP033", label, json.dumps({"base":metrics(base),"relative_momentum_gate":metrics(candidate),"comparison":comp}), flush=True)

    report = {
        "experiment": "EXP-033-RELATIVE-MOMENTUM-GATE-MULTIWINDOW-ROBUSTNESS",
        "status": "completed",
        "research_branch": "research/exp033-relative-momentum-robustness-v1",
        "candidate": "7d relative-momentum sign gate on original funding-ranked tails; selected only from EXP-032 2021-2022 screen; no further tuning.",
        "previously_inspected_windows": True,
        "strategy_branch": "MEAFLOW-72 frozen read-only",
        "data_source": "Binance Vision USD-M monthly fundingRate + 1h markPriceKlines, with SHA-256-verified daily mark supplements for missing hours",
        "context_months": months,
        "configuration": {
            "initial_capital_usdt": 100, "leverage": 1,
            "lookback_days": 7, "rebalance_days": 7, "tail_fraction": .20,
            "regime": "BTC trailing 30d mark-price return +/-5%, last completed hourly candle",
            "regime_policy": POLICY, "sideways_action": "hold",
            "fee_bp_one_way": 5, "slippage_bp_one_way": 2,
            "symbols": SYMBOLS,
            "relative_momentum_gate": "longs require positive 7d return relative to BTC; shorts require negative 7d return relative to BTC; as-of last completed hourly candle"
        },
        "data_quality": {
            "symbols_loaded": list(data),
            "monthly_archives_per_symbol": len(months)*2,
            "daily_mark_supplement_archive_count": sum(len(v) for v in daily_supplements.values()),
            "errors": errors,
            "per_symbol": monthly_meta
        },
        "window_results": results,
        "all_windows_joint_gate_passed": all(v["comparison"]["joint_acceptance_gate_passed"] for v in results.values()),
        "limitations": [
            "2023-2026 windows were previously inspected in prior research; this is a robustness extension, not pristine OOS.",
            "No threshold retuning was performed; only the 24h half-life selected in EXP-030 was tested.",
            "Hourly OHLC adverse-mark DD and liquidation remain approximations, not Binance's exact portfolio margin engine.",
            "Fixed 2 bp one-way slippage; no event-level L2 fills, partial fills, or market impact."
        ]
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("EXP033 SUMMARY", json.dumps({k:v["comparison"] for k,v in results.items()}), flush=True)

if __name__ == "__main__":
    main()
