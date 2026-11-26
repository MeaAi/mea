#!/usr/bin/env python3
"""EXP-016: frozen-threshold multi-horizon taker-flow absorption test.

Distinct from the prior EXP-012 same-minute candle-direction proxy:
- accumulates signed taker quote flow over 5/15/60 completed minutes;
- measures signed price response over the same window;
- flags unusually strong signed flow with unusually weak price response;
- thresholds are estimated only on May-Jun 2024 calibration data;
- tests contrarian entries on Sep-Oct 2024, next-minute open to horizon close.

This is an OHLC/aggTrades proxy, not true L2 passive absorption or queue data.
"""
import argparse, csv, gzip, glob, json, math
from pathlib import Path

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
WINDOWS = (5, 15, 60)
INITIAL_EQUITY = 100.0
FEE_BP_ONE_WAY = 5.0
SLIPPAGE_BP_ONE_WAY = 2.0
ROUND_TRIP_BP = 2 * (FEE_BP_ONE_WAY + SLIPPAGE_BP_ONE_WAY)

def load(pattern, symbol):
    rows = {}
    for path in sorted(glob.glob(pattern)):
        if Path(path).name.split("-")[0] != symbol:
            continue
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                t = int(r["open_time_ms"])
                if t in rows:
                    raise ValueError(f"{symbol}: duplicate minute {t}")
                rows[t] = {
                    "t": t, "open": float(r["open"]), "close": float(r["close"]),
                    "buy": float(r["agg_taker_buy_quote"] or 0),
                    "sell": float(r["agg_taker_sell_quote"] or 0),
                    "quote_volume": float(r["quote_volume"] or 0),
                }
    return [rows[t] for t in sorted(rows)]

def quantile(values, q):
    a = sorted(x for x in values if math.isfinite(x))
    if not a:
        raise ValueError("No calibration observations")
    # Nearest-rank quantile, fixed before OOS.
    return a[min(len(a)-1, max(0, math.ceil(q*len(a))-1))]

def features(rows, window):
    out = [None] * len(rows)
    for i in range(window-1, len(rows)):
        start = i-window+1
        if rows[i]["t"] - rows[start]["t"] != (window-1)*60000:
            continue
        buy = sum(rows[j]["buy"] for j in range(start, i+1))
        sell = sum(rows[j]["sell"] for j in range(start, i+1))
        total = buy + sell
        if total <= 0 or rows[start]["close"] <= 0:
            continue
        imbalance = (buy-sell)/total
        # Positive when price moves in the same direction as aggressive flow.
        signed_response_bp = (1 if imbalance >= 0 else -1) * math.log(
            rows[i]["close"] / rows[start]["close"]) * 10000
        out[i] = {"imbalance": imbalance, "abs_flow": abs(imbalance),
                  "signed_response_bp": signed_response_bp,
                  "buy_quote": buy, "sell_quote": sell, "total_quote": total}
    return out

