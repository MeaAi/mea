#!/usr/bin/env python3
"""Independent 4h RSI(20)>70 + 1h pullback experiment.
Public Binance Vision USD-M data only. UTC-aligned completed candles, Wilder RSI,
next-hour-open execution, 1m adverse marks, funding cashflows, 1x notional.
"""
import argparse, csv, hashlib, io, json, urllib.request, zipfile
from collections import defaultdict
from datetime import datetime, timezone

BASE="https://data.binance.vision/data"
SYMBOL="BTCUSDT"
FEE_LEVELS=(2.0,5.0,8.0)
SLIP_BP=2.0
PULLBACK=0.0075
RSI_PERIOD=20
RSI_THRESHOLD=70.0
ALPHA_STOP=0.0125
CATASTROPHE_STOP=0.025
HOLD_BARS=24
COOLDOWN_BARS=26
MAX_ENTRIES=6

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"research-only"})
    with urllib.request.urlopen(req,timeout=180) as r: return r.read()

def months(start,end):
    y,m=map(int,start.split("-")); ey,em=map(int,end.split("-"))
    while (y,m)<=(ey,em):
        yield f"{y:04d}-{m:02d}"
        m+=1
        if m==13: y,m=y+1,1

def ts(v):
    n=int(float(v))
    if n>10**17:return n//10**6
    if n>10**14:return n//10**3
    return n

def archive(kind,month):
    if kind=="perp": path=f"futures/um/monthly/klines/{SYMBOL}/1m/{SYMBOL}-1m-{month}.zip"
    elif kind=="mark": path=f"futures/um/monthly/markPriceKlines/{SYMBOL}/1m/{SYMBOL}-1m-{month}.zip"
    elif kind=="funding": path=f"futures/um/monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-{month}.zip"
    else: raise ValueError(kind)
    url=f"{BASE}/{path}"
    blob=get(url); check=get(url+".CHECKSUM").decode().strip().split()[0].lower()
    digest=hashlib.sha256(blob).hexdigest()
    if digest!=check: raise RuntimeError("SHA256 mismatch "+path)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name=next(n for n in z.namelist() if n.lower().endswith(".csv"))
        rows=list(csv.reader(io.TextIOWrapper(z.open(name),encoding="utf-8-sig",newline="")))
    return rows,digest,len(blob)

