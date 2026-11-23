#!/usr/bin/env python3
"""Report-aligned failed-breakout/liquidity-trap proxy backtest.
Uses Binance Vision 1m klines + aggTrades aggregated to minute. No L2, OI,
funding, queue/fill model, or wallet-level positioning; those are explicit gaps.
All signals use closed bars only; entry is next 1m open; stop-first on ambiguous
OHLC bars. Fixed rules are frozen before chronological 50/20/30 evaluation.
"""
import argparse, csv, gzip, glob, json, math
from pathlib import Path

def load(path):
    rows=[]
    with gzip.open(path,"rt",encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "t":int(r["open_time_ms"]), "o":float(r["open"]),
                "h":float(r["high"]), "l":float(r["low"]), "c":float(r["close"]),
                "qv":float(r["quote_volume"]),
                "buy":float(r["agg_taker_buy_quote"]),
                "sell":float(r["agg_taker_sell_quote"])
            })
    return rows

def aggregate(rows, n):
    out=[]
    for s in range(0,len(rows)-n+1,n):
        x=rows[s:s+n]
        out.append({"start":s,"end":s+n-1,"o":x[0]["o"],
                    "h":max(z["h"] for z in x),"l":min(z["l"] for z in x),
                    "c":x[-1]["c"],"buy":sum(z["buy"] for z in x),
                    "sell":sum(z["sell"] for z in x),"qv":sum(z["qv"] for z in x)})
    return out

def ema(values, period):
    out=[]; a=2/(period+1); v=None
    for x in values:
        v=x if v is None else a*x+(1-a)*v
        out.append(v)
    return out