def simulate(rows, feats, candidates, horizon):
    equity = INITIAL_EQUITY
    peak = equity
    max_dd = 0.0
    next_free = 0
    trades = []
    skipped_overlap = 0
    skipped_gap = 0
    for i, direction in candidates:
        if i < next_free:
            skipped_overlap += 1
            continue
        if i+1 >= len(rows) or i+horizon >= len(rows):
            skipped_gap += 1
            continue
        if rows[i+1]["t"]-rows[i]["t"] != 60000 or rows[i+horizon]["t"]-rows[i]["t"] != horizon*60000:
            skipped_gap += 1
            continue
        entry = rows[i+1]["open"]
        exit_px = rows[i+horizon]["close"]
        if entry <= 0:
            skipped_gap += 1
            continue
        gross_bp = direction * math.log(exit_px/entry) * 10000
        notional = equity
        exit_notional = notional * exit_px/entry
        fees = (notional+exit_notional)*FEE_BP_ONE_WAY/10000
        slip = (notional+exit_notional)*SLIPPAGE_BP_ONE_WAY/10000
        gross_pnl = notional*gross_bp/10000
        pnl = gross_pnl-fees-slip
        net_bp = pnl/notional*10000
        equity += pnl
        peak = max(peak,equity)
        max_dd = max(max_dd,(peak-equity)/peak if peak else 0.0)
        trades.append({"signal_time_ms":rows[i]["t"],"entry_time_ms":rows[i+1]["t"],
                       "exit_time_ms":rows[i+horizon]["t"],"direction":direction,
                       "gross_bp":gross_bp,"net_bp":net_bp,"notional_usdt":notional,
                       "fees_usdt":fees,"slippage_usdt":slip,"net_pnl_usdt":pnl,
                       "equity_after_usdt":equity})
        next_free = i+horizon
        if equity <= 0:
            break
    n=len(trades)
    net=[x["net_bp"] for x in trades]
    gross=[x["gross_bp"] for x in trades]
    wins=sum(x>0 for x in net)
    pos=sum(x for x in net if x>0)
    neg=-sum(x for x in net if x<0)
    return {
        "signals":len(candidates),"trades":n,"skipped_overlap":skipped_overlap,
        "skipped_gap_or_boundary":skipped_gap,"starting_equity_usdt":INITIAL_EQUITY,
        "ending_equity_usdt":round(equity,6),"net_pnl_usdt":round(equity-INITIAL_EQUITY,6),
        "net_return_pct":round((equity/INITIAL_EQUITY-1)*100,4),
        "gross_mean_bp":round(sum(gross)/n,4) if n else None,
        "net_mean_bp":round(sum(net)/n,4) if n else None,
        "win_rate_pct":round(wins/n*100,2) if n else None,
        "profit_factor":round(pos/neg,4) if neg else (None if not pos else "inf"),
        "max_drawdown_pct":round(max_dd*100,4),
        "fees_usdt":round(sum(x["fees_usdt"] for x in trades),6),
        "slippage_usdt":round(sum(x["slippage_usdt"] for x in trades),6),
        "trade_log":trades,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--calibration",required=True)
    ap.add_argument("--oos",required=True)
    ap.add_argument("--out",default="exp016_absorption.json")
    args=ap.parse_args()
    report={
      "experiment":"EXP-016",
      "status":"completed only when this report is produced by a successful Actions run",
      "hypothesis":"High multi-minute signed taker flow with unusually weak same-window signed price response indicates passive absorption; fade the aggressive-flow direction.",
      "calibration_period_utc":["2024-05-01T00:00:00Z","2024-07-01T00:00:00Z"],
      "oos_period_utc":["2024-09-01T00:00:00Z","2024-11-01T00:00:00Z"],
      "symbols":{},
      "method":{
        "flow":"sum(aggressive_buy_quote - aggressive_sell_quote) / sum(aggressive_buy_quote + aggressive_sell_quote) over completed 5/15/60m windows",
        "price_response":"sign(flow_imbalance) * log(close_now / close_window_start) * 10000",
        "absorption_rule":"abs(flow_imbalance) >= calibration q80 AND signed_price_response <= calibration q20 conditional on abs(flow_imbalance) >= calibration q80",
        "direction":"contrarian to signed taker flow",
        "entry":"next 1m open after the window closes",
        "exit":"5/15/60m close after signal minute; non-overlapping per isolated series",
        "thresholds":"q80 absolute flow and conditional q20 signed response from May-Jun calibration only; frozen for Sep-Oct OOS",
        "capital":"100 USDT per symbol/window series, 1x, 100% equity notional, compounding only within each independent series",
        "costs":"5bp one-way fee + 2bp one-way slippage on entry and exit notionals",
        "funding":"not modeled; report boundary checks and note trades up to 60m may cross funding timestamp",
        "fills":"taker market orders assumed filled; no maker/queue/fill-probability claim"
      },
      "comparison_to_prior_work":"Not a rerun of EXP-012 same-minute candle-direction absorption proxy. This uses cumulative multi-minute signed quote flow and conditional signed price-impact quantiles. Still an aggTrades+1m OHLC proxy, not event-level L2.",
      "limitations":[
        "Historical May-Jun calibration period was previously inspected in EXP-010-013.",
        "Sep-Oct 2024 is a separate test window in this experiment but may have been inspected elsewhere in the wider project; do not call it pristine unseen history.",
        "No event-level L2 queue reconstruction, passive-order additions/cancellations, or true passive absorption measurement.",
        "No funding charge for rare trades crossing an 8h funding timestamp; max horizon 60m.",
        "Fixed slippage, no market impact, no liquidation model; static BTC/ETH/SOL sample only.",
        "A positive result is exploratory and does not justify modifying MEAFLOW-72."
      ]
    }
    for symbol in SYMBOLS:
        cal=load(args.calibration,symbol)
        oos=load(args.oos,symbol)
        if len(cal)<50000 or len(oos)<50000:
            raise SystemExit(f"{symbol}: insufficient minutes cal={len(cal)} oos={len(oos)}; need >=50,000 each")
        if not (1714521600000 <= cal[0]["t"] < 1714608000000 and 1719792000000 <= cal[-1]["t"] < 1719878400000):
            raise SystemExit(f"{symbol}: calibration timestamp bounds invalid")
        if not (1725148800000 <= oos[0]["t"] < 1725235200000 and 1727740800000 <= oos[-1]["t"] < 1727827200000):
            raise SystemExit(f"{symbol}: OOS timestamp bounds invalid")
        sym={"calibration_rows":len(cal),"oos_rows":len(oos),"windows":{}}
        for w in WINDOWS:
            cf=features(cal,w)
            valid=[x for x in cf if x is not None]
            high_cut=quantile([x["abs_flow"] for x in valid],.80)
            conditional=[x["signed_response_bp"] for x in valid if x["abs_flow"]>=high_cut]
            response_cut=quantile(conditional,.20)
            of=features(oos,w)
            candidates=[]
            total_valid=0
            for i,x in enumerate(of):
                if x is None: continue
                total_valid+=1
                if x["abs_flow"]>=high_cut and x["signed_response_bp"]<=response_cut:
                    direction=-1 if x["imbalance"]>0 else 1
                    candidates.append((i,direction))
            sym["windows"][str(w)]={
              "frozen_thresholds":{"abs_flow_q80":high_cut,"signed_response_q20_conditional":response_cut},
              "oos_valid_windows":total_valid,"absorption_signals":len(candidates),
              "contrarian_strategy":simulate(oos,of,candidates,w)
            }
        report["symbols"][symbol]=sym
        print(f"{symbol}: calibration={len(cal):,}, OOS={len(oos):,}",flush=True)
    Path(args.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("EXP-016 report written:",args.out,flush=True)

if __name__=="__main__":
    main()
