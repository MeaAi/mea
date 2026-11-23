#!/usr/bin/env python3
"""Conservative maker trade-through test using raw aggTrade price extremes.

A passive bid is considered filled only if an aggressive-sell trade prints
strictly below the signal-minute close during the next minute. A passive ask
requires an aggressive-buy print strictly above that close. This is still not
queue-accurate: trade-through is a proxy, not proof of our queue position.
"""
import argparse,csv,gzip,glob,json,math
from pathlib import Path
from collections import defaultdict

def load(pattern):
    out=defaultdict(dict)
    for path in glob.glob(pattern):
        sym=Path(path).name.split("-")[0]
        with gzip.open(path,"rt",encoding="utf-8",newline="") as f:
            for r in csv.DictReader(f):
                try: out[sym][int(r["open_time_ms"])]=r
                except (KeyError,ValueError): pass
    return out

def qtile(xs,q):
    a=sorted(x for x in xs if math.isfinite(x))
    return a[min(len(a)-1,max(0,math.ceil(q*len(a))-1))] if a else None

def stats(trades,initial):
    eq=initial; peak=eq; maxdd=0; gross=fees=slip=0; wins=0
    for t in trades:
        gross+=t[0]; fees+=t[1]; slip+=t[2]; eq+=t[3]; peak=max(peak,eq)
        maxdd=max(maxdd,(peak-eq)/peak if peak else 0); wins+=t[3]>0
    gp=sum(max(0,t[3]) for t in trades); gl=-sum(min(0,t[3]) for t in trades)
    n=len(trades)
    return {"trades":n,"end_equity_usdt":round(eq,6),
      "net_return_pct":round((eq/initial-1)*100,4),"gross_pnl_usdt":round(gross,6),
      "fees_usdt":round(fees,6),"slippage_usdt":round(slip,6),
      "net_mean_bp":round(sum(t[4] for t in trades)/n,4) if n else None,
      "win_rate_pct":round(wins/n*100,2) if n else None,
      "profit_factor":round(gp/gl,4) if gl else (None if not gp else "inf"),
      "max_drawdown_pct":round(maxdd*100,4)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bookdepth",required=True); ap.add_argument("--orderflow",required=True)
    ap.add_argument("--out",default="maker_trade_through_backtest.json")
    ap.add_argument("--capital",type=float,default=100.0)
    args=ap.parse_args()
    books=load(args.bookdepth); flows=load(args.orderflow)
    result={"method":"Train-only q80 thresholds; signals at minute t; one-minute passive limit at close(t); fill only on strict aggressive trade-through during t+1; exit at close(t+h); non-overlapping events.",
      "assumptions":{"capital_usdt":args.capital,"equity_fraction_per_trade":1.0,
       "maker_entry_fee_bp":2,"taker_exit_fee_bp":5,"taker_entry_fee_bp":5,
       "maker_fill_rule":"Long: next-minute aggressive-sell min price < signal close. Short: next-minute aggressive-buy max price > signal close.",
       "maker_fill_caveat":"Trade-through does not prove queue fill; no L2 queue position or available quantity reconstruction. Unfilled orders are cancelled after one minute.",
       "exit_slippage_bp_scenarios":[0,2,4,6],"funding":"not modeled; horizon <=60m","liquidation":"not modeled; 1x only"},
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
                sell_min=float(f.get("agg_sell_min_price") or 0); buy_max=float(f.get("agg_buy_max_price") or 0)
            except (KeyError,ValueError): continue
            rows.append({"t":t,"bid":bid,"ask":ask,"buy":buy,"sell":sell,"open":op,"close":close,
              "sell_min":sell_min,"buy_max":buy_max,"sp":(sell-buy)/(sell+buy) if sell+buy else 0,
              "bp":(buy-sell)/(sell+buy) if sell+buy else 0})
        for i,r in enumerate(rows):
            prev=rows[i-1] if i else None
            r["bid_grow"]=bool(prev and r["t"]-prev["t"]==60000 and prev["bid"]>0 and r["bid"]>prev["bid"])
            r["ask_grow"]=bool(prev and r["t"]-prev["t"]==60000 and prev["ask"]>0 and r["ask"]>prev["ask"])
        n=len(rows); cut=int(n*.5); val=int(n*.7)
        sell_thr=qtile([r["sp"] for r in rows[:cut]],.8); buy_thr=qtile([r["bp"] for r in rows[:cut]],.8)
        sr={"matched_minutes":n,"train_q80":{"sell_pressure":sell_thr,"buy_pressure":buy_thr},"splits":{}}
        for split,lo,hi in (("train",0,cut),("validation",cut,val),("oos",val,n)):
            out={}
            for h in (5,15,60):
              for side in ("long","short"):
                candidates=[]
                for i in range(max(lo,1),min(hi,n-h-1)):
                    if rows[i+1]["t"]-rows[i]["t"]!=60000 or rows[i+h]["t"]-rows[i]["t"]!=h*60000: continue
                    r=rows[i]
                    signal=(r["bid_grow"] and sell_thr is not None and r["sp"]>=sell_thr) if side=="long" else (r["ask_grow"] and buy_thr is not None and r["bp"]>=buy_thr)
                    if signal: candidates.append(i)
                # Keep signals non-overlapping even if an order fails to fill.
                chosen=[]; next_free=lo
                for i in candidates:
                    if i>=next_free:
                        chosen.append(i); next_free=i+h
                for model in ("taker","maker_trade_through"):
                    for slip_bp in ((2,4,8) if model=="taker" else (0,2,4,6)):
                        eq=args.capital; trades=[]; filled=0
                        for i in chosen:
                            r=rows[i]; nxt=rows[i+1]
                            if model=="maker_trade_through":
                                limit=r["close"]
                                did_fill=(nxt["sell_min"]>0 and nxt["sell_min"]<limit) if side=="long" else (nxt["buy_max"]>limit)
                                if not did_fill: continue
                                entry=limit; entry_fee=2
                            else:
                                entry=nxt["open"]; entry_fee=5
                            exitp=rows[i+h]["close"]
                            if entry<=0: continue
                            filled+=1
                            raw=(exitp/entry-1)*10000*(1 if side=="long" else -1)
                            notional=eq; exit_fee=5
                            fee=notional*(entry_fee+exit_fee)/10000
                            sl=notional*slip_bp/10000
                            gross=notional*raw/10000; pnl=gross-fee-sl
                            trades.append((gross,fee,sl,pnl,raw-entry_fee-exit_fee-slip_bp)); eq+=pnl
                        key=f"{side}_{h}m_{model}_exit_slip{slip_bp}bp"
                        m=stats(trades,args.capital); m["signals"]=len(chosen); m["filled"]=filled
                        m["observed_fill_rate_pct"]=round(filled/len(chosen)*100,2) if chosen else None
                        out[key]=m
            sr["splits"][split]=out
        result["symbols"][sym]=sr
    Path(args.out).write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
