#!/usr/bin/env python3
"""EXP-038: causal STH-SOPR overlay test on a frozen MEAFLOW-72 simulator copy."""
import bisect, copy, json, math, re, shutil, sys, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import funding_carry_liquidation_causal as base

SOPR_URL = "https://blackalmanak.com/data/charts/sth-sopr.json"
SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}

def download_sopr():
    req=urllib.request.Request(SOPR_URL,headers={"User-Agent":"Mozilla/5.0 MEAFLOW research"})
    with urllib.request.urlopen(req,timeout=90) as r: raw=r.read()
    Path("research-output").mkdir(exist_ok=True)
    Path("research-output/sth-sopr-source.json").write_bytes(raw)
    obj=json.loads(raw)
    rows=[]
    # Black Almanak schema: {"rows":[{"d":"YYYY-MM-DD","values":[sth_sopr, btc_price]}, ...]}
    source_rows=obj.get("rows",[]) if isinstance(obj,dict) else []
    for row in source_rows:
        try:
            dt=str(row["d"])[:10]
            v=float(row["values"][0])
            if math.isfinite(v) and 0.5<v<1.5: rows.append((dt,v))
        except (KeyError,IndexError,TypeError,ValueError):
            continue
    dedup={d:v for d,v in rows if 0.5<v<1.5}
    if len(dedup)<500:
        raise RuntimeError("Could not parse >=500 daily STH-SOPR rows. JSON top-level="+str(type(obj).__name__)+" keys="+str(list(obj)[:20] if isinstance(obj,dict) else "not-dict")+" sample="+raw[:1200].decode("utf-8","replace"))
    print("SOPR rows",len(dedup),"range",min(dedup),max(dedup),"sample",list(sorted(dedup.items()))[:3],flush=True)
    return dedup

def trailing_avg(series, ts):
    # Only use fully closed UTC days strictly before the decision timestamp.
    day=datetime.fromtimestamp(ts/1000,timezone.utc).date()
    vals=[]
    for i in range(1,8):
        d=(day-timedelta(days=i)).isoformat()
        if d not in series: return None
        vals.append(series[d])
    return sum(vals)/len(vals)

def make_sopr_sim(series):
    # Isolated copy of the existing causal simulator; only inserts a causal
    # overlay immediately before target turnover is calculated.
    src=Path("research/funding_carry_liquidation_causal.py").read_text(encoding="utf-8")
    old="def run(data,period,lev,fee_bp,slip_bp=2,mmr=.005,liq_fee=.01,lookback_days=7,rebalance_days=7,tail_fraction=.20,side_mode='both',regime_filter=None,regime_policy=None,regime_threshold_pct=5.0,trade_universe=None,sideways_action='flat',sideways_confirm_hours=1):"
    new="def run(data,period,lev,fee_bp,slip_bp=2,mmr=.005,liq_fee=.01,lookback_days=7,rebalance_days=7,tail_fraction=.20,side_mode='both',regime_filter=None,regime_policy=None,regime_threshold_pct=5.0,trade_universe=None,sideways_action='flat',sideways_confirm_hours=1,sopr_series=None,sopr_mode='baseline',sopr_threshold=1.0):"
    if old not in src: raise RuntimeError("Simulator signature changed; refusing unsafe patch")
    src=src.replace(old,new,1)
    anchor="    turnover=sum(abs((target[s]-qty[s])*px[s]) for s in symbols if s in px)"
    inject="""    # EXP-038 overlay: the seven prior CLOSED UTC daily STH-SOPR observations.
    # Missing values disable the overlay (never backfill from future data).
    if sopr_series is not None and sopr_mode!='baseline':
     avg=trailing_avg(sopr_series,t)
     if avg is not None and avg < sopr_threshold:
      if sopr_mode=='flat_below':
       target={s:0. for s in symbols}
      elif sopr_mode=='half_below':
       target={s:q*0.5 for s,q in target.items()}
      elif sopr_mode=='freeze_below':
       target=qty.copy()
      elif sopr_mode=='recovery_2d':
       prev_day=(datetime.fromtimestamp(t/1000,timezone.utc).date()-timedelta(days=1))
       prev_avg=trailing_avg(sopr_series,int(datetime.combine(prev_day,datetime.min.time(),tzinfo=timezone.utc).timestamp()*1000))
       if prev_avg is None or prev_avg < sopr_threshold:
        target={s:0. for s in symbols}
    turnover=sum(abs((target[s]-qty[s])*px[s]) for s in symbols if s in px)"""
    if src.count(anchor)!=1: raise RuntimeError("Simulator target turnover anchor not unique; refusing patch")
    src=src.replace(anchor,inject,1)
    # Expose source functions in an isolated namespace; no repository source is edited.
    ns={"__name__":"exp038_isolated_sim","trailing_avg":trailing_avg,"datetime":datetime,"timezone":timezone,"timedelta":timedelta}
    exec(compile(src,"research/funding_carry_liquidation_causal.py [EXP038 isolated copy]","exec"),ns)
    def run(*args,**kwargs):
        kwargs["sopr_series"]=series
        return ns["run"](*args,**kwargs)
    return run

