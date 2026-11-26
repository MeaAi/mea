#!/usr/bin/env python3
"""EXP-014: frozen May-Jun 2024 order-flow calibration, independent Jul-Aug 2024 OOS.

Uses official Binance Vision USD-M monthly aggTrades/1m klines and daily
bookDepth percentage-band snapshots. Thresholds are fit ONLY on the pilot
period, then frozen for the later test period. No OOS fitting.
"""
import argparse, csv, gzip, glob, json, math
from pathlib import Path
from collections import defaultdict

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HORIZONS = (5, 15, 60)
ONE_WAY_FEE_BP = 5.0
ONE_WAY_SLIPPAGE_BP = 2.0
ROUND_TRIP_COST_BP = 2 * (ONE_WAY_FEE_BP + ONE_WAY_SLIPPAGE_BP)
INITIAL_EQUITY = 100.0

def load_files(pattern, symbol):
    out = {}
    for path in sorted(glob.glob(pattern)):
        if Path(path).name.split("-")[0] != symbol:
            continue
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                t = int(r["open_time_ms"])
                if t in out:
                    raise ValueError(f"{symbol}: duplicate timestamp {t} in {pattern}")
                out[t] = r
    return out

def quantile(values, q):
    xs = sorted(x for x in values if math.isfinite(x))
    if not xs:
        raise ValueError("No valid calibration values")
    return xs[min(len(xs)-1, max(0, math.ceil(q*len(xs))-1))]

def build_rows(flow, book):
    rows = []
    for t in sorted(set(flow) & set(book)):
        f, b = flow[t], book[t]
        try:
            bid = sum(float(b[k] or 0) for k in ("notional_1pct", "notional_2pct"))
            ask = sum(float(b[k] or 0) for k in ("notional_-1pct", "notional_-2pct"))
            buy = float(f["agg_taker_buy_quote"] or 0)
            sell = float(f["agg_taker_sell_quote"] or 0)
            whale_buy = float(f["whale_buy_quote"] or 0)
            whale_sell = float(f["whale_sell_quote"] or 0)
            op, close = float(f["open"]), float(f["close"])
        except (KeyError, ValueError):
            continue
        if bid + ask <= 0 or buy + sell <= 0 or whale_buy + whale_sell <= 0 or op <= 0:
            continue
        rows.append({
            "t": t, "open": op, "close": close,
            "obi": (bid-ask)/(bid+ask),
            "ofi": (buy-sell)/(buy+sell),
            "whale": (whale_buy-whale_sell)/(whale_buy+whale_sell),
        })
    return rows

def make_thresholds(pilot):
    return {k: {"q20": quantile([r[k] for r in pilot], .20),
                "q80": quantile([r[k] for r in pilot], .80)}
            for k in ("obi", "ofi", "whale")}

def sign(value, threshold):
    if value >= threshold["q80"]: return 1
    if value <= threshold["q20"]: return -1
    return 0

def strategy_signals(rows, thresholds):
    signals = defaultdict(list)
    for i, r in enumerate(rows):
        s = {k: sign(r[k], thresholds[k]) for k in ("obi", "ofi", "whale")}
        if s["obi"]: signals["obi_only"].append((i, s["obi"]))
        if s["ofi"]: signals["ofi_only"].append((i, s["ofi"]))
        if s["whale"]: signals["whale_only"].append((i, s["whale"]))
        if s["obi"] and s["ofi"] and s["obi"] == s["ofi"]:
            signals["obi_ofi_agreement"].append((i, s["obi"]))
        if s["ofi"] and s["whale"] and s["ofi"] == s["whale"]:
            signals["ofi_whale_agreement"].append((i, s["ofi"]))
        if s["obi"] and s["ofi"] and s["whale"] and s["obi"] == s["ofi"] == s["whale"]:
            signals["three_way_agreement"].append((i, s["ofi"]))
    return signals

