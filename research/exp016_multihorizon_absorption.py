#!/usr/bin/env python3
"""EXP-016: multi-horizon taker-flow absorption; frozen May-Jun calibration, Sep-Oct OOS.
This is distinct from EXP-012's same-minute candle-direction proxy, but remains
an aggTrades + 1m OHLC proxy, not event-level L2 passive absorption.
"""
import argparse,csv,gzip,glob,json,math
from pathlib import Path
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
WINDOWS=(5,15,60)
INITIAL=100.0
FEE_BP=5.0
SLIP_BP=2.0

def load(pattern,symbol):
    d={}
    for p in sorted(glob.glob(pattern)):
        if Path(p).name.split("-")[0]!=symbol: continue
        with gzip.open(p,"rt",encoding="utf-8",newline="") as f:
            for r in csv.DictReader(f):
                t=int(r["open_time_ms"])
                if t in d: raise ValueError(f"{symbol}: duplicate minute {t}")
                d[t]={"t":t,"open":float(r["open"]),"close":float(r["close"]),
                      "buy":float(r["agg_taker_buy_quote"] or 0),
                      "sell":float(r["agg_taker_sell_quote"] or 0)}
    return [d[t] for t in sorted(d)]

def qtile(v,q):
    a=sorted(x for x in v if math.isfinite(x))
    if not a: raise ValueError("No calibration observations")
    return a[min(len(a)-1,max(0,math.ceil(q*len(a))-1))]

def features(rows,w):
    out=[None]*len(rows)
    for i in range(w-1,len(rows)):
        j=i-w+1
        if rows[i]["t"]-rows[j]["t"]!=(w-1)*60000: continue
        b=sum(rows[k]["buy"] for k in range(j,i+1))
        s=sum(rows[k]["sell"] for k in range(j,i+1))
        if b+s<=0 or rows[j]["close"]<=0 or rows[i]["close"]<=0: continue
        imb=(b-s)/(b+s)
        response=(1 if imb>=0 else -1)*math.log(rows[i]["close"]/rows[j]["close"])*10000
        out[i]={"imbalance":imb,"abs_flow":abs(imb),"signed_response_bp":response}
    return out