def load_data(start,end):
    minutes={}; marks={}; funding=[]; qa={}
    for month in months(start,end):
        for kind,target in (("perp",minutes),("mark",marks)):
            rows,digest,size=archive(kind,month); good=0; bad=0
            for r in rows:
                if not r: continue
                try:
                    t=ts(r[0]); target[t]={"o":float(r[1]),"h":float(r[2]),"l":float(r[3]),"c":float(r[4])}; good+=1
                except (ValueError,IndexError): bad+=1
            qa[f"{month}:{kind}"]={"rows":good,"bad_rows":bad,"sha256":digest,"zip_bytes":size}
        rows,digest,size=archive("funding",month); good=0
        for r in rows:
            if not r: continue
            try: funding.append((ts(r[0]),float(r[2]))); good+=1
            except (ValueError,IndexError): pass
        qa[f"{month}:funding"]={"rows":good,"sha256":digest,"zip_bytes":size}
    minutes=dict(sorted(minutes.items())); marks=dict(sorted(marks.items())); funding.sort()
    if not minutes: raise RuntimeError("No futures minute bars downloaded")
    gaps=sum(1 for a,b in zip(minutes, list(minutes)[1:]) if b-a!=60000)
    missing_funding_marks=sum(1 for ft,_ in funding if (ft//60000)*60000 not in marks)
    if missing_funding_marks:
        raise RuntimeError(f"{missing_funding_marks} funding events lack a corresponding minute-open mark candle")
    return minutes,marks,funding,{"archives":qa,"perp_minutes":len(minutes),"mark_minutes":len(marks),"funding_events":len(funding),"perp_minute_gaps":gaps,"funding_events_without_mark":missing_funding_marks}

def build_hours(minutes):
    hours=[]
    byhour=defaultdict(list)
    for t,b in minutes.items(): byhour[t//3600000].append((t,b))
    for h,items in sorted(byhour.items()):
        if len(items)!=60 or items[0][0]!=h*3600000 or items[-1][0]!=(h+1)*3600000-60000: continue
        if any(items[i][0]-items[i-1][0]!=60000 for i in range(1,60)): continue
        bs=[x[1] for x in items]
        hours.append({"t":h*3600000,"o":bs[0]["o"],"h":max(x["h"] for x in bs),"l":min(x["l"] for x in bs),"c":bs[-1]["c"],"minute_ts":[x[0] for x in items]})
    return hours

def wilder_rsi(closes,period):
    out=[None]*len(closes)
    if len(closes)<=period:return out
    gains=[];losses=[]
    for i in range(1,period+1):
        d=closes[i]-closes[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/period; al=sum(losses)/period
    def val(g,l):
        if l==0:return 100.0
        return 100.0-100.0/(1.0+g/l)
    out[period]=val(ag,al)
    for i in range(period+1,len(closes)):
        d=closes[i]-closes[i-1]
        ag=(ag*(period-1)+max(d,0))/period
        al=(al*(period-1)+max(-d,0))/period
        out[i]=val(ag,al)
    return out

def build_regime(hours):
    four=[]; byblock=defaultdict(list)
    for i,h in enumerate(hours): byblock[h["t"]//14400000].append((i,h))
    for block,items in sorted(byblock.items()):
        if len(items)!=4: continue
        if [x[1]["t"] for x in items] != [block*14400000+j*3600000 for j in range(4)]: continue
        four.append({"end_hour_index":items[-1][0],"close":items[-1][1]["c"],"end_ts":(block+1)*14400000})
    vals=wilder_rsi([x["close"] for x in four],RSI_PERIOD)
    return {four[i]["end_hour_index"]:vals[i] for i in range(len(four)) if vals[i] is not None}

def backtest(hours,minutes,marks,funding,lo,hi,fee_bp,with_pullback):
    equity=100.0; peak=100.0; maxdd=0.0; trades=[]
    regime_map=build_regime(hours)
    active=False; zone_high=0.0; entries=0; bars_since_exit=10**9
    pending=None; pos=None
    fund_i=0
    funding=sorted(funding)
    # Funding events assigned to the mark-price minute that contains the event timestamp.
    funding_by_min=defaultdict(list)
    for ft,rate in funding: funding_by_min[(ft//60000)*60000].append((ft,rate))
    for i in range(lo,hi):
        h=hours[i]
        if pending=="entry" and pos is None:
            raw=h["o"]; fill=raw*(1+SLIP_BP/10000)
            notional=equity
            qty=notional/fill
            fee=notional*fee_bp/10000
            equity-=fee
            pos={"entry":fill,"qty":qty,"entry_i":i,"bars":0,"funding":0.0,"entry_fee":fee,"notional":notional}
            pending=None
        elif pending=="exit" and pos is not None:
            raw=h["o"]; close_pos(pos,raw,"alpha_or_time",fee_bp)
            pending=None
        if i in regime_map:
            rsi=regime_map[i]
            now=rsi>RSI_THRESHOLD
            if now and not active:
                active=True; zone_high=h["c"]; entries=0
            elif not now and active:
                active=False
            elif now and active:
                zone_high=max(zone_high,h["c"])
        if pos is not None:
            pos["bars"]+=1
            exited=False
            for mt in h["minute_ts"]:
                b=minutes[mt]
                # Apply any funding settled in this minute using minute-open mark price approximation.
                for ft,rate in funding_by_min.get(mt,[]):
                    if pos["entry_i"]<=i and mt>=hours[pos["entry_i"]]["t"]:
                        mb=marks.get(mt)
                        if mb is not None:
                            cashflow=-pos["qty"]*mb["o"]*rate
                            pos["funding"]+=cashflow
                            equity+=cashflow
                # Adverse mark-to-market at minute low for a long.
                unreal=pos["qty"]*(b["l"]-pos["entry"])
                marked=equity+unreal
                peak=max(peak,marked)
                if peak>0:maxdd=min(maxdd,marked/peak-1)
                stop=pos["entry"]*(1-CATASTROPHE_STOP)
                if b["l"]<=stop:
                    raw_exit=min(b["o"],stop)
                    exit_fill=raw_exit*(1-SLIP_BP/10000)
                    close_pos(pos,raw_exit,"catastrophe_stop",fee_bp,exit_fill=exit_fill)
                    pos=None; bars_since_exit=0; exited=True; break
            if pos is not None:
                if h["c"]<=pos["entry"]*(1-ALPHA_STOP):
                    pending="exit"
                elif pos["bars"]>=HOLD_BARS:
                    pending="exit"
            if exited: continue
        else:
            bars_since_exit+=1
        # Signals are evaluated only after this completed 1h candle; fill occurs next hour open.
        if pos is None and pending is None and active and i+1<hi and entries<MAX_ENTRIES:
            if entries==0:
                pending="entry"; entries+=1
            elif with_pullback and bars_since_exit>=COOLDOWN_BARS and zone_high>0:
                drop=(zone_high-h["c"])/zone_high
                if drop>=PULLBACK:
                    pending="entry"; entries+=1
            zone_high=max(zone_high,h["c"])
        peak=max(peak,equity)
        if peak>0:maxdd=min(maxdd,equity/peak-1)
    if pos is not None:
        last=hours[hi-1]; raw=last["c"]
        close_pos(pos,raw,"end_of_split",fee_bp)
    wins=[x["net_pnl"] for x in trades if x["net_pnl"]>0]
    losses=[-x["net_pnl"] for x in trades if x["net_pnl"]<0]
    return {"trades":len(trades),"ending_equity_usdt":round(equity,6),"net_return_pct":round((equity/100-1)*100,4),
            "max_adverse_minute_drawdown_pct":round(maxdd*100,4),"win_rate_pct":round(100*len(wins)/len(trades),2) if trades else None,
            "profit_factor":round(sum(wins)/sum(losses),4) if losses else None,
            "funding_pnl_usdt":round(sum(x["funding"] for x in trades),6),
            "commission_usdt":round(sum(x["fees"] for x in trades),6),
            "slippage_bp_per_side":SLIP_BP,"fee_bp_per_side":fee_bp,"trades_detail":trades}

def close_pos(pos,raw_exit,reason,fee_bp,exit_fill=None):
    # closure mutates global equity/trades via closure variables in backtest
    nonlocal_dummy=None

def regime_state_at(hours,regime_map,stop):
    active=False; zone_high=0.0
    for i in range(stop):
        h=hours[i]
        if i in regime_map:
            now=regime_map[i]>RSI_THRESHOLD
            if now and not active: active=True; zone_high=h["c"]
            elif not now and active: active=False; zone_high=0.0
            elif now and active: zone_high=max(zone_high,h["c"])
        if active: zone_high=max(zone_high,h["c"])
    return active,zone_high

def run_variant(hours,minutes,marks,funding,lo,hi,fee_bp,with_pullback):
    equity=100.0; peak=100.0; maxdd=0.0; trades=[]
    regime_map=build_regime(hours); active,zone_high=regime_state_at(hours,regime_map,lo); entries=0; bars_since_exit=10**9
    pending=None; pos=None; funding_by_min=defaultdict(list)
    for ft,rate in funding: funding_by_min[(ft//60000)*60000].append((ft,rate))
    def finish(raw_exit,reason,exit_fill=None):
        nonlocal equity,pos,peak,maxdd
        p=pos
        fill=exit_fill if exit_fill is not None else raw_exit*(1-SLIP_BP/10000)
        exit_notional=p["qty"]*fill
        fee=exit_notional*fee_bp/10000
        pnl=p["qty"]*(fill-p["entry"])+p["funding"]-fee
        equity+=pnl
        peak=max(peak,equity)
        if peak>0:maxdd=min(maxdd,equity/peak-1)
        trades.append({"entry_time":hours[p["entry_i"]]["t"],"exit_time":hours[current_i]["t"],"entry_price":p["entry"],"exit_price":fill,
          "gross_pnl_usdt":round(p["qty"]*(fill-p["entry"]),6),"funding":round(p["funding"],6),
          "fees":round(p["entry_fee"]+fee,6),"net_pnl":round(pnl-p["entry_fee"],6),"reason":reason})
        pos=None
    for current_i in range(lo,hi):
        h=hours[current_i]
        if pending=="entry" and pos is None:
            fill=h["o"]*(1+SLIP_BP/10000); notional=equity; qty=notional/fill
            fee=notional*fee_bp/10000; equity-=fee
            pos={"entry":fill,"qty":qty,"entry_i":current_i,"bars":0,"funding":0.0,"entry_fee":fee}
            pending=None
        elif pending=="exit" and pos is not None:
            finish(h["o"],"alpha_or_time"); pending=None
        if current_i in regime_map:
            now=regime_map[current_i]>RSI_THRESHOLD
            if now and not active: active=True; zone_high=h["c"]; entries=0
            elif not now and active: active=False
            elif now and active: zone_high=max(zone_high,h["c"])
        exited=False
        if pos is not None:
            pos["bars"]+=1
            for mt in h["minute_ts"]:
                b=minutes[mt]
                for ft,rate in funding_by_min.get(mt,[]):
                    mb=marks.get(mt)
                    if mb is not None:
                        cashflow=-pos["qty"]*mb["o"]*rate
                        pos["funding"]+=cashflow
                marked=equity+pos["funding"]+pos["qty"]*(b["l"]-pos["entry"])
                peak=max(peak,marked)
                if peak>0:maxdd=min(maxdd,marked/peak-1)
                stop=pos["entry"]*(1-CATASTROPHE_STOP)
                if b["l"]<=stop:
                    raw=min(b["o"],stop); finish(raw,"catastrophe_stop",raw*(1-SLIP_BP/10000))
                    exited=True; break
            if pos is not None:
                if h["c"]<=pos["entry"]*(1-ALPHA_STOP) or pos["bars"]>=HOLD_BARS:
                    pending="exit"
        else:
            bars_since_exit+=1
        if exited:
            bars_since_exit=0
        if pos is None and pending is None and active and current_i+1<hi and entries<MAX_ENTRIES:
            if entries==0:
                pending="entry"; entries+=1
            elif with_pullback and bars_since_exit>=COOLDOWN_BARS and zone_high>0:
                if (zone_high-h["c"])/zone_high>=PULLBACK:
                    pending="entry"; entries+=1
            zone_high=max(zone_high,h["c"])
        peak=max(peak,equity)
        if peak>0:maxdd=min(maxdd,equity/peak-1)
    if pos is not None:
        finish(hours[hi-1]["c"],"end_of_split")
    wins=[x["net_pnl"] for x in trades if x["net_pnl"]>0]
    losses=[-x["net_pnl"] for x in trades if x["net_pnl"]<0]
    return {"trades":len(trades),"ending_equity_usdt":round(equity,6),"net_return_pct":round((equity/100-1)*100,4),
      "max_adverse_minute_drawdown_pct":round(maxdd*100,4),"win_rate_pct":round(100*len(wins)/len(trades),2) if trades else None,
      "profit_factor":round(sum(wins)/sum(losses),4) if losses else None,
      "funding_pnl_usdt":round(sum(x["funding"] for x in trades),6),"commission_usdt":round(sum(x["fees"] for x in trades),6),
      "slippage_bp_per_side":SLIP_BP,"fee_bp_per_side":fee_bp}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start-month",default="2020-01"); ap.add_argument("--end-month",default="2026-10")
    ap.add_argument("--out",default="research-results/rsi_pullback_report.json")
    a=ap.parse_args()
    minutes,marks,funding,qa=load_data(a.start_month,a.end_month)
    hours=build_hours(minutes)
    if len(hours)<1000: raise SystemExit("Insufficient complete hourly candles")
    # Only compare complete contiguous UTC-aligned hourly candles.
    gaps=sum(1 for x,y in zip(hours,hours[1:]) if y["t"]-x["t"]!=3600000)
    n=len(hours); a1=int(n*.5); a2=int(n*.7)
    splits={"train":(0,a1),"validation":(a1,a2),"oos":(a2,n)}
    report={"strategy":"4h Wilder RSI(20)>70 regime; 1h first entry; optional 0.75% pullback re-entry",
      "source":"Binance Vision public USD-M 1m klines, mark-price klines and funding archives; SHA256 verified",
      "period":[a.start_month,a.end_month],"symbol":SYMBOL,"start_equity_usdt":100,"leverage":1,
      "method":{"rsi":"Wilder RSI(20) on completed UTC-aligned 4h candles; no 1h stride sampling","entry":"Signal after completed 1h close; fill at next 1h open with adverse 2bp slippage","control":"One initial entry per RSI regime; no re-entry","candidate":"Same initial entry plus re-entry after close is at least 0.75% below the highest close in the active RSI regime; maximum 6 entries per zone; 26h cooldown after exit","stops":"1.25% close-triggered alpha stop queued for next 1h open; 2.5% catastrophe stop checked against every 1m low; max hold 24h","costs":"Commission on actual entry and exit notionals; 2bp slippage each side; funding at actual event timestamps using the containing minute's mark-price open approximation","drawdown":"Minute-by-minute adverse low mark-to-market, plus realized equity"},
      "data_qa":qa,"complete_hourly_bars":n,"hourly_gaps_after_filter":gaps,
      "chronological_split":"50% train / 20% validation / 30% OOS by complete hourly bars; no parameter tuning",
      "results":{},"limitations":["Funding event mark uses minute-open approximation, not exact event mark.","One BTC symbol only; does not prove cross-asset robustness.","Historical fills are simulated at next-hour open; no order-book queue model.","A stop gap is filled at the worse of the stop and minute open, plus slippage; still a bar-based approximation."]}
    for name,(lo,hi) in splits.items():
        report["results"][name]={}
        for fee in FEE_LEVELS:
            report["results"][name][f"fee{int(fee)}"]={
              "control_initial_entry_only":run_variant(hours,minutes,marks,funding,lo,hi,fee,False),
              "candidate_initial_plus_pullback":run_variant(hours,minutes,marks,funding,lo,hi,fee,True)}
    import os
    os.makedirs("research-results",exist_ok=True)
    with open(a.out,"w",encoding="utf-8") as f: json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
