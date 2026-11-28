#!/usr/bin/env python3
"""EXP-039: causal Binance BTC volume-weighted price zone overlays on frozen MEAFLOW-72."""
import bisect, csv, io, json, math, time, urllib.request, zipfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import funding_carry_liquidation_causal as base

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}
BASE_URL = "https://data.binance.vision/data/futures/um/monthly"
HOUR = 3_600_000
DAY = 86_400_000

def load_btc_vwap(months, root):
    """BTC USD-M 1h close*quote-volume VWAP inputs; all bars CRC-checked."""
    closes=[]; qvols=[]; times=[]; metadata=[]
    for month in months:
        name=f"BTCUSDT-1h-{month}.zip"
        path=root/"cache"/"BTCUSDT"/"klines"/"1h"/name
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            url=f"{BASE_URL}/klines/BTCUSDT/1h/{name}"
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 MEAFLOW research"})
            err=None
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(req,timeout=90) as r, path.open("wb") as f:
                        while True:
                            block=r.read(1<<20)
                            if not block: break
                            f.write(block)
                    err=None; break
                except Exception as e:
                    err=str(e); path.unlink(missing_ok=True); time.sleep(2**attempt)
            if err: raise RuntimeError(f"Binance kline download failed {name}: {err}")
        z=zipfile.ZipFile(path)
        if z.testzip() is not None: raise RuntimeError("Corrupt Binance ZIP: "+name)
        member=next((x for x in z.namelist() if x.endswith(".csv")),None)
        if not member: raise RuntimeError("CSV missing: "+name)
        f=io.TextIOWrapper(z.open(member),encoding="utf-8-sig",newline="")
        n=0
        for row in csv.reader(f):
            if len(row)<8: continue
            try:
                ts=int(float(row[0])); close=float(row[4]); quote=float(row[7])
                if close>0 and quote>0 and math.isfinite(close) and math.isfinite(quote):
                    times.append(ts); closes.append(close); qvols.append(quote); n+=1
            except (ValueError,IndexError): continue
        f.close(); z.close()
        metadata.append({"archive":name,"rows":n,"bytes":path.stat().st_size})
        print("VWAP_SOURCE",name,n,flush=True)
    order=sorted(range(len(times)),key=times.__getitem__)
    ts=[times[i] for i in order]; px=[closes[i] for i in order]; qv=[qvols[i] for i in order]
    if len(set(ts))!=len(ts): raise RuntimeError("Duplicate BTC hourly kline timestamps")
    return {"times":ts,"close":px,"quote_volume":qv,"archives":metadata}

def make_vwap_series(raw):
    # Prefix sums make each rolling VWAP query deterministic and O(log n).
    ts=raw["times"]; pv=[0.0]; vv=[0.0]
    for p,v in zip(raw["close"],raw["quote_volume"]):
        pv.append(p*v+pv[-1]); vv.append(v+vv[-1])
    return {"times":ts,"pv":pv,"vol":vv}

def vwap_at(series, decision_ts, days):
    # Use only the last fully CLOSED 1h candle before the decision timestamp.
    last_open=decision_ts-HOUR
    j=bisect.bisect_right(series["times"],last_open)-1
    if j<0:return None
    first_open=series["times"][j]-(days*24-1)*HOUR
    i=bisect.bisect_left(series["times"],first_open,0,j+1)
    vol=series["vol"][j+1]-series["vol"][i]
    if vol<=0:return None
    return (series["pv"][j+1]-series["pv"][i])/vol

def make_sim(series):
    src=Path("research/funding_carry_liquidation_causal.py").read_text(encoding="utf-8")
    old="def run(data,period,lev,fee_bp,slip_bp=2,mmr=.005,liq_fee=.01,lookback_days=7,rebalance_days=7,tail_fraction=.20,side_mode='both',regime_filter=None,regime_policy=None,regime_threshold_pct=5.0,trade_universe=None,sideways_action='flat',sideways_confirm_hours=1):"
    new="def run(data,period,lev,fee_bp,slip_bp=2,mmr=.005,liq_fee=.01,lookback_days=7,rebalance_days=7,tail_fraction=.20,side_mode='both',regime_filter=None,regime_policy=None,regime_threshold_pct=5.0,trade_universe=None,sideways_action='flat',sideways_confirm_hours=1,vwap_series=None,vwap_days=30,vwap_mode='baseline'):"
    if old not in src: raise RuntimeError("Simulator signature changed; refusing unsafe patch")
    src=src.replace(old,new,1)
    anchor="    turnover=sum(abs((target[s]-qty[s])*px[s]) for s in symbols if s in px)"
    inject="""    # EXP-039 causal BTC volume-weighted price overlay. The reference uses
    # completed Binance USD-M 1h klines only; it is NOT holder cost basis.
    if vwap_series is not None and vwap_mode!='baseline':
     ref=vwap_at(vwap_series,t,vwap_days)
     btc=px.get('BTCUSDT')
     if ref is not None and btc is not None and btc < ref:
      if vwap_mode=='flat_below':
       target={s:0. for s in symbols}
      elif vwap_mode=='half_below':
       target={s:q*0.5 for s,q in target.items()}
      elif vwap_mode=='short_only_below':
       target={s:(q if q<0 else 0.) for s,q in target.items()}
    turnover=sum(abs((target[s]-qty[s])*px[s]) for s in symbols if s in px)"""
    if src.count(anchor)!=1: raise RuntimeError("Target turnover anchor not unique; refusing patch")
    src=src.replace(anchor,inject,1)
    ns={"__name__":"exp039_isolated_sim","vwap_at":vwap_at}
    exec(compile(src,"funding_carry_liquidation_causal.py [EXP039 isolated copy]","exec"),ns)
    return ns["run"]

