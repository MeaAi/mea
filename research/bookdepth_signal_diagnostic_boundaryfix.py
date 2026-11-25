#!/usr/bin/env python3
"""Exploratory OBI / taker-OFI signal diagnostic with chronological holdout.

OBI is computed from Binance Vision aggregated percentage-band notional depth.
It is NOT full L2, order-level imbalance, or queue position. Signals at minute t
enter at t+1 open and exit at t+h close. Train-only quantiles are frozen for
validation/OOS. This is a predictive diagnostic, not a cost-aware strategy test.
"""
import argparse, csv, gzip, glob, json, math
from pathlib import Path
from collections import defaultdict

def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def quantile(values, q):
    xs = sorted(x for x in values if math.isfinite(x))
    if not xs:
        return None
    return xs[min(len(xs)-1, max(0, int(math.ceil(q*len(xs))-1)))]

def split_indices(lo, hi, n, h):
    """Indices whose signal, next-open entry, and h-minute exit all stay in [lo, hi)."""
    if h < 1 or lo < 0 or hi < lo or n < 0:
        raise ValueError("invalid split bounds or horizon")
    start = max(0, lo)
    stop = min(hi - h, n - h)
    return range(start, max(start, stop))

def contiguous_horizon(rows, i, h):
    """Require every minute from signal t through exit t+h to be present."""
    return all(rows[j+1]["t"] - rows[j]["t"] == 60000
               for j in range(i, i+h))