def make_signals(rows, symbol):
    m5,m15,m60,m240=(aggregate(rows,n) for n in (5,15,60,240))
    closes240=[x["c"] for x in m240]
    e20,e50=ema(closes240,20),ema(closes240,50)
    threshold={"BTCUSDT":.80,"ETHUSDT":.85,"SOLUSDT":.85}.get(symbol,.85)
    signals=[]
    # 15m sweep: prior 20 completed bars define the liquidity level.
    for k in range(20,len(m15)-1):
        b=m15[k]; prev=m15[k-20:k]
        prior_low=min(x["l"] for x in prev); prior_high=max(x["h"] for x in prev)
        low_sweep=b["l"]<prior_low and b["c"]>prior_low
        high_sweep=b["h"]>prior_high and b["c"]<prior_high
        if not (low_sweep or high_sweep): continue
        direction=1 if low_sweep else -1
        width=max(b["h"]-b["l"],1e-12)
        close_pos=(b["c"]-b["l"])/width
        reclaim=(close_pos>=.65) if direction==1 else (close_pos<=.35)
        # 5m CVD divergence: last 3 completed bars vs preceding 3.
        k5=(b["end"]+1)//5-1
        if k5<6: continue
        recent=m5[k5-2:k5+1]; prior=m5[k5-5:k5-2]
        recent_delta=sum(x["buy"]-x["sell"] for x in recent)
        prior_delta=sum(x["buy"]-x["sell"] for x in prior)
        recent_low=min(x["l"] for x in recent); prior_5_low=min(x["l"] for x in prior)
        recent_high=max(x["h"] for x in recent); prior_5_high=max(x["h"] for x in prior)
        cvd_div=(recent_low<prior_5_low and recent_delta>prior_delta) if direction==1 else (recent_high>prior_5_high and recent_delta<prior_delta)
        # Absorption proxy: unusually large aggressive counter-flow, but limited
        # net price progress across the 15m reclaim bar. Not true L2 absorption.
        counter=b["sell"] if direction==1 else b["buy"]
        hist=[x["sell"] if direction==1 else x["buy"] for x in m15[max(0,k-20):k]]
        med=sorted(hist)[len(hist)//2] if hist else 0
        progress=abs(b["c"]-b["o"])/max(b["o"],1e-12)
        absorption=counter>med and progress<.0015
        # 4h regime context: avoid entries against a strongly extended 4h EMA
        # trend; the regime check is a simple proxy, not the report's full model.
        k240=(b["end"]+1)//240-1
        if k240<50: continue
        trend=(e20[k240]-e50[k240])/max(closes240[k240],1e-12)
        context_ok=(trend>-.012 if direction==1 else trend<.012)
        score=.35 + (.20 if reclaim else 0)+(.25 if cvd_div else 0)+(.20 if absorption else 0)
        if not context_ok or score+1e-12<threshold: continue
        signal_minute=b["end"]
        if signal_minute+1>=len(rows): continue
        signals.append({"i":signal_minute,"dir":direction,"sweep":b["l"] if direction==1 else b["h"],
                        "score":round(score,4),"threshold":threshold})
    return signals

def simulate(rows, signals, symbol, cost_bp, fraction, leverage=1.0, start_idx=0, end_idx=None):
    cfg={"BTCUSDT":(1.0,2.5,2.0),"ETHUSDT":(2.0,1.5,2.0),"SOLUSDT":(1.0,3.0,1.25)}
    stop_mult,activate_r,trail_r=cfg.get(symbol,(1.0,2.0,2.0))
    if end_idx is None: end_idx=len(rows)
    equity=100.0; peak=100.0; maxdd=0.0; trades=[]; free=start_idx
    for sig in signals:
        i=sig["i"]
        if i<start_idx or i<free or i+1>=end_idx: continue
        entry=rows[i+1]["o"]
        if entry<=0: continue
        direction=sig["dir"]
        raw_dist=abs(entry-sig["sweep"])/entry*10000
        stop_bp=max(8,min(25,raw_dist*stop_mult))
        stop=entry*(1-stop_bp/10000) if direction==1 else entry*(1+stop_bp/10000)
        risk=abs(entry-stop); best=entry; active=False
        exit_px=None; exit_idx=None; reason="time"
        # 4h max hold; each bar: stop checked before favorable trailing updates.
        for j in range(i+1,min(end_idx,i+1+240)):
            bar=rows[j]
            hit=(bar["l"]<=stop) if direction==1 else (bar["h"]>=stop)
            if hit:
                exit_px=stop; exit_idx=j; reason="stop"; break
            best=max(best,bar["h"]) if direction==1 else min(best,bar["l"])
            favorable=(best-entry)*direction
            if favorable>=activate_r*risk:
                active=True
            if active:
                new_stop=best-trail_r*risk if direction==1 else best+trail_r*risk
                stop=max(stop,new_stop) if direction==1 else min(stop,new_stop)
            exit_px=bar["c"]; exit_idx=j
        if exit_px is None or exit_idx is None: continue
        gross=direction*(exit_px/entry-1)*10000
        notional=equity*fraction*leverage
        net_bp=gross-cost_bp
        pnl=notional*net_bp/10000
        equity+=pnl
        peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak if peak else 0)
        trades.append({"entry_i":i+1,"exit_i":exit_idx,"gross_bp":gross,"net_bp":net_bp,
                       "cost_bp":cost_bp,"pnl_usdt":pnl,"equity":equity,"exit":reason,
                       "score":sig["score"],"fraction":fraction})
        free=exit_idx+1
        if equity<=0: break
    if not trades:
        return {"trades":0,"starting_equity_usdt":100,"ending_equity_usdt":100,"net_return_pct":0,
                "max_drawdown_pct":0,"gross_mean_bp":None,"net_mean_bp":None,"profit_factor":None}
    wins=[t["pnl_usdt"] for t in trades if t["pnl_usdt"]>0]
    losses=[-t["pnl_usdt"] for t in trades if t["pnl_usdt"]<0]
    return {"trades":len(trades),"starting_equity_usdt":100,"ending_equity_usdt":round(equity,6),
            "net_return_pct":round((equity/100-1)*100,4),"max_drawdown_pct":round(maxdd*100,4),
            "gross_mean_bp":round(sum(t["gross_bp"] for t in trades)/len(trades),4),
            "net_mean_bp":round(sum(t["net_bp"] for t in trades)/len(trades),4),
            "win_rate_pct":round(100*sum(t["pnl_usdt"]>0 for t in trades)/len(trades),2),
            "profit_factor":round(sum(wins)/sum(losses),4) if losses else None,
            "exit_reasons":{"stop":sum(t["exit"]=="stop" for t in trades),
                            "time":sum(t["exit"]=="time" for t in trades)}}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True); ap.add_argument("--out",default="report_strategy_backtest.json")
    args=ap.parse_args(); paths=glob.glob(args.input)
    if not paths: raise SystemExit("No feature files found")
    report={"strategy":"Failed-breakout / liquidity-trap reversal (report-aligned proxy)",
      "method":"15m 20-bar sweep/reclaim; 5m CVD divergence and aggressive-flow absorption proxy; 4h EMA regime proxy; next-1m-open entry; structural stop and conditional trailing.",
      "chronological_split":"50% train / 20% validation / 30% untouched OOS; fixed rules, no parameter fitting on OOS",
      "execution":"1x leverage; non-overlapping positions; 4h max hold; stop-first on ambiguous OHLC bars; 100 USDT starting equity; fee/slippage deducted from notional each trade.",
      "cost_scenarios_round_trip_bp":[12,14,16,18],
      "position_fractions":[0.10,0.25,0.50,1.00],
      "limitations":["Score weights are a transparent proxy because the source report's exact weights/normalization were not reproducibly specified.",
       "No historical L2 book, queue position, maker fills, OI, long/short account ratio, liquidation stream, or funding history.",
       "AggTrade absorption is a proxy; it does not prove passive limit-order absorption.",
       "No leverage above 1x or liquidation model; no live trading. Results are exploratory, not production validation."],
      "files":{}}
    for path in paths:
        rows=load(path)
        if len(rows)<240*10: raise SystemExit(f"{path}: insufficient rows for 4h context")
        symbol=Path(path).name.split("-")[0]
        signals=make_signals(rows,symbol)
        n=len(rows); a=int(n*.5); b=int(n*.7)
        sections={"train":(0,a),"validation":(a,b),"oos":(b,n)}
        result={"rows":n,"signals":len(signals),"split":{}}
        for name,(lo,hi) in sections.items():
            ss=[s for s in signals if lo<=s["i"]<hi]
            result["split"][name]={"minute_range":[lo,hi],"signals":len(ss),"costs":{}}
            for cost in (12,14,16,18):
                result["split"][name]["costs"][str(cost)+"bp"]={}
                for frac in (.10,.25,.50,1.0):
                    result["split"][name]["costs"][str(cost)+"bp"][str(frac)] = simulate(rows,ss,symbol,cost,frac,start_idx=lo,end_idx=hi)
        report["files"][Path(path).name]=result
        print(f"{symbol}: {len(rows):,} bars, {len(signals)} signals; OOS signals={result['split']['oos']['signals']}",flush=True)
    Path(args.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT WRITTEN:",args.out,flush=True)
if __name__=="__main__": main()
