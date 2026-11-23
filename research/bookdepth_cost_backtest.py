#!/usr/bin/env python3
"""Cost-aware, non-overlapping BookDepth/aggTrade event backtest.

Signals are frozen from the training half. Entry is next-minute open and exit is
h-minute close. This is a sensitivity model, not queue-accurate maker execution:
maker fill is a deterministic timestamp-hash sample at the requested rate,
with no assumed price improvement. All costs are charged on notional.
"""
import argparse, csv, gzip, glob, json, math
from pathlib import Path
from collections import defaultdict

def read_rows(pattern):
    out=defaultdict(dict)
    for path in glob.glob(pattern):
        symbol=Path(path).name.split("-")[0]
        with gzip.open(path,"rt",encoding="utf-8",newline="") as f:
            for r in csv.DictReader(f):
                try: out[symbol][int(r["open_time_ms"])]=r
                except (KeyError,ValueError): pass
    return out

def quantile(v,q):
    a=sorted(x for x in v if math.isfinite(x))
    return a[min(len(a)-1,max(0,math.ceil(q*len(a))-1))] if a else None

def summarize(trades, start=100.0):
    eq=start; peak=eq; dd=0.0; wins=0; gross=net=fees=slip=0.0
    for t in trades:
        gross += t["gross_usdt"]; net += t["net_usdt"]
        fees += t["fee_usdt"]; slip += t["slippage_usdt"]
        eq += t["net_usdt"]; peak=max(peak,eq); dd=max(dd,(peak-eq)/peak if peak else 0)
        wins += t["net_usdt"]>0
    n=len(trades)
    gp=sum(max(0,t["net_usdt"]) for t in trades)
    gl=-sum(min(0,t["net_usdt"]) for t in trades)
    return {"trades":n,"start_equity":start,"end_equity":round(eq,6),
      "net_return_pct":round((eq/start-1)*100,4),"gross_pnl_usdt":round(gross,6),
      "net_pnl_usdt":round(net,6),"fees_usdt":round(fees,6),"slippage_usdt":round(slip,6),
      "net_mean_bp":round(sum(t["net_bp"] for t in trades)/n,4) if n else None,
      "win_rate_pct":round(wins/n*100,2) if n else None,
      "profit_factor":round(gp/gl,4) if gl else (None if not gp else "inf"),
      "max_drawdown_pct":round(dd*100,4)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bookdepth",required=True); p.add_argument("--orderflow",required=True)
    p.add_argument("--out",default="bookdepth_cost_backtest.json")
    p.add_argument("--capital",type=float,default=100.0)
    args=p.parse_args()
    books=read_rows(args.bookdepth); flows=read_rows(args.orderflow)
    report={"method":"Train-only q80 thresholds; non-overlapping events per symbol/direction/horizon; next-minute open entry, horizon close exit; full-equity notional compounding.",
      "assumptions":{"capital_usdt":args.capital,"fee_bp_per_side":{"taker":5,"maker":2},
      "round_trip_slippage_bp_scenarios":[2,4,6,8],"maker_fill_rate_scenarios":[0.25,0.5,0.75],
      "maker_fill_model":"deterministic timestamp modulo 100; no price improvement; sensitivity only, not queue simulation",
      "leverage":[1,2,3],"full_equity_margin":True,
      "funding":"not applied; holding periods <=60m; funding timestamp/cashflows still require separate exact simulation",
      "liquidation":"not simulated; leverage results are sensitivity only"},
      "symbols":{}}
    for sym in sorted(set(books)&set(flows)):
        ts=sorted(set(books[sym])&set(flows[sym])); rows=[]
        for t in ts:
            b=books[sym][t]; f=flows[sym][t]
            try:
                bid=float(b["notional_-1pct"] or 0)+float(b["notional_-2pct"] or 0)
                ask=float(b["notional_1pct"] or 0)+float(b["notional_2pct"] or 0)
                buy=float(f["agg_taker_buy_quote"] or 0); sell=float(f["agg_taker_sell_quote"] or 0)
                op=float(f["open"]); close=float(f["close"])
            except (KeyError,ValueError): continue
            rows.append({"t":t,"bid":bid,"ask":ask,"buy":buy,"sell":sell,"open":op,"close":close,
              "sp":(sell-buy)/(sell+buy) if sell+buy else 0,
              "bp":(buy-sell)/(sell+buy) if sell+buy else 0})
        for i,r in enumerate(rows):
            prev=rows[i-1] if i else None
            r["bid_grow"]=bool(prev and r["t"]-prev["t"]==60000 and prev["bid"]>0 and r["bid"]>prev["bid"])
            r["ask_grow"]=bool(prev and r["t"]-prev["t"]==60000 and prev["ask"]>0 and r["ask"]>prev["ask"])
        n=len(rows); cut=int(n*.5); val=int(n*.7)
        st=rows[:cut]
        sthr=quantile([r["sp"] for r in st],.8); bthr=quantile([r["bp"] for r in st],.8)
        sr={"matched_minutes":n,"thresholds_train_only":{"sell_pressure_q80":sthr,"buy_pressure_q80":bthr},"splits":{}}
        for split,lo,hi in (("train",0,cut),("validation",cut,val),("oos",val,n)):
            split_out={}
            for h in (5,15,60):
                for direction in ("long","short"):
                    candidates=[]
                    for i in range(max(lo,1),min(hi,n-h-1)):
                        r=rows[i]
                        if rows[i+1]["t"]-r["t"]!=60000 or rows[i+h]["t"]-r["t"]!=h*60000: continue
                        if direction=="long" and r["bid_grow"] and sthr is not None and r["sp"]>=sthr: candidates.append(i)
                        if direction=="short" and r["ask_grow"] and bthr is not None and r["bp"]>=bthr: candidates.append(i)
                    # Greedy non-overlap, separately per side/horizon.
                    selected=[]; next_allowed=lo
                    for i in candidates:
                        if i>=next_allowed:
                            selected.append(i); next_allowed=i+h
                    for lev in (1,2,3):
                        for slip_bp in (2,4,6,8):
                            modes=[("taker_taker",1.0,5,5)]
                            modes += [(f"maker_taker_fill_{int(fr*100)}pct",fr,2,5) for fr in (.25,.5,.75)]
                            for mode,fill,entry_fee,exit_fee in modes:
                                eq=args.capital; trades=[]
                                for i in selected:
                                    # Reproducible fill sampling. Non-filled maker orders are skipped.
                                    if fill<1 and ((rows[i]["t"]//60000)%100)>=int(fill*100): continue
                                    entry=rows[i+1]["open"]; exitp=rows[i+h]["close"]
                                    if entry<=0: continue
                                    raw=(exitp/entry-1)*10000*(1 if direction=="long" else -1)
                                    notional=eq*lev
                                    fee_bp=entry_fee+exit_fee
                                    gross=notional*raw/10000
                                    fee=notional*fee_bp/10000
                                    slippage=notional*slip_bp/10000
                                    pnl=gross-fee-slippage
                                    trades.append({"gross_usdt":gross,"net_usdt":pnl,"fee_usdt":fee,
                                      "slippage_usdt":slippage,"net_bp":raw-fee_bp-slip_bp})
                                    eq+=pnl
                                key=f"{direction}_{h}m_{mode}_slip{slip_bp}bp_{lev}x"
                                split_out[key]=summarize(trades,args.capital)
            sr["splits"][split]=split_out
        report["symbols"][sym]=sr
    Path(args.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
