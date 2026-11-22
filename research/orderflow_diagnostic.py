#!/usr/bin/env python3
"""Exploratory, no-lookahead order-flow diagnostics for Binance 1m feature files.
This is not a production backtest: costs are sensitivity assumptions and fills use
next-minute open / horizon close, with no L2 queue or intrabar execution model.
"""
import argparse, csv, gzip, glob, json, math
from pathlib import Path

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

def evaluate(op, cl, signal, horizon, direction_mode, cost_bp):
    # Signal at close of minute i; enter at next minute open; exit at close i+h.
    trades, gross = [], []
    next_free = 0
    for i, s in enumerate(signal):
        if i < next_free or i+ horizon >= len(cl) or i+1 >= len(op): continue
        if s == 0: continue
        direction = s if direction_mode == "continuation" else -s
        entry, exit_px = op[i+1], cl[i+horizon]
        if entry <= 0: continue
        bp = direction*(exit_px/entry-1)*10000
        gross.append(bp)
        trades.append(bp-cost_bp)
        next_free = i+horizon
    if not gross: return {"trades":0}
    wins = sum(x > 0 for x in trades)
    mean = sum(trades)/len(trades)
    # Trade-level PF; no annualization due single-month pilot.
    pos = sum(x for x in trades if x > 0); neg = -sum(x for x in trades if x < 0)
    eq, peak, maxdd = 1.0, 1.0, 0.0
    for x in trades:
        eq *= (1+x/10000)
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak-eq)/peak)
    return {"trades":len(trades), "gross_mean_bp":sum(gross)/len(gross),
            "net_mean_bp":mean, "win_rate":wins/len(trades),
            "profit_factor":pos/neg if neg else None, "max_drawdown_pct":maxdd*100,
            "cost_bp_round_trip":cost_bp}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--out", default="orderflow_diagnostic.json")
    args=ap.parse_args()
    paths=glob.glob(args.input)
    if not paths: raise SystemExit("No feature files matched")
    report={"scope":"exploratory one-month order-flow diagnostic; not validated strategy",
            "execution_assumption":"signal at minute close; enter next minute open; exit at horizon close; non-overlapping trades",
            "cost_scenarios_bp_round_trip":[10,14,20],
            "files":{}}
    for path in paths:
        op,cl,ofi,wb,ws,qv=load(path)
        # AggTrade totals should reconcile to the Binance kline totals.
        # OFI is calculated from aggTrades taker buy/sell quote notional.
        imbalance=[(b-s)/(b+s) if b+s else 0.0 for b,s in zip(wb,ws)]
        fwd={}
        for h in (5,15,60):
            ret=[(cl[i+h]/op[i+1]-1)*10000 for i in range(len(cl)-h-1)]
            sig_ofi=[1 if x>=quantile(ofi,.9) else (-1 if x<=quantile(ofi,.1) else 0) for x in ofi]
            sig_whale=[1 if x>=quantile(imbalance,.9) else (-1 if x<=quantile(imbalance,.1) else 0) for x in imbalance]
            valid_ofi=[(i,sig_ofi[i],ret[i]) for i in range(len(ret)) if sig_ofi[i]]
            valid_whale=[(i,sig_whale[i],ret[i]) for i in range(len(ret)) if sig_whale[i]]
            def bucket_stats(items):
                if not items: return {}
                return {"signals":len(items),"long_or_buy_pressure_mean_fwd_bp":sum(x[2] for x in items if x[1]>0)/max(1,sum(x[1]>0 for x in items)),
                        "short_or_sell_pressure_mean_fwd_bp":sum(x[2] for x in items if x[1]<0)/max(1,sum(x[1]<0 for x in items))}
            fwd[str(h)]={"ofi_return_corr":corr(ofi[:len(ret)],ret),
                         "whale_imbalance_return_corr":corr(imbalance[:len(ret)],ret),
                         "ofi_extreme_bucket":bucket_stats(valid_ofi),
                         "whale_extreme_bucket":bucket_stats(valid_whale),
                         "strategies":{}}
            for signal_name, sig in (("ofi",sig_ofi),("whale_imbalance",sig_whale)):
                for mode in ("continuation","contrarian"):
                    for cost in (10,14,20):
                        fwd[str(h)]["strategies"][f"{signal_name}_{mode}_{cost}bp"]=evaluate(op,cl,sig,h,mode,cost)
        report["files"][Path(path).name]={
            "rows":len(cl),"mean_1m_quote_volume_usdt":sum(qv)/len(qv),
            "ofi_quote_mean":sum(ofi)/len(ofi),"ofi_quote_p10":quantile(ofi,.1),"ofi_quote_p90":quantile(ofi,.9),
            "whale_imbalance_mean":sum(imbalance)/len(imbalance),
            "whale_buy_minutes":sum(x>0 for x in wb),"whale_sell_minutes":sum(x>0 for x in ws),
            "horizons":fwd}
    Path(args.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"output":args.out,"files":list(report["files"])},indent=2))
if __name__=="__main__": main()