def simulate(rows,candidates,h):
    eq=INITIAL; peak=eq; maxdd=0.0; next_free=0; trades=[]; overlap=gap=0
    for i,direction in candidates:
        if i<next_free: overlap+=1; continue
        if i+1>=len(rows) or i+h>=len(rows): gap+=1; continue
        if rows[i+1]["t"]-rows[i]["t"]!=60000 or rows[i+h]["t"]-rows[i]["t"]!=h*60000:
            gap+=1; continue
        entry=rows[i+1]["open"]; exitp=rows[i+h]["close"]
        if entry<=0: gap+=1; continue
        gross_bp=direction*(exitp/entry-1)*10000
        notional=eq; exit_notional=notional*exitp/entry
        fees=(notional+exit_notional)*FEE_BP/10000
        slip=(notional+exit_notional)*SLIP_BP/10000
        pnl=notional*gross_bp/10000-fees-slip
        net_bp=pnl/notional*10000
        eq+=pnl; peak=max(peak,eq); maxdd=max(maxdd,(peak-eq)/peak if peak else 0)
        trades.append({"signal_time_ms":rows[i]["t"],"entry_time_ms":rows[i+1]["t"],
          "exit_time_ms":rows[i+h]["t"],"direction":direction,"gross_bp":gross_bp,
          "net_bp":net_bp,"notional_usdt":notional,"fees_usdt":fees,"slippage_usdt":slip,
          "net_pnl_usdt":pnl,"equity_after_usdt":eq})
        next_free=i+h
        if eq<=0: break
    n=len(trades); net=[x["net_bp"] for x in trades]; gross=[x["gross_bp"] for x in trades]
    wins=sum(x>0 for x in net); pos=sum(x for x in net if x>0); neg=-sum(x for x in net if x<0)
    return {"signals":len(candidates),"trades":n,"skipped_overlap":overlap,"skipped_gap_or_boundary":gap,
      "starting_equity_usdt":INITIAL,"ending_equity_usdt":round(eq,6),"net_pnl_usdt":round(eq-INITIAL,6),
      "net_return_pct":round((eq/INITIAL-1)*100,4),"gross_mean_bp":round(sum(gross)/n,4) if n else None,
      "net_mean_bp":round(sum(net)/n,4) if n else None,"win_rate_pct":round(wins/n*100,2) if n else None,
      "profit_factor":round(pos/neg,4) if neg else (None if not pos else "inf"),
      "max_drawdown_pct":round(maxdd*100,4),
      "fees_usdt":round(sum(x["fees_usdt"] for x in trades),6),
      "slippage_usdt":round(sum(x["slippage_usdt"] for x in trades),6),"trade_log":trades}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--calibration",required=True); ap.add_argument("--oos",required=True)
    ap.add_argument("--out",default="exp016_absorption.json"); a=ap.parse_args()
    report={"experiment":"EXP-016","status":"report exists only after successful workflow completion",
      "hypothesis":"Extreme multi-minute signed taker quote flow with weak same-window signed price response indicates absorption; fade the aggressive-flow direction.",
      "calibration_period_utc":["2024-05-01T00:00:00Z","2024-07-01T00:00:00Z"],
      "oos_period_utc":["2024-09-01T00:00:00Z","2024-11-01T00:00:00Z"],
      "symbols":{},"method":{
        "flow":"sum(buy quote - sell quote)/sum(buy quote + sell quote) over completed 5/15/60m window",
        "signed_response":"sign(flow imbalance)*log(close_now/close_window_start)*10000 bp",
        "signal":"absolute flow imbalance >= calibration q80 AND signed response <= calibration q20 conditional on high-flow calibration windows",
        "direction":"contrarian to signed taker flow","entry":"next 1m open","exit":"horizon close; non-overlapping",
        "thresholds":"May-Jun calibration only; frozen on Sep-Oct OOS",
        "capital":"100 USDT per independent symbol/horizon, 1x, 100% equity notional",
        "costs":"5bp one-way fee + 2bp one-way slippage, charged on entry and exit notionals",
        "funding":"not explicitly charged for trades crossing 8h funding timestamp",
        "execution":"taker market orders assumed filled; no maker fill or queue model"},
      "prior_work_distinction":"EXP-012 tested a same-minute OFI-extreme + candle-direction-failure proxy. EXP-016 uses rolling multi-minute signed quote flow and a conditional price-impact threshold. It is a methodological extension, not event-level L2 proof.",
      "limitations":["May-Jun calibration was previously inspected in EXP-010-013.",
        "Sep-Oct 2024 is a separate OOS window for this experiment, but may have been inspected elsewhere; not pristine unseen history.",
        "No event-level L2, passive additions/cancellations, queue position, or true passive absorption measurement.",
        "Fixed slippage; no market impact or liquidation model; BTC/ETH/SOL only.",
        "Funding not explicitly modeled for rare trades crossing funding timestamps.",
        "No integration into MEAFLOW-72 regardless of this exploratory result."]}
    for sym in SYMBOLS:
        cal=load(a.calibration,sym); oos=load(a.oos,sym)
        if len(cal)<50000 or len(oos)<50000: raise SystemExit(f"{sym}: insufficient rows cal={len(cal)} oos={len(oos)}")
        if not (1714521600000<=cal[0]["t"]<1714608000000 and 1719705600000<=cal[-1]["t"]<1719792000000):
            raise SystemExit(f"{sym}: calibration must span May 1 through Jun 30 2024")
        if not (1725148800000<=oos[0]["t"]<1725235200000 and 1730332800000<=oos[-1]["t"]<1730419200000):
            raise SystemExit(f"{sym}: OOS must span Sep 1 through Oct 31 2024")
        result={"calibration_rows":len(cal),"oos_rows":len(oos),"windows":{}}
        for w in WINDOWS:
            cf=features(cal,w); valid=[x for x in cf if x is not None]
            flow_cut=qtile([x["abs_flow"] for x in valid],.80)
            response_cut=qtile([x["signed_response_bp"] for x in valid if x["abs_flow"]>=flow_cut],.20)
            of=features(oos,w); candidates=[]; valid_oos=0
            for i,x in enumerate(of):
                if x is None: continue
                valid_oos+=1
                if x["abs_flow"]>=flow_cut and x["signed_response_bp"]<=response_cut:
                    candidates.append((i,-1 if x["imbalance"]>0 else 1))
            result["windows"][str(w)]={"frozen_thresholds":{"abs_flow_q80":flow_cut,
              "signed_response_q20_conditional":response_cut},"oos_valid_windows":valid_oos,
              "absorption_signals":len(candidates),"contrarian_strategy":simulate(oos,candidates,w)}
        report["symbols"][sym]=result
        print(f"{sym}: calibration={len(cal):,} OOS={len(oos):,}",flush=True)
    Path(a.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("EXP-016 report written:",a.out,flush=True)
if __name__=="__main__": main()
