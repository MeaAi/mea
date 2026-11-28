#!/usr/bin/env python3
"""EXP-025: untouched November 2026 forward validation of frozen MEAFLOW-72.

Loads October monthly Binance Vision history for lookback/regime context and
November daily public archives. Only the research copy relaxes the simulator's
minimum event-count guard from 100 to 60 so this 27-day forward window can run.
No strategy parameters or MEAFLOW-72 files are modified.
"""
import json, math, hashlib, urllib.request, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import exp025_forward_simulator as sim

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull": "both", "bear": "short_only", "sideways": "hold", "unknown": "flat"}
START = "2026-11-01T00:00:00+00:00"
END = "2026-11-26T23:00:00+00:00"
OUT = Path("research-results/exp025_november_forward_validation.json")
DAILY_BASE = sim.BASE.replace("/monthly", "/daily")
DATES = [(datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(26)]

def ms(value):
    return int(datetime.fromisoformat(value).timestamp() * 1000)

def verified_archive(url, path, kind):
    # Binance publishes a sibling SHA-256 CHECKSUM for each ZIP archive.
    sim.download(url, path)
    with urllib.request.urlopen(url + ".CHECKSUM", timeout=60) as response:
        checksum_text = response.read().decode("utf-8").strip()
    expected = []
    for line in checksum_text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[-1].lstrip("*") == path.name:
            expected.append(fields[0].lower())
    if len(expected) != 1:
        raise RuntimeError(f"Expected exactly one checksum entry for {path.name}; found {len(expected)}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected[0]:
        raise RuntimeError(f"SHA-256 mismatch for {path.name}: expected {expected[0]}, got {actual}")
    return sim.readzip(path, kind)  # also validates ZIP CRC


def load_funding_rest(symbol, start, end):
    # Public, unauthenticated Binance USD-M mirror; response schema matches Binance.
    url = 'https://api-dev.pipai.org/fapi/v1/fundingRate?symbol=' + symbol + '&startTime=' + str(ms(start)) + '&endTime=' + str(ms(end)) + '&limit=1000'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    last_error = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                rows = json.loads(response.read().decode('utf-8'))
            break
        except Exception as exc:
            last_error = exc
            if attempt == 4: raise
            time.sleep(2 ** attempt)
    out = {}
    for row in rows:
        ts = int(row['fundingTime']); rate = float(row['fundingRate'])
        if ms(start) <= ts <= ms(end) and math.isfinite(rate): out[ts] = rate
    if not out: raise RuntimeError('Funding mirror returned no records for ' + symbol)
    return out

def load_symbol_forward(symbol):
    root = Path('research-output')
    _, funding, marks = sim.load_symbol(symbol, ['2026-10'], root)
    errors = []
    try:
        # Validate mirror against the complete October Vision monthly archive
        # before accepting November records; exact timestamp/rate equality required.
        oct_start, oct_end = "2026-10-01T00:00:00+00:00", "2026-10-31T23:59:59+00:00"
        mirror_oct = load_funding_rest(symbol, oct_start, oct_end)
        vision_oct = {t:r for t,r in funding.items() if ms(oct_start) <= t <= ms(oct_end)}
        common = set(mirror_oct) & set(vision_oct)
        if len(common) < 90 or any(mirror_oct[t] != vision_oct[t] for t in common):
            raise RuntimeError("Funding mirror failed October cross-check: common=" + str(len(common)))
        missing = set(vision_oct) ^ set(mirror_oct)
        if missing:
            raise RuntimeError("Funding mirror October timestamp population mismatch: " + str(len(missing)))
        november_raw = load_funding_rest(symbol, START, END)
        # API fundingTime carries 1-5 ms serialization offsets around exact hourly
        # settlements; normalize only when within 10 ms of an hour boundary.
        november = {}
        for ts, rate in november_raw.items():
            hour_ts = round(ts / 3600000) * 3600000
            if abs(ts - hour_ts) > 10:
                raise RuntimeError("Funding timestamp is not within 10 ms of an hourly settlement: " + str(ts))
            november[hour_ts] = rate
        if len(november) != len(november_raw):
            raise RuntimeError("Funding timestamp normalization collision for " + symbol)
        funding.update(november)
    except Exception as exc:
        errors.append({'date':'2026-11-01..26','kind':'validated_public_funding_mirror','error':str(exc)})
    for date in DATES:
        mark_name = f'{symbol}-1h-{date}.zip'
        mark_path = root / 'cache' / symbol / 'mark_daily' / mark_name
        mark_url = f'{DAILY_BASE}/markPriceKlines/{symbol}/1h/{mark_name}'
        try: marks.update(verified_archive(mark_url, mark_path, 'mark'))
        except Exception as exc: errors.append({'date':date,'kind':'daily_markPriceKlines','error':str(exc)})
    return symbol, funding, marks, errors

def main():
    data, errors = {}, {}
    with ThreadPoolExecutor(max_workers=13) as pool:
        futures = {pool.submit(load_symbol_forward, s): s for s in SYMBOLS}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                _, funding, marks, symbol_errors = future.result()
                data[symbol] = {"fund": funding, "marks": marks}
                if symbol_errors:
                    errors[symbol] = symbol_errors
                print("LOADED", symbol, "funding", len(funding), "marks", len(marks),
                      "daily_errors", len(symbol_errors), flush=True)
            except Exception as exc:
                errors[symbol] = [{"kind": "symbol_load", "error": str(exc)}]
                print("FAILED", symbol, str(exc), flush=True)

    if len(data) != len(SYMBOLS) or "BTCUSDT" not in data:
        raise RuntimeError("BLOCKED: incomplete 13-symbol universe or archive/checksum failure; no strategy run: " + json.dumps(errors))

    data = {s: data[s] for s in sorted(data)}
    first, last = ms(START), ms(END)
    all_times = sorted(set(t for s in data for t in data[s]["fund"] if first <= t <= last))
    # Diagnostics before enforcing the simulator's event-coverage guard.
    coverage = {t: sum(t in data[s]["fund"] and t in data[s]["marks"] for s in data) for t in all_times}
    nov_first, nov_last = ms(START), ms(END)
    nov_funding_counts = {s: sum(nov_first <= t <= nov_last for t in data[s]["fund"]) for s in sorted(data)}
    coverage_hist = {str(n): sum(v == n for v in coverage.values()) for n in range(len(data)+1) if any(v == n for v in coverage.values())}
    print("NOV_FUNDING_COUNTS", json.dumps(nov_funding_counts), flush=True)
    off_hour = [t for t in all_times if nov_first <= t <= nov_last and t % 3600000 != 0]
    print("OFF_HOUR_FUNDING_SAMPLE", [datetime.fromtimestamp(t/1000,timezone.utc).isoformat() for t in off_hour[:20]], flush=True)
    print("OFF_HOUR_MODULUS_MS", sorted(set(t % 3600000 for t in off_hour))[:20], flush=True)
    print("EVENT_COVERAGE_HISTOGRAM", json.dumps(coverage_hist), flush=True)
    required = math.ceil(.8 * len(data))
    aligned = [t for t in all_times if coverage[t] >= required]
    print("ALIGNED_EVENTS_AT_80PCT", len(aligned), "required_symbols", required, flush=True)
    if errors:
        raise RuntimeError("BLOCKED: one or more required archives failed checksum/download validation; no strategy run: " + json.dumps(errors))
    if len(aligned) < 60:
        raise RuntimeError(f"Only {len(aligned)} aligned forward funding events; need at least 60. Errors: {json.dumps(errors)}")

    result = sim.run(
        data, (first, last), 1.0, 5, slip_bp=2,
        lookback_days=7, rebalance_days=7, tail_fraction=.20,
        regime_policy=POLICY, regime_threshold_pct=5.0,
        sideways_action="hold",
    )
    # Matched control: identical inputs and regime policy, but flatten on sideways.
    control = sim.run(
        data, (first, last), 1.0, 5, slip_bp=2,
        lookback_days=7, rebalance_days=7, tail_fraction=.20,
        regime_policy=POLICY, regime_threshold_pct=5.0,
        sideways_action="flat",
    )
    # Unfiltered base funding-rank control: both long and short legs in every regime.
    unfiltered = sim.run(
        data, (first, last), 1.0, 5, slip_bp=2,
        lookback_days=7, rebalance_days=7, tail_fraction=.20,
        side_mode="both", regime_policy=None, regime_threshold_pct=5.0,
        sideways_action="flat",
    )
    unfiltered_comparison = {
        "net_return_delta_percentage_points": round(result["net_return_pct"] - unfiltered["net_return_pct"], 4),
        "max_drawdown_delta_percentage_points": round(result["max_drawdown_pct"] - unfiltered["max_drawdown_pct"], 4),
        "end_equity_delta_usdt": round(result["end_equity_usdt"] - unfiltered["end_equity_usdt"], 6),
        "acceptance_gate_passed_vs_unfiltered_control": (
            result["net_return_pct"] > unfiltered["net_return_pct"] and
            result["max_drawdown_pct"] > unfiltered["max_drawdown_pct"]
        )
    }
    comparison = {
        "net_return_delta_percentage_points": round(result["net_return_pct"] - control["net_return_pct"], 4),
        "max_drawdown_delta_percentage_points": round(result["max_drawdown_pct"] - control["max_drawdown_pct"], 4),
        "end_equity_delta_usdt": round(result["end_equity_usdt"] - control["end_equity_usdt"], 6),
        "acceptance_gate_passed_vs_sideways_flat_control": (
            result["net_return_pct"] > control["net_return_pct"] and
            result["max_drawdown_pct"] > control["max_drawdown_pct"]
        )
    }

    # EXP-027 exploratory per-symbol hard-stop screen. Each threshold is
    # compared with the identical frozen MEAFLOW-72 rules on this same window.
    stop_tests = {}
    for threshold in (1.0, 1.5, 2.0, 3.0, 5.0, 7.5):
        stopped = sim.run(
            data, (first, last), 1.0, 5, slip_bp=2,
            lookback_days=7, rebalance_days=7, tail_fraction=.20,
            regime_policy=POLICY, regime_threshold_pct=5.0,
            sideways_action="hold", position_stop_pct=threshold,
        )
        stop_tests[f"{threshold:g}%"] = {
            "metrics": {k: stopped[k] for k in (
                "end_equity_usdt", "net_return_pct", "max_drawdown_pct",
                "liquidated", "trading_fees_usdt", "slippage_usdt",
                "rebalance_count", "position_stop_count", "hourly_adverse_checks")},
            "stop_log": stopped["position_stop_log"],
            "comparison_vs_frozen_baseline": {
                "return_delta_percentage_points": round(stopped["net_return_pct"] - result["net_return_pct"], 4),
                "max_drawdown_delta_percentage_points": round(stopped["max_drawdown_pct"] - result["max_drawdown_pct"], 4),
                "joint_acceptance_gate_passed": (
                    stopped["net_return_pct"] > result["net_return_pct"] and
                    stopped["max_drawdown_pct"] > result["max_drawdown_pct"]
                )
            }
        }

    log = result["rebalance_log"]
    regime_events = {}
    for regime in ("bull", "bear", "sideways", "unknown"):
        selected = [e for e in log if e.get("regime") == regime]
        regime_events[regime] = {
            "rebalance_events": len(selected),
            "order_deltas": sum(len(e.get("orders", [])) for e in selected),
            "turnover_usdt": round(sum(e.get("turnover_usdt", 0) for e in selected), 6),
        }

    report = {
        "experiment": "EXP-027-MEAFLOW72-PER-SYMBOL-STOP-LOSS-SCREEN",
        "status": "completed_with_data_gaps" if errors else "completed",
        "strategy_branch": "MEAFLOW-72 (frozen, read-only)",
        "research_branch": "research/exp027-per-symbol-stop-loss-v1",
        "data_source": "October monthly Binance Vision context + November 1-26 daily markPriceKlines + public Binance USD-M fundingRate mirror, cross-checked against October Vision archives",
        "forward_period_utc": {"start": START, "end": END},
        "sample_scope": "PARTIAL NOVEMBER 1-26 UTC; not a full-month validation.",
        "configuration": {
            "capital_usdt": 100, "leverage": 1,
            "lookback_days": 7, "rebalance_days": 7, "tail_fraction": .20,
            "regime": "BTC trailing 30d mark-price return, +/-5%, last completed hourly candle",
            "regime_policy": POLICY, "sideways_action": "hold",
            "fee_bp_one_way": 5, "slippage_bp_one_way": 2,
            "simulator_guard": "Research-copy minimum aligned-event guard relaxed from 100 to 60; no strategy rule changed."
        },
        "data_quality": {
            "symbols_requested": SYMBOLS,
            "symbols_loaded": list(data),
            "daily_dates_requested": DATES,
            "aligned_funding_events": len(aligned),
            "required_symbols_per_event": required,
            "daily_archive_error_count": sum(len(v) for v in errors.values()),
            "errors_by_symbol": {k: len(v) for k, v in errors.items()},
            "errors_sample": [dict(symbol=k, **x) for k, vals in errors.items() for x in vals][:30],
        },
        "strategy_metrics": {k: result[k] for k in (
            "start_equity_usdt", "end_equity_usdt", "net_return_pct",
            "max_drawdown_pct", "liquidated", "liquidation_time_utc",
            "trading_fees_usdt", "slippage_usdt", "rebalance_count",
            "hourly_adverse_checks", "hourly_sideways_exits")},
        "matched_control": {
            "name": "same regime policy, flatten positions on sideways",
            "strategy_metrics": {k: control[k] for k in (
                "start_equity_usdt", "end_equity_usdt", "net_return_pct",
                "max_drawdown_pct", "liquidated", "liquidation_time_utc",
                "trading_fees_usdt", "slippage_usdt", "rebalance_count",
                "hourly_adverse_checks", "hourly_sideways_exits")},
            "comparison_vs_hold": comparison
        },
        "unfiltered_base_control": {
            "name": "base funding-rank control, both long and short legs in all regimes",
            "strategy_metrics": {k: unfiltered[k] for k in (
                "start_equity_usdt", "end_equity_usdt", "net_return_pct",
                "max_drawdown_pct", "liquidated", "liquidation_time_utc",
                "trading_fees_usdt", "slippage_usdt", "rebalance_count",
                "hourly_adverse_checks", "hourly_sideways_exits")},
            "comparison_vs_regime_policy": unfiltered_comparison
        },
        "exp027_per_symbol_stop_tests": {
            "hypothesis": "A hard adverse-price stop per symbol may reduce hourly adverse-mark drawdown without sacrificing net return.",
            "execution_rule": "Trigger when hourly mark OHLC crosses the stop from the position's weighted-average entry; fill at stop price, or at the worse bar open if the bar gaps through. Closed symbols remain flat until the next scheduled/regime rebalance. Fees and slippage are charged on stop-exit notional.",
            "thresholds": stop_tests,
            "limitations": [
                "Exploratory screening on the partial Nov 1-26 window only; no threshold is selected or promoted.",
                "Hourly OHLC cannot reveal intrabar path or stop queue/market impact; fills are modeled at stop/open plus fixed costs.",
                "Only three base rebalance events occurred in this window, all in bear regime."
            ]
        },
        "rebalance_events_by_regime": regime_events,
        "rebalance_log": log,
        "market_regime_attribution": result["market_regime_attribution"],
        "entry_regime_attribution": result["entry_regime_attribution"],
        "interpretation_limits": [
            "This is a partial new forward window after the previously inspected OOS period ended on 2026-10-31. November 27-30 are excluded.",
            "The forward sample covers 26 calendar days (Nov 1-26 inclusive) and contains few weekly rebalances; it is an early generalization check, not final validation.",
            "Execution still uses the existing 5 bp one-way fee and 2 bp one-way slippage assumptions; no new L2 replay is available for November in this experiment.",
            "Hourly OHLC adverse-mark drawdown remains a simulator approximation, not an exchange liquidation-engine result.",
            "No parameter tuning, strategy promotion, or changes to MEAFLOW-72/MEAFLOW-52 are made. EXP-027 stop thresholds are a separate exploratory screen only."
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("EXP025 METRICS", json.dumps(report["strategy_metrics"]), flush=True)
    print("EXP025 EVENTS", json.dumps(regime_events), flush=True)

if __name__ == "__main__":
    main()
