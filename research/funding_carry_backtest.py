#!/usr/bin/env python3
"""Cross-sectional Binance USD-M funding carry research.
Uses only Binance Vision public monthly fundingRate + 1h klines.
No API keys, private endpoints, or order placement.
"""
from __future__ import annotations
import argparse, bisect, csv, hashlib, io, json, math, sys, time, urllib.request, zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://data.binance.vision/data/futures/um/monthly"
HOUR = 3_600_000
DAY = 86_400_000

def months_between(start, end):
    y,m=map(int,start.split("-")); ey,em=map(int,end.split("-"))
    while (y,m)<=(ey,em):
        yield f"{y:04d}-{m:02d}"
        m+=1
        if m==13: y,m=y+1,1

def get(url, path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size: return "cached"
    tmp=path.with_suffix(path.suffix+".part")
    err=None
    for attempt in range(4):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 research-only"})
            with urllib.request.urlopen(req,timeout=90) as r,tmp.open("wb") as f:
                while True:
                    b=r.read(1024*1024)
                    if not b: break
                    f.write(b)
            tmp.replace(path); return "downloaded"
        except Exception as e:
            err=str(e); tmp.unlink(missing_ok=True); time.sleep(2**attempt)
    raise RuntimeError(f"{url}: {err}")

def verified_zip(url, cache):
    status=get(url,cache)
    check=Path(str(cache)+".CHECKSUM")
    try:
        get(url+".CHECKSUM",check)
        expected=check.read_text().strip().split()[0].lower()
        h=hashlib.sha256()
        with cache.open("rb") as f:
            for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
        if h.hexdigest()!=expected: raise RuntimeError("SHA256 mismatch "+cache.name)
    except Exception:
        cache.unlink(missing_ok=True); check.unlink(missing_ok=True)
        raise
    return status

def read_csv_zip(path):
    z=zipfile.ZipFile(path)
    names=[n for n in z.namelist() if n.lower().endswith(".csv")]
    if not names: raise RuntimeError("CSV missing in "+str(path))
    f=io.TextIOWrapper(z.open(names[0]),encoding="utf-8-sig",newline="")
    return z,f

def ts_ms(v):
    n=int(float(v))
    if n>=10**17: return n//1_000_000
    if n>=10**14: return n//1_000
    return n

def load_funding(path):
    z,f=read_csv_zip(path); out={}
    try:
        reader=csv.reader(f); first=True; idx=None
        for row in reader:
            if not row: continue
            if first:
                first=False
                low=[x.strip().lower() for x in row]
                if any(x in low for x in ("calc_time","fundingtime","funding_time")):
                    def find(names, default):
                        for n in names:
                            if n in low: return low.index(n)
                        return default
                    idx=(find(["calc_time","fundingtime","funding_time"],0),
                         find(["last_funding_rate","fundingrate","funding_rate"],2))
                    continue
                idx=(0,2)
            try:
                t=ts_ms(row[idx[0]]); rate=float(row[idx[1]])
                if math.isfinite(rate): out[t]=rate
            except (ValueError,IndexError): continue
    finally: f.close(); z.close()
    return out

def load_prices(path):
    z,f=read_csv_zip(path); out={}
    try:
        for row in csv.reader(f):
            if len(row)<5: continue
            try:
                t=ts_ms(row[0]); close=float(row[4])
                if close>0 and math.isfinite(close): out[t]=close
            except (ValueError,IndexError): continue
    finally: f.close(); z.close()
    return out

def load_symbol(symbol, months, root):
    funding={}; prices={}; files=0
    for month in months:
        fn=f"{symbol}-fundingRate-{month}.zip"
        fp=root/"cache"/symbol/"fundingRate"/fn
        fu=f"{BASE}/fundingRate/{symbol}/{fn}"
        kn=f"{symbol}-1h-{month}.zip"
        kp=root/"cache"/symbol/"klines"/"1h"/kn
        ku=f"{BASE}/klines/{symbol}/1h/{kn}"
        verified_zip(fu,fp); verified_zip(ku,kp)
        funding.update(load_funding(fp)); prices.update(load_prices(kp)); files+=2
    times=sorted(funding)
    # Funding event price: close of the 1h candle ending at/just before settlement.
    p_times=sorted(prices)
    events={}
    for t in times:
        j=bisect.bisect_right(p_times,t-1)-1
        if j>=0: events[t]=(funding[t],prices[p_times[j]])
    return symbol,events,{"funding_events":len(funding),"priced_events":len(events),"price_bars_1h":len(prices),"archives":files}

def rank_and_backtest(data, symbols, start_ms, end_ms, fee_bp, capital=100.0, rebalance_days=7, lookback_days=7):
    # Use timestamps where >=80% of symbols have a priced funding event.
    ts=sorted(t for t in set().union(*(set(data[s]) for s in symbols))
              if start_ms<=t<=end_ms and sum(t in data[s] for s in symbols)>=math.ceil(.8*len(symbols)))
    if len(ts)<100: raise RuntimeError(f"Too few aligned funding events: {len(ts)}")
    equity=capital; qty={s:0.0 for s in symbols}; prev_px={}; last_rebal=None
    daily=[]; equity_peak=capital; maxdd=0.0; gross_pnl=0.0; funding_pnl=0.0; fees=0.0
    trades=0; turnover_total=0.0; holdings_log=[]; rebalance_log=[]
    lookback=lookback_days*DAY; rebal_ms=rebalance_days*DAY
    for t in ts:
        px={s:data[s][t][1] for s in symbols if t in data[s]}
        rates={s:data[s][t][0] for s in symbols if t in data[s]}
        # Mark existing positions and settle funding for the interval ending now.
        step_price=0.0; step_funding=0.0
        for s,q in qty.items():
            if q and s in px and s in prev_px:
                step_price += q*(px[s]-prev_px[s])
                if s in rates: step_funding += -q*px[s]*rates[s]
        equity += step_price+step_funding
        gross_pnl += step_price; funding_pnl += step_funding
        # Rank on completed trailing funding events, including the just-settled event.
        do_rebalance = last_rebal is None and t>=start_ms+lookback
        if last_rebal is not None and t-last_rebal>=rebal_ms: do_rebalance=True
        if do_rebalance:
            scores={}
            for s in symbols:
                vals=[r for et,(r,p) in data[s].items() if t-lookback<et<=t]
                if len(vals)>=12: scores[s]=sum(vals)
            k=max(1,len(scores)//5)
            ordered=sorted(scores,key=scores.get)
            if len(ordered)>=2*k:
                longs=ordered[:k]; shorts=ordered[-k:]
                target={s:0.0 for s in symbols}
                per_leg=max(0.0,equity)*0.5
                for s in longs: target[s]=per_leg/k/px[s]
                for s in shorts: target[s]=-per_leg/k/px[s]
                turnover=sum(abs((target[s]-qty[s])*px[s]) for s in symbols if s in px)
                cost=turnover*fee_bp/10000.0
                equity-=cost; fees+=cost; turnover_total+=turnover
                qty=target; last_rebal=t; trades+=2*k
                rebalance_log.append({"time":datetime.fromtimestamp(t/1000,timezone.utc).isoformat(),
                                      "longs":longs,"shorts":shorts,"funding_spread_7d":round(scores[shorts[-1]]-scores[longs[0]],8),
                                      "turnover_usdt":round(turnover,4),"fee_usdt":round(cost,6)})
        for s in symbols:
            if s in px: prev_px[s]=px[s]
        equity_peak=max(equity_peak,equity)
        dd=(equity/equity_peak-1)*100 if equity_peak else -100
        maxdd=min(maxdd,dd)
        daily.append((t,equity))
    # Periodic equity snapshots are funding-event values; return and drawdown are exact at event cadence.
    ret=(equity/capital-1)*100
    years=max((ts[-1]-ts[0])/DAY/365.25,1/365.25)
    cagr=((equity/capital)**(1/years)-1)*100 if equity>0 else -100
    rets=[]
    for (ta,ea),(tb,eb) in zip(daily,daily[1:]):
        if ea>0: rets.append(eb/ea-1)
    mean=sum(rets)/len(rets) if rets else 0
    var=sum((x-mean)**2 for x in rets)/max(1,len(rets)-1) if len(rets)>1 else 0
    sharpe=(mean/math.sqrt(var)*math.sqrt(365*3)) if var>0 else 0
    return {"start_equity_usdt":capital,"end_equity_usdt":round(equity,6),"net_return_pct":round(ret,4),
            "cagr_pct":round(cagr,4),"max_drawdown_pct":round(maxdd,4),"event_sharpe_annualized":round(sharpe,4),
            "gross_price_pnl_usdt":round(gross_pnl,6),"funding_pnl_usdt":round(funding_pnl,6),
            "fees_usdt":round(fees,6),"turnover_usdt":round(turnover_total,4),"one_way_fee_bp":fee_bp,
            "rebalance_count":len(rebalance_log),"leg_changes":trades,"lookback_days":lookback_days,
            "rebalance_days":rebalance_days,"selection":"lowest 20% trailing realized funding long; highest 20% short",
            "gross_exposure":"100% of equity total: 50% long + 50% short; 1x gross, dollar neutral",
            "rebalance_log":rebalance_log}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",default="2024-01"); ap.add_argument("--end",default="2026-10")
    ap.add_argument("--symbols",default="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT")
    ap.add_argument("--out",default="research-results/funding_carry_backtest.json")
    args=ap.parse_args()
    months=list(months_between(args.start,args.end))
    symbols=[s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if len(months)<12 or len(symbols)<8: raise SystemExit("Need >=12 months and >=8 symbols for cross-sectional test.")
    root=Path("research-output"); root.mkdir(exist_ok=True)
    data={}; qa={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs={pool.submit(load_symbol,s,months,root):s for s in symbols}
        for f in as_completed(futs):
            s=futs[f]
            try:
                sym,events,meta=f.result(); data[sym]=events; qa[sym]=meta
                print(f"{sym}: {len(events):,} priced funding events",flush=True)
            except Exception as e:
                qa[s]={"error":str(e)}; print(f"SKIP {s}: {e}",flush=True)
    usable=sorted(data)
    if len(usable)<8: raise RuntimeError(f"Only {len(usable)} symbols usable; need >=8. {qa}")
    all_ts=sorted(set().union(*(set(data[s]) for s in usable)))
    # Chronological 50/20/30; first 7 days are lookback warm-up.
    first=all_ts[0]; last=all_ts[-1]; span=last-first
    train_end=first+int(span*.50); val_end=first+int(span*.70)
    periods={"train":(first+7*DAY,train_end),"validation":(train_end,val_end),"oos":(val_end,last)}
    report={"strategy":"Cross-sectional funding carry; low trailing funding long / high trailing funding short",
            "source":"Official free Binance Vision USD-M Futures monthly fundingRate and 1h klines",
            "date_range":{"first_event_utc":datetime.fromtimestamp(first/1000,timezone.utc).isoformat(),
                          "last_event_utc":datetime.fromtimestamp(last/1000,timezone.utc).isoformat()},
            "universe_requested":symbols,"universe_used":usable,"data_qa":qa,
            "methodology":{"lookback_days":7,"rebalance_days":7,"selection":"lowest 20% funding long; highest 20% funding short",
                           "capital_usdt":100,"gross_exposure":"100% total gross: 50% long and 50% short",
                           "leverage":"1x gross","fees":"one-way fee charged on actual traded notional turnover",
                           "funding":"realized funding cashflow applied at each settlement to positions held before settlement",
                           "price":"1h kline close at/just before each funding settlement",
                           "timing":"rank after settlement using trailing completed funding, then hold into next interval",
                           "splits":"chronological 50% train / 20% validation / 30% OOS; fixed rule, no OOS tuning",
                           "limitations":["Static major-coin universe has survivorship bias; delisted contracts are not yet included.",
                                          "Hourly close is a proxy for executable mark/index price at settlement.",
                                          "No intraday rebalance, liquidation, margin interest, or market impact model.",
                                          "Backtest is research only; no live orders or API keys."]},
            "periods":{}}
    for name,(a,b) in periods.items():
        if b-a<30*DAY: continue
        report["periods"][name]={}
        for fee in (2,5,8):
            report["periods"][name][f"fee_{fee}bp"]=rank_and_backtest(data,usable,a,b,fee)
        print(name, {k:v["net_return_pct"] for k,v in report["periods"][name].items()},flush=True)
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("REPORT",Path(args.out).resolve(),flush=True)

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("FATAL:",e,file=sys.stderr); raise

# Research run trigger: cross-sectional funding carry candidate, distinct from prior failed signal families.