def simulate(rows, candidates, horizon):
    equity = INITIAL_EQUITY
    peak = equity
    max_dd = 0.0
    next_free = 0
    trades, skipped_overlap, skipped_gap = [], 0, 0
    for i, direction in candidates:
        if i < next_free:
            skipped_overlap += 1
            continue
        if i + horizon >= len(rows) or i + 1 >= len(rows):
            skipped_gap += 1
            continue
        if rows[i+1]["t"] - rows[i]["t"] != 60000 or rows[i+horizon]["t"] - rows[i]["t"] != horizon*60000:
            skipped_gap += 1
            continue
        entry, exit_px = rows[i+1]["open"], rows[i+horizon]["close"]
        gross_bp = direction * (exit_px/entry - 1.0) * 10000
        net_bp = gross_bp - ROUND_TRIP_COST_BP
        notional = equity  # 100% of wallet equity at 1x; no leverage
        fees = notional * (2*ONE_WAY_FEE_BP) / 10000
        slippage = notional * (2*ONE_WAY_SLIPPAGE_BP) / 10000
        pnl = notional * net_bp / 10000
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak-equity)/peak if peak else 0)
        trades.append({"signal_time_ms": rows[i]["t"], "entry_time_ms": rows[i+1]["t"],
                       "exit_time_ms": rows[i+horizon]["t"], "direction": direction,
                       "gross_bp": gross_bp, "net_bp": net_bp, "notional_usdt": notional,
                       "fees_usdt": fees, "slippage_usdt": slippage, "net_pnl_usdt": pnl,
                       "equity_after_usdt": equity})
        next_free = i + horizon
        if equity <= 0:
            break
    gross = [t["gross_bp"] for t in trades]
    net = [t["net_bp"] for t in trades]
    wins = [x for x in net if x > 0]
    losses = [-x for x in net if x < 0]
    n = len(trades)
    return {
        "trades": n, "signals_total": len(candidates),
        "skipped_due_overlap": skipped_overlap, "skipped_due_data_gap_or_boundary": skipped_gap,
        "market_orders_assumed_filled": n, "unfilled_market_orders": 0,
        "starting_equity_usdt": INITIAL_EQUITY, "ending_equity_usdt": round(equity, 6),
        "net_pnl_usdt": round(equity-INITIAL_EQUITY, 6),
        "net_return_pct": round((equity/INITIAL_EQUITY-1)*100, 4),
        "gross_mean_bp": round(sum(gross)/n, 4) if n else None,
        "net_mean_bp": round(sum(net)/n, 4) if n else None,
        "win_rate_pct": round(100*len(wins)/n, 2) if n else None,
        "profit_factor": round(sum(wins)/sum(losses), 4) if losses else (None if not wins else "inf"),
        "max_drawdown_pct": round(max_dd*100, 4),
        "fees_usdt": round(sum(t["fees_usdt"] for t in trades), 6),
        "slippage_usdt": round(sum(t["slippage_usdt"] for t in trades), 6),
        "trade_log": trades,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-flow", required=True)
    ap.add_argument("--pilot-book", required=True)
    ap.add_argument("--test-flow", required=True)
    ap.add_argument("--test-book", required=True)
    ap.add_argument("--out", default="exp014_independent_oos.json")
    args = ap.parse_args()
    report = {
        "experiment": "EXP-014",
        "purpose": "Independent-period order-flow validation; thresholds calibrated only on May-June 2024 and frozen for July-August 2024.",
        "calibration_period_utc": ["2024-05-01T00:00:00Z", "2024-07-01T00:00:00Z"],
        "oos_period_utc": ["2024-07-01T00:00:00Z", "2024-09-01T00:00:00Z"],
        "symbols": {},
        "execution": {"entry": "next 1m open after completed signal minute",
          "exit": "horizon close (5/15/60 minutes after signal minute)",
          "fee_bp_one_way": ONE_WAY_FEE_BP, "slippage_bp_one_way": ONE_WAY_SLIPPAGE_BP,
          "round_trip_cost_bp": ROUND_TRIP_COST_BP, "leverage": 1,
          "capital_usdt_per_symbol_per_strategy_horizon": INITIAL_EQUITY,
          "sizing": "100% of current equity at 1x; compounding only within each isolated symbol/strategy/horizon series",
          "funding": "not modeled; maximum holding horizon 60 minutes, but trades crossing an 8-hour funding timestamp are not explicitly charged",
          "maker": "not tested; taker market execution assumed filled at next-minute open with fixed slippage",
          "missed_or_unfilled": "Market orders assumed filled; signals skipped due to overlap, boundary, or timestamp gap are counted separately."},
        "feature_definitions": {
          "obi": "Aggregated +/-1% and +/-2% BookDepth notional imbalance; not full per-price L2.",
          "ofi": "Aggressive taker buy/sell quote imbalance from aggTrades; not order-book OFI.",
          "whale": "Imbalance of individual aggTrades above 100,000 USDT notional; not trader/wallet identity."
        },
        "threshold_rule": "Per feature q20/q80 from all valid exact-minute intersections in May-June calibration only; immutable when applied to July-August.",
        "limitations": ["BookDepth is coarse percentage-band snapshots, not full event-level L2.",
          "No queue position, passive fills, partial fills, or maker probability.",
          "No funding debit/credit explicitly modeled for trades crossing funding timestamps.",
          "Fixed slippage, no market impact, and next-minute-open execution are proxies.",
          "The pilot period has been previously inspected in EXP-010-013; only July-August is the new OOS evaluation window.",
          "No claim of pristine untouched historical data; the independent period is new to this EXP, but the calendar window may have been inspected elsewhere in the broader research."]},
    }
    for symbol in SYMBOLS:
        pf = load_files(args.pilot_flow, symbol); pb = load_files(args.pilot_book, symbol)
        tf = load_files(args.test_flow, symbol); tb = load_files(args.test_book, symbol)
        pilot = build_rows(pf, pb); test = build_rows(tf, tb)
        if len(pilot) < 10000 or len(test) < 10000:
            raise SystemExit(f"{symbol}: insufficient exact-minute pilot/test intersection ({len(pilot)}/{len(test)})")
        thresholds = make_thresholds(pilot)
        sigs = strategy_signals(test, thresholds)
        sym = {"pilot_matched_minutes": len(pilot), "oos_matched_minutes": len(test),
               "pilot_first_utc_ms": min(r["t"] for r in pilot), "pilot_last_utc_ms": max(r["t"] for r in pilot),
               "oos_first_utc_ms": min(r["t"] for r in test), "oos_last_utc_ms": max(r["t"] for r in test),
               "frozen_thresholds_from_pilot_only": thresholds, "strategies": {}}
        for name, candidates in sigs.items():
            sym["strategies"][name] = {"oos_signals": len(candidates), "horizons": {}}
            for h in HORIZONS:
                sym["strategies"][name]["horizons"][str(h)] = simulate(test, candidates, h)
        report["symbols"][symbol] = sym
        print(f"{symbol}: pilot={len(pilot):,} matched minutes; OOS={len(test):,}; "
              f"signals=" + ", ".join(f"{k}:{len(v)}" for k,v in sigs.items()), flush=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("EXP-014 report written:", args.out, flush=True)

if __name__ == "__main__":
    main()
