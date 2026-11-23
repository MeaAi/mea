#!/usr/bin/env python3
"""Exploratory past-only order-flow diagnostics for Binance 1m feature files.
First seven days calibrate thresholds; remaining days are the test segment.
Not a production backtest: fills are next-minute open / horizon close, with no
L2 queue, intrabar execution, funding, market impact, or calibrated fee schedule.
"""
import argparse, csv, gzip, glob, json, math
from pathlib import Path

CALIBRATION_MINUTES = 7 * 1440

def quantile(values, q):
    a = sorted(values)
    if not a: return 0.0
    x = (len(a)-1)*q
    lo, hi = int(math.floor(x)), int(math.ceil(x))
    return a[lo] if lo == hi else a[lo]*(hi-x)+a[hi]*(x-lo)

def corr(xs, ys):
    n = min(len(xs), len(ys))
    if n < 2: return None
    mx, my = sum(xs[:n])/n, sum(ys[:n])/n
    vx = sum((x-mx)**2 for x in xs[:n]); vy = sum((y-my)**2 for y in ys[:n])
    if vx <= 0 or vy <= 0: return None
    return sum((xs[i]-mx)*(ys[i]-my) for i in range(n))/math.sqrt(vx*vy)

def load(path):
    op, cl, ofi, wb, ws, qv = [], [], [], [], [], []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            op.append(float(r["open"])); cl.append(float(r["close"]))
            ofi.append(float(r["ofi_quote"]))
            wb.append(float(r["whale_buy_quote"])); ws.append(float(r["whale_sell_quote"]))
            qv.append(float(r["quote_volume"]))
    return op, cl, ofi, wb, ws, qv

