#!/usr/bin/env python3
"""MEAFLOW-72 bear-entry cohort attribution diagnostic.

Runs an unchanged MEAFLOW-72 copy on free Binance Vision data. The goal is
not to optimize a new policy, but to separate PnL by the regime in which
incremental position size was opened from the regime in which PnL accrued.
"""
import json, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import funding_carry_liquidation_fixed as sim

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull":"both", "bear":"short_only", "sideways":"hold", "unknown":"flat"}
WINDOWS = {
    "2023_calendar": ("2023-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
    "2024_calendar": ("2024-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00"),
    "2025_jan_to_sep": ("2025-01-01T00:00:00+00:00", "2025-09-06T18:24:00+00:00"),
    "2025_sep_to_2026_oct": ("2025-09-06T18:24:00+00:00", "2026-10-31T16:00:00+00:00"),
}
CONFIGS = {
    "uncapped": None,
    "bear_cap_20pct": {"bear": .20},
    "bear_cap_15pct": {"bear": .15},
}
def ms(s): return int(datetime.fromisoformat(s).timestamp() * 1000)
def iso(t): return datetime.fromtimestamp(t/1000, timezone.utc).isoformat()

def main():
    months = list(sim.months_between("2023-01", "2026-10"))
    data, errors = {}, {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(sim.load_symbol, s, months, Path("research-output")): s for s in SYMBOLS}
        for f in as_completed(futures):
            s = futures[f]
            try:
                _, funding, marks = f.result()
                data[s] = {"fund": funding, "marks": marks}
                print("LOADED", s, len(funding), len(marks), flush=True)
            except Exception as e:
                errors[s] = str(e)
                print("SKIP", s, str(e), flush=True)
    if len(data) < 8 or "BTCUSDT" not in data:
        raise RuntimeError("Insufficient symbols: " + json.dumps(errors))
    data = {s: data[s] for s in sorted(data)}
    aligned = sorted(t for s in data for t in data[s]["fund"]
                     if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data) >= math.ceil(.8*len(data)))
    report = {}
    keep = (
        "net_return_pct", "end_equity_usdt", "max_drawdown_pct",
        "maxdd_peak_time_utc", "maxdd_trough_time_utc", "rebalance_count",
        "liquidated", "price_pnl_usdt", "funding_pnl_usdt",
        "trading_fees_usdt", "slippage_usdt",
        "market_regime_attribution", "entry_regime_attribution",
        "entry_regime_attribution_note", "symbol_attribution",
    )
    for name, (a, b) in WINDOWS.items():
        lo, hi = ms(a), ms(b)
        events = [t for t in aligned if lo <= t <= hi]
        if len(events) < 100:
            report[name] = {"error":"insufficient aligned funding events", "event_count":len(events)}
            continue
        report[name] = {"period_utc":[iso(events[0]), iso(events[-1])], "event_count":len(events), "configs":{}}
        for label, cap in CONFIGS.items():
            result = sim.run(
                data, (events[0], events[-1]), 1.0, 5, slip_bp=2,
                lookback_days=7, rebalance_days=7, tail_fraction=.20,
                regime_policy=POLICY, regime_threshold_pct=5.0,
                sideways_action="hold", sideways_retention_fraction=1.0,
                max_symbol_exposure_pct=cap,
            )
            report[name]["configs"][label] = {k: result[k] for k in keep}
            print("RESULT", name, label, json.dumps(report[name]["configs"][label], separators=(",",":")), flush=True)
    output = {
        "experiment":"MEAFLOW-72 BTC trend severity entry-cohort attribution",
        "branch":"research/meaflow72-bear-cohort-attribution-v1",
        "parent":"research/meaflow72-regime-threshold-sensitivity-v1",
        "purpose":"Split entry cohorts by BTC trailing-30d mark-price return: bull_mild +5% to +10%, bull_strong >+10%, bear_mild -5% to -10%, bear_strong <-10%, sideways otherwise. Compare uncapped baseline with bear-only caps. No parameter optimization.",
        "source":"Free official Binance Vision monthly fundingRate + 1h markPriceKlines",
        "loaded_symbols":list(data), "data_errors":errors,
        "capital_usdt":100, "leverage":1,
        "costs":"5 bp fee one-way + 2 bp slippage one-way",
        "strategy":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d mark-price +/-5% regime; bull both, bear short-only, sideways hold, unknown flat.",
        "configs":CONFIGS,
        "windows":report,
        "interpretation_caution":[
            "Historical windows have been previously inspected and are exploratory, not pristine forward OOS.",
            "entry_regime_attribution assigns incremental position quantity to BTC trailing-30d return severity at opening; it reports price/funding PnL only and excludes execution costs.",
            "market_regime_attribution assigns price/funding PnL and execution costs to the regime in which they accrue/execute. Comparing the two is diagnostic, not an exact causal decomposition.",
            "Simulator uses 1h mark OHLC adverse-extreme stress, not Binance's tick-level liquidation engine; static 0.5% MMR and 1% liquidation-fee proxy.",
            "No maker queue/partial-fill model; fixed slippage; static 13-symbol universe survivorship bias."
        ]
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/meaflow72_bear_cohort_attribution.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print("REPORT research-results/meaflow72_bear_cohort_attribution.json", flush=True)

if __name__ == "__main__":
    main()