def compact(v):
    keys=("start_equity_usdt","end_equity_usdt","net_return_pct","max_drawdown_pct","liquidated",
          "rebalance_count","hourly_adverse_checks","price_pnl_usdt","funding_pnl_usdt",
          "trading_fees_usdt","slippage_usdt","market_regime_attribution")
    return {k:v[k] for k in keys}

def main():
    months=list(base.months_between("2023-01","2026-10"))
    root=Path("research-output"); root.mkdir(exist_ok=True)
    data={}; errors={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs={pool.submit(base.load_symbol,s,months,root):s for s in SYMBOLS}
        for f in as_completed(futs):
            s=futs[f]
            try:
                _,fund,marks=f.result(); data[s]={"fund":fund,"marks":marks}
                print("LOADED",s,len(fund),len(marks),flush=True)
            except Exception as e:
                errors[s]=str(e); print("SKIP",s,str(e),flush=True)
    if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("Insufficient symbols: "+json.dumps(errors))
    data={s:data[s] for s in sorted(data)}
    events=sorted(t for s in data for t in data[s]["fund"]
                  if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
    first,last=events[0],events[-1]
    vwap_raw=load_btc_vwap(months,root)
    vwap=make_vwap_series(vwap_raw)
    # Match EXP-038 OOS split convention: final 30% of overlapping data.
    warm_start=vwap["times"][0]+155*DAY
    first=max(first,warm_start)
    start=first+int((last-first)*.70); end=last
    mid=(start+end)//2
    periods={"full_oos":(start,end),"oos_first_half":(start,mid),"oos_second_half":(mid,end)}
    run=make_sim(vwap)
    variants={"baseline":("baseline",30)}
    for days in (7,30,155):
        for mode in ("half_below","flat_below","short_only_below"):
            variants[f"btc_{days}d_vwap_{mode}"]=(mode,days)
    out={}
    for pname,period in periods.items():
        out[pname]={}
        for label,(mode,days) in variants.items():
            v=run(data,period,1.0,5,slip_bp=2,lookback_days=7,rebalance_days=7,tail_fraction=.20,
                  regime_policy=POLICY,regime_threshold_pct=5.0,sideways_action="hold",
                  vwap_series=vwap,vwap_days=days,vwap_mode=mode)
            out[pname][label]=compact(v)
            print("RESULT",pname,label,json.dumps(compact(v),separators=(",",":")),flush=True)
    def iso(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()
    report={
      "experiment":"EXP-039 Binance BTC rolling VWAP cost-zone proxy overlays",
      "branch":"research/exp039-binance-vwap",
      "base_sha":"a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1",
      "baseline":"Frozen MEAFLOW-72: 7d funding lookback, 7d rebalance, 20% tails; BTC 30d regime +/-5%; bull both, bear short-only, sideways flat/hold; 100 USDT, 1x.",
      "data_source":"Official Binance Vision USD-M monthly 1h markPriceKlines + fundingRate for portfolio simulator; BTCUSDT 1h USD-M klines close and quote volume for VWAP proxy.",
      "vwap_source":{"symbol":"BTCUSDT","interval":"1h","archives":vwap_raw["archives"],"rows":len(vwap["times"]),"first_bar_open_utc":iso(vwap["times"][0]),"last_bar_open_utc":iso(vwap["times"][-1])},
      "loaded_symbols":list(data),"data_errors":errors,
      "periods_utc":{k:{"start":iso(v[0]),"end":iso(v[1])} for k,v in periods.items()},
      "capital_usdt":100,"leverage":1,"costs":"5bp fee one-way + 2bp slippage one-way",
      "signal":"BTC close below trailing volume-weighted average of hourly close*quote_volume",
      "windows_days":[7,30,155],"overlay_modes":["half_below","flat_below","short_only_below"],
      "timing":"At each funding decision, compare last available BTC close to trailing VWAP from fully completed hourly candles only; the candle beginning at decision timestamp is excluded.",
      "results":out,
      "limitations":["VWAP is a traded-volume price proxy, not actual investor/holder cost basis or on-chain realized price.",
       "USD-M quote volume and mark-price portfolio accounting are different data series; this is a causal risk overlay approximation.",
       "Static 13-symbol universe has survivorship bias; symbol availability errors are reported.",
       "Hourly adverse drawdown and liquidation are portfolio OHLC stress approximations, not the Binance liquidation engine."],
      "decision_rule":"Reject unless net return increases AND hourly adverse-mark maximum drawdown becomes less negative versus matched baseline, with no liquidation and evidence across OOS halves."
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp039_binance_vwap.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT_READY research-results/exp039_binance_vwap.json",flush=True)

if __name__=="__main__": main()