def evaluate(op, cl, signal, horizon, direction_mode, cost_bp, test_start, start_equity):
    # Signal at minute i close; entry next minute open; exit at close i+h.
    trades, gross = [], []
    next_free = test_start
    for i in range(test_start, len(signal)):
        s = signal[i]
        if i < next_free or i + horizon >= len(cl) or i + 1 >= len(op) or s == 0:
            continue
        direction = s if direction_mode == "continuation" else -s
        entry, exit_px = op[i+1], cl[i+horizon]
        if entry <= 0: continue
        bp = direction*(exit_px/entry-1)*10000
        gross.append(bp)
        trades.append(bp-cost_bp)
        next_free = i+horizon
    if not gross: return {"trades":0}
    wins = sum(x > 0 for x in trades)
    pos = sum(x for x in trades if x > 0); neg = -sum(x for x in trades if x < 0)
    eq, peak, maxdd, total_cost = start_equity, start_equity, 0.0, 0.0
    for g, n in zip(gross, trades):
        notional = eq  # 100% of available equity at 1x; next trade uses remaining equity
        total_cost += notional * cost_bp / 10000
        eq *= (1+n/10000)
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak-eq)/peak)
    return {"trades":len(trades), "starting_equity_usdt":start_equity,
            "ending_equity_usdt":round(eq, 6), "net_pnl_usdt":round(eq-start_equity, 6),
            "net_return_pct":round((eq/start_equity-1)*100, 4),
            "total_modeled_cost_usdt":round(total_cost, 6),
            "gross_mean_bp":sum(gross)/len(gross),
            "net_mean_bp":sum(trades)/len(trades), "win_rate":wins/len(trades),
            "profit_factor":pos/neg if neg else None, "max_drawdown_pct":maxdd*100,
            "cost_bp_round_trip":cost_bp}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--out", default="orderflow_diagnostic.json")
    ap.add_argument("--start-equity", type=float, default=100.0)
    args=ap.parse_args()
    if args.start_equity <= 0: raise SystemExit("--start-equity must be positive")
    paths=glob.glob(args.input)
    if not paths: raise SystemExit("No feature files matched")
    report={"scope":"exploratory; first 7 days calibration, remainder strictly held-out within each monthly file; not a validated strategy",
            "execution_assumption":"signal at minute close; enter next minute open; exit at horizon close; non-overlapping trades",
            "threshold_method":"p10/p90 thresholds estimated only from first 7 days; frozen for the test segment",
            "calibration_days":7, "starting_equity_usdt":args.start_equity,
            "position_sizing":"100% of remaining equity per trade at 1x; equity compounded after every closed trade",
            "cost_scenarios_bp_round_trip":[2,4,6,8,10,14,20], "files":{}}
    for path in paths:
        op,cl,ofi,wb,ws,qv=load(path)
        if len(cl) <= CALIBRATION_MINUTES + 60:
            raise SystemExit(f"{path}: need more than 7 days plus 60 minutes; got {len(cl)} rows")
        imbalance=[(b-s)/(b+s) if b+s else 0.0 for b,s in zip(wb,ws)]
        train_ofi=ofi[:CALIBRATION_MINUTES]
        train_whale=imbalance[:CALIBRATION_MINUTES]
        ofi_lo, ofi_hi = quantile(train_ofi,.1), quantile(train_ofi,.9)
        whale_lo, whale_hi = quantile(train_whale,.1), quantile(train_whale,.9)
        whale_share=[(b-s)/v if v else 0.0 for b,s,v in zip(wb,ws,qv)]
        train_whale_share=whale_share[:CALIBRATION_MINUTES]
        whale_share_lo, whale_share_hi = quantile(train_whale_share,.1), quantile(train_whale_share,.9)
        test_start=CALIBRATION_MINUTES
        sig_ofi=[0 if i < test_start else (1 if x>=ofi_hi else (-1 if x<=ofi_lo else 0)) for i,x in enumerate(ofi)]
        sig_whale=[0 if i < test_start else (1 if x>=whale_hi else (-1 if x<=whale_lo else 0)) for i,x in enumerate(imbalance)]
        sig_whale_share=[0 if i < test_start else (1 if x>=whale_share_hi else (-1 if x<=whale_share_lo else 0)) for i,x in enumerate(whale_share)]
        # Combined signal: trade only when OFI and whale imbalance both cross
        # their independently calibrated extremes in the same direction.
        sig_combined=[a if a != 0 and a == b else 0 for a,b in zip(sig_ofi,sig_whale)]
        sig_combined_share=[a if a != 0 and a == b else 0 for a,b in zip(sig_ofi,sig_whale_share)]
        fwd={}
        for h in (5,15,60):
            ret=[(cl[i+h]/op[i+1]-1)*10000 for i in range(len(cl)-h-1)]
            test_end=len(ret)
            test_ofi=ofi[test_start:test_end]
            test_whale=imbalance[test_start:test_end]
            test_ret=ret[test_start:test_end]
            valid_ofi=[(i,sig_ofi[i],ret[i]) for i in range(test_start,test_end) if sig_ofi[i]]
            valid_whale=[(i,sig_whale[i],ret[i]) for i in range(test_start,test_end) if sig_whale[i]]
            def bucket_stats(items):
                if not items: return {}
                buys=[x[2] for x in items if x[1]>0]
                sells=[x[2] for x in items if x[1]<0]
                return {"signals":len(items),
                        "buy_pressure_mean_fwd_bp":sum(buys)/len(buys) if buys else None,
                        "sell_pressure_mean_fwd_bp":sum(sells)/len(sells) if sells else None}
            fwd[str(h)]={"ofi_return_corr_test_only":corr(test_ofi,test_ret),
                         "whale_imbalance_return_corr_test_only":corr(test_whale,test_ret),
                         "ofi_extreme_bucket_test_only":bucket_stats(valid_ofi),
                         "whale_extreme_bucket_test_only":bucket_stats(valid_whale),
                         "strategies":{}}
            for signal_name,sig in (("ofi",sig_ofi),("whale_imbalance_legacy",sig_whale),("whale_share",sig_whale_share),("ofi_whale_agreement_legacy",sig_combined),("ofi_whale_share_agreement",sig_combined_share)):
                for mode in ("continuation","contrarian"):
                    for cost in (2,4,6,8,10,14,20):
                        fwd[str(h)]["strategies"][f"{signal_name}_{mode}_{cost}bp"]=evaluate(op,cl,sig,h,mode,cost,test_start,args.start_equity)
        report["files"][Path(path).name]={
            "rows":len(cl),"calibration_rows":test_start,"test_rows":len(cl)-test_start,
            "thresholds":{"ofi_p10":ofi_lo,"ofi_p90":ofi_hi,"whale_imbalance_legacy_p10":whale_lo,"whale_imbalance_legacy_p90":whale_hi,"whale_share_p10":whale_share_lo,"whale_share_p90":whale_share_hi},
            "mean_1m_quote_volume_usdt_test":sum(qv[test_start:])/len(qv[test_start:]),
            "ofi_quote_mean_test":sum(ofi[test_start:])/len(ofi[test_start:]),
            "whale_imbalance_mean_test":sum(imbalance[test_start:])/len(imbalance[test_start:]),
            "whale_share_mean_test":sum(whale_share[test_start:])/len(whale_share[test_start:]),
            "whale_buy_minutes_test":sum(x>0 for x in wb[test_start:]),
            "whale_sell_minutes_test":sum(x>0 for x in ws[test_start:]),"horizons":fwd}
    Path(args.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"output":args.out,"files":list(report["files"])},indent=2))
if __name__=="__main__": main()