def compact(v):
    keys=("start_equity_usdt","end_equity_usdt","net_return_pct","max_drawdown_pct","liquidated",
          "rebalance_count","hourly_adverse_checks","price_pnl_usdt","funding_pnl_usdt",
          "trading_fees_usdt","slippage_usdt","market_regime_attribution")
    return {k:v[k] for k in keys}

def main():
    sopr=download_sopr()
    months=list(base.months_between("2023-01","2026-10"))
    root=Path("research-output"); data={}; errors={}
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
    events=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
    first,last=events[0],events[-1]
    # Restrict to overlap with closed STH-SOPR data; warm-up is still available before each decision.
    sopr_start=int(datetime.fromisoformat(min(sopr).replace("Z","+00:00")).replace(tzinfo=timezone.utc).timestamp()*1000) if False else int(datetime.strptime(min(sopr),"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)
    sopr_end=int(datetime.strptime(max(sopr),"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)
    first=max(first,sopr_start+8*86400000); last=min(last,sopr_end+86400000)
    start=first+int((last-first)*.70); end=last
    periods={"full_oos":(start,end),"oos_first_half":(start,(start+end)//2),"oos_second_half":((start+end)//2,end)}
    run=make_sopr_sim(sopr)
    variants={"baseline":("baseline",1.0),"flat_when_sopr_7d_below_1":("flat_below",1.0),
              "half_exposure_when_sopr_7d_below_1":("half_below",1.0),
              "freeze_new_positions_when_sopr_7d_below_1":("freeze_below",1.0),
              "wait_for_2d_recovery_above_1":("recovery_2d",1.0)}
    out={}
    for pname,period in periods.items():
        out[pname]={}
        for label,(mode,threshold) in variants.items():
            v=run(data,period,1.0,5,slip_bp=2,lookback_days=7,rebalance_days=7,tail_fraction=.20,
                  regime_policy=POLICY,regime_threshold_pct=5.0,sideways_action="hold",
                  sopr_mode=mode,sopr_threshold=threshold)
            out[pname][label]=compact(v)
            print("RESULT",pname,label,json.dumps(compact(v),separators=(",",":")),flush=True)
    report={
      "experiment":"EXP-038 STH-SOPR causal risk overlay",
      "branch":"research/exp038-sth-sopr",
      "baseline":"Frozen MEAFLOW-72 rules: 7d funding lookback, 7d rebalance, 20% tails; BTC 30d regime +/-5%; bull both, bear short-only, sideways hold; 100 USDT, 1x.",
      "sopr_source":"Black Almanak BTC STH-SOPR daily JSON, computed from public Bitcoin blockchain data; source caveats apply.",
      "sopr_source_url":SOPR_URL,"sopr_rows":len(sopr),"sopr_first_date":min(sopr),"sopr_last_date":max(sopr),
      "data_source":"Official Binance Vision USD-M monthly fundingRate and 1h markPriceKlines",
      "loaded_symbols":list(data),"data_errors":errors,
      "periods_utc":{k:{"start":datetime.fromtimestamp(v[0]/1000,timezone.utc).isoformat(),"end":datetime.fromtimestamp(v[1]/1000,timezone.utc).isoformat()} for k,v in periods.items()},
      "capital_usdt":100,"leverage":1,"costs":"5bp fee one-way + 2bp slippage one-way",
      "timing":"At each decision timestamp, use only the seven completed UTC daily STH-SOPR observations strictly before that timestamp; no same-day/future data.",
      "variants":{k:v[0] for k,v in variants.items()},"results":out,
      "limitations":["Black Almanak methodology differs from some commercial STH-SOPR implementations; daily aggregate includes self-transfers and does not identify actual sales.",
       "The source begins 2023-01-01; no pre-2023 test is possible with this series.",
       "Hourly adverse drawdown and liquidation remain simulator approximations, not exchange liquidation engine.",
       "Static 13-symbol universe has survivorship bias; data availability and OOS window must be reported."],
      "decision_rule":"Promote no change unless net return increases AND hourly adverse-mark max drawdown becomes less negative versus matched baseline, with robustness across OOS subwindows."
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp038_sth_sopr.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT_READY research-results/exp038_sth_sopr.json",flush=True)

if __name__=="__main__": main()
