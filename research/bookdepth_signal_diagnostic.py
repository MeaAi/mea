#!/usr/bin/env python3
"""Exploratory, no-lookahead BookDepth + aggTrade predictive diagnostic."""
import argparse, csv, gzip, glob, json, math
from pathlib import Path
from collections import defaultdict

def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def quantile(values, q):
    xs=sorted(x for x in values if math.isfinite(x))
    if not xs: return None
    return xs[min(len(xs)-1, max(0, int(math.ceil(q*len(xs))-1)))]

def stats(values):
    if not values: return {"n":0,"mean_bp":None,"median_bp":None,"win_rate_pct":None}
    xs=sorted(values); n=len(xs)
    return {"n":n,"mean_bp":round(sum(xs)/n,4),
            "median_bp":round(xs[n//2],4),
            "win_rate_pct":round(100*sum(x>0 for x in xs)/n,2)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bookdepth",required=True)
    ap.add_argument("--orderflow",required=True)
    ap.add_argument("--out",default="bookdepth_signal_diagnostic.json")
    args=ap.parse_args()
    book_files=glob.glob(args.bookdepth); flow_files=glob.glob(args.orderflow)
    if not book_files or not flow_files: raise SystemExit("BookDepth/orderflow files missing")
    books=defaultdict(dict); flows=defaultdict(dict)
    for p in book_files:
        name=Path(p).name; symbol=name.split("-")[0]
        for r in read_gz(p):
            try: books[symbol][int(r["open_time_ms"])]=r
            except (ValueError,KeyError): continue
    for p in flow_files:
        name=Path(p).name; symbol=name.split("-")[0]
        for r in read_gz(p):
            try: flows[symbol][int(r["open_time_ms"])]=r
            except (ValueError,KeyError): continue
    report={"method":"BookDepth snapshot features joined on exact UTC minute; signals formed only from minute t; entry at minute t+1 open; forward exit at t+h close. Train-derived 80th percentile thresholds are frozen for validation/OOS.",
      "limitations":["BookDepth is aggregated percentage-band depth, not full L2 or queue data.",
      "A snapshot depth increase does not prove new limit orders; decreases do not prove cancellations.",
      "No maker fill, spread, slippage, funding, or liquidation simulation in this predictive diagnostic.",
      "Only exact timestamp intersections are used; missing BookDepth minutes are excluded, not interpolated."],
      "symbols":{}}
    for symbol in sorted(set(books)&set(flows)):
        ts=sorted(set(books[symbol])&set(flows[symbol]))
        rows=[]
        for t in ts:
            b=books[symbol][t]; f=flows[symbol][t]
            try:
                bid=float(b["notional_-1"] or 0)+float(b["notional_-2"] or 0)
                ask=float(b["notional_1"] or 0)+float(b["notional_2"] or 0)
                buy=float(f["agg_taker_buy_quote"] or 0); sell=float(f["agg_taker_sell_quote"] or 0)
                o=float(f["open"]); c=float(f["close"])
            except (ValueError,KeyError): continue
            rows.append({"t":t,"bid":bid,"ask":ask,"buy":buy,"sell":sell,
                         "open":o,"close":c,
                         "sell_pressure":(sell-buy)/(sell+buy) if sell+buy else 0.0,
                         "buy_pressure":(buy-sell)/(sell+buy) if sell+buy else 0.0})
        for i,r in enumerate(rows):
            prev=rows[i-1] if i else None
            r["bid_change"]=(r["bid"]/prev["bid"]-1) if prev and r["t"]-prev["t"]==60000 and prev["bid"]>0 else None
            r["ask_change"]=(r["ask"]/prev["ask"]-1) if prev and r["t"]-prev["t"]==60000 and prev["ask"]>0 else None
        n=len(rows); a=int(n*.5); b=int(n*.7)
        train=rows[:a]
        sell_thr=quantile([x["sell_pressure"] for x in train],.8)
        buy_thr=quantile([x["buy_pressure"] for x in train],.8)
        symbol_report={"matched_minutes":n,"train_thresholds":{"sell_pressure_q80":sell_thr,"buy_pressure_q80":buy_thr},
                       "split":{"train":[0,a],"validation":[a,b],"oos":[b,n]},"horizons":{}}
        for h in (1,5,15,60):
            h_report={}
            for split,(lo,hi) in {"train":(0,a),"validation":(a,b),"oos":(b,n)}.items():
                baseline=[]; sell_abs=[]; buy_abs=[]
                for i in range(max(lo,1),min(hi,n-h-1)):
                    if rows[i+1]["t"]-rows[i]["t"]!=60000 or rows[i+h]["t"]-rows[i]["t"]!=h*60000: continue
                    entry=rows[i+1]["open"]; exit_px=rows[i+h]["close"]
                    if entry<=0: continue
                    ret=(exit_px/entry-1)*10000
                    baseline.append(ret)
                    r=rows[i]
                    if r["bid_change"] is not None and sell_thr is not None and r["sell_pressure"]>=sell_thr and r["bid_change"]>0:
                        sell_abs.append(ret)
                    if r["ask_change"] is not None and buy_thr is not None and r["buy_pressure"]>=buy_thr and r["ask_change"]>0:
                        buy_abs.append(-ret)
                h_report[split]={"baseline_long_return":stats(baseline),
                  "sell_pressure_plus_bid_growth_long":stats(sell_abs),
                  "buy_pressure_plus_ask_growth_short":stats(buy_abs)}
            h_report["thresholds_source"]="train only; q80 fixed across all splits"
            symbol_report["horizons"][str(h)]=h_report
        report["symbols"][symbol]=symbol_report
    Path(args.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