def stats(values):
    if not values:
        return {"n": 0, "mean_bp": None, "median_bp": None, "win_rate_pct": None}
    xs = sorted(values)
    n = len(xs)
    return {"n": n, "mean_bp": round(sum(xs)/n, 4),
            "median_bp": round(xs[n//2], 4),
            "win_rate_pct": round(100*sum(x > 0 for x in xs)/n, 2)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bookdepth", required=True)
    ap.add_argument("--orderflow", required=True)
    ap.add_argument("--out", default="bookdepth_signal_diagnostic.json")
    args = ap.parse_args()
    book_files = glob.glob(args.bookdepth)
    flow_files = glob.glob(args.orderflow)
    if not book_files or not flow_files:
        raise SystemExit("BookDepth/orderflow files missing")
    books, flows = defaultdict(dict), defaultdict(dict)
    for p in book_files:
        symbol = Path(p).name.split("-")[0]
        for r in read_gz(p):
            try: books[symbol][int(r["open_time_ms"])] = r
            except (ValueError, KeyError): continue
    for p in flow_files:
        symbol = Path(p).name.split("-")[0]
        for r in read_gz(p):
            try: flows[symbol][int(r["open_time_ms"])] = r
            except (ValueError, KeyError): continue

    report = {
      "method": "Boundary-corrected exact UTC-minute join; signals at minute t; entry at t+1 open; exit at t+h close. Every signal/entry/exit remains inside its own chronological split. All thresholds estimated on first 50% only; validation 20%, untouched OOS 30%.",
      "obi_definition": "OBI=(bid_notional_1pct+bid_notional_2pct - ask_notional_1pct-ask_notional_2pct)/(bid+ask). Binance Vision bookDepth aggregated percentage bands; not full L2.",
      "ofi_definition": "AggTrade taker quote imbalance=(aggressive_buy_quote-aggressive_sell_quote)/(sum); excludes passive order additions/cancellations.",
      "limitations": ["BookDepth is aggregated percentage-band depth, not full L2 or queue data.",
        "Depth changes do not identify additions versus cancellations.",
        "No fees, spread, slippage, maker fills, funding, or liquidation in this predictive diagnostic.",
        "Only exact timestamp intersections are used; missing minutes are excluded, never interpolated.",
        "OBI and OFI signals are exploratory; no strategy profitability claim."],
      "symbols": {}
    }

    for symbol in sorted(set(books) & set(flows)):
        ts = sorted(set(books[symbol]) & set(flows[symbol]))
        rows = []
        for t in ts:
            b, f = books[symbol][t], flows[symbol][t]
            try:
                bid = float(b["notional_1pct"] or 0) + float(b["notional_2pct"] or 0)
                ask = float(b["notional_-1pct"] or 0) + float(b["notional_-2pct"] or 0)
                buy = float(f["agg_taker_buy_quote"] or 0)
                sell = float(f["agg_taker_sell_quote"] or 0)
                op, close = float(f["open"]), float(f["close"])
            except (KeyError, ValueError):
                continue
            depth_sum = bid + ask
            flow_sum = buy + sell
            if depth_sum <= 0 or flow_sum <= 0 or op <= 0:
                continue
            rows.append({"t":t, "open":op, "close":close,
                         "obi":(bid-ask)/depth_sum,
                         "ofi":(buy-sell)/flow_sum,
                         "bid":bid, "ask":ask,
                         "buy_pressure":(buy-sell)/flow_sum,
                         "sell_pressure":(sell-buy)/flow_sum})

        n = len(rows)
        train_end = int(n*.5)
        val_end = int(n*.7)
        train = rows[:train_end]
        obi_lo, obi_hi = quantile([r["obi"] for r in train], .2), quantile([r["obi"] for r in train], .8)
        ofi_lo, ofi_hi = quantile([r["ofi"] for r in train], .2), quantile([r["ofi"] for r in train], .8)
        # Signals are signed: +1 long, -1 short. Thresholds never refit after train.
        for r in rows:
            r["obi_signal"] = 1 if r["obi"] >= obi_hi else (-1 if r["obi"] <= obi_lo else 0)
            r["ofi_signal"] = 1 if r["ofi"] >= ofi_hi else (-1 if r["ofi"] <= ofi_lo else 0)
            r["obi_ofi_agree"] = r["obi_signal"] if r["obi_signal"] != 0 and r["obi_signal"] == r["ofi_signal"] else 0

        sym = {"matched_minutes":n,
               "thresholds_train_only":{"obi_q20":obi_lo,"obi_q80":obi_hi,"ofi_q20":ofi_lo,"ofi_q80":ofi_hi},
               "split":{"train":[0,train_end],"validation":[train_end,val_end],"oos":[val_end,n]},
               "horizons":{}}
        for h in (1,5,15,60):
            hr = {}
            for split, lo, hi in (("train",0,train_end),("validation",train_end,val_end),("oos",val_end,n)):
                always_long, obi_returns, ofi_returns, agree_returns = [], [], [], []
                counts = {"obi":0,"ofi":0,"obi_ofi_agree":0}
                for i in split_indices(lo, hi, n, h):
                    if not contiguous_horizon(rows, i, h):
                        continue
                    entry, exit_px = rows[i+1]["open"], rows[i+h]["close"]
                    if entry <= 0: continue
                    raw = (exit_px/entry-1)*10000
                    always_long.append(raw)
                    for field, dest in (("obi_signal",obi_returns),("ofi_signal",ofi_returns),("obi_ofi_agree",agree_returns)):
                        signal = rows[i][field]
                        if signal:
                            dest.append(raw*signal)
                            counts[{"obi_signal":"obi","ofi_signal":"ofi","obi_ofi_agree":"obi_ofi_agree"}[field]] += 1
                hr[split] = {"always_long_market_return":stats(always_long),
                             "obi_directional_return":stats(obi_returns),
                             "ofi_directional_return":stats(ofi_returns),
                             "obi_plus_ofi_agreement_return":stats(agree_returns),
                             "signal_counts":counts}
            hr["thresholds_source"] = "first 50% chronological training segment only"
            sym["horizons"][str(h)] = hr
        report["symbols"][symbol] = sym

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output":args.out,"symbols":list(report["symbols"])}, indent=2))

if __name__ == "__main__":
    main()
