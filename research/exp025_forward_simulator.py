#!/usr/bin/env python3
"""Conservative liquidation-aware cross-sectional funding carry simulation.
Free Binance Vision markPriceKlines + fundingRate; no credentials or orders.
This is a portfolio-level approximation, not Binance's private liquidation engine.
"""
import argparse,bisect,csv,hashlib,io,json,math,time,urllib.request,zipfile
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed

BASE="https://data.binance.vision/data/futures/um/monthly"
DAY=86400000
LEVERS=(1.0,1.25,1.5,2.0,2.5,3.0)

def months_between(a,b):
 y,m=map(int,a.split("-")); ey,em=map(int,b.split("-"))
 while (y,m)<=(ey,em):
  yield f"{y:04d}-{m:02d}"; m+=1
  if m==13:y,m=y+1,1

def download(url,path):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and path.stat().st_size:return
 tmp=Path(str(path)+".part")
 for i in range(4):
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
   with urllib.request.urlopen(req,timeout=90) as r,tmp.open("wb") as f:
    while True:
     b=r.read(1<<20)
     if not b:break
     f.write(b)
   tmp.replace(path);return
  except Exception:
   tmp.unlink(missing_ok=True);time.sleep(2**i)
 raise RuntimeError("download failed: "+url)

def verified_download(url,path):
 # Binance monthly archive sidecars are intermittently unavailable; validate ZIP CRC in readzip.
 download(url,path)

def readzip(path,kind):
 z=zipfile.ZipFile(path)
 if z.testzip() is not None:raise RuntimeError("corrupt ZIP "+str(path))
 n=next(x for x in z.namelist() if x.endswith(".csv"))
 f=io.TextIOWrapper(z.open(n),encoding="utf-8-sig",newline="")
 out={}
 for row in csv.reader(f):
  try:
   t=int(float(row[0]))
   if kind=="mark":
    vals=tuple(float(row[i]) for i in (1,2,3,4))
    if all(math.isfinite(x) and x>0 for x in vals):out[t]=vals
   else:
    rate=float(row[2])
    if math.isfinite(rate):out[t]=rate
  except (ValueError,IndexError):pass
 f.close();z.close();return out

def load_symbol(sym,months,root):
 fund={};marks={}
 for mo in months:
  fn=f"{sym}-fundingRate-{mo}.zip"
  fp=root/"cache"/sym/"funding"/fn
  verified_download(f"{BASE}/fundingRate/{sym}/{fn}",fp);fund.update(readzip(fp,"fund"))
  mn=f"{sym}-1h-{mo}.zip"
  mp=root/"cache"/sym/"mark"/mn
  verified_download(f"{BASE}/markPriceKlines/{sym}/1h/{mn}",mp);marks.update(readzip(mp,"mark"))
 return sym,fund,marks

def run(data,period,lev,fee_bp,slip_bp=2,mmr=.005,liq_fee=.01,lookback_days=7,rebalance_days=7,tail_fraction=.20,side_mode='both',regime_filter=None,regime_policy=None,regime_threshold_pct=5.0,trade_universe=None,sideways_action='flat',sideways_confirm_hours=1):
 symbols=sorted(data); trade_symbols=sorted(trade_universe) if trade_universe is not None else symbols; first,last=period
 if not set(trade_symbols).issubset(set(symbols)) or 'BTCUSDT' not in data: raise ValueError('invalid trade universe or missing BTC regime benchmark')
 mark_times={s:sorted(data[s]["marks"]) for s in symbols}
 all_events=sorted(set(t for s in symbols for t in data[s]["fund"] if first<=t<=last))
 events=[t for t in all_events if sum(t in data[s]["fund"] and t in data[s]["marks"] for s in symbols)>=math.ceil(.8*len(symbols))]
 if len(events)<60:raise RuntimeError("insufficient aligned funding events for short forward window")
 equity=100.; peak=100.; maxdd=0.; qty={s:0. for s in symbols}; prev={}; last_rebal=None
 fee_total=slip_total=price_pnl=funding_pnl=0.; liquidated=False; liq_time=None; liq_equity=None; last_regime=None
 price_by_symbol={z:0. for z in symbols}; funding_by_symbol={z:0. for z in symbols}; fees_by_symbol={z:0. for z in symbols}; slippage_by_symbol={z:0. for z in symbols}
 cohort_qty={z:{k:0. for k in ('bull','bear','sideways','unknown')} for z in symbols}
 entry_regime_pnl={k:{'price_pnl_usdt':0.,'funding_pnl_usdt':0.} for k in ('bull','bear','sideways','unknown')}
 regime_pnl={k:{'price_pnl_usdt':0.,'funding_pnl_usdt':0.,'fees_usdt':0.,'slippage_usdt':0.} for k in ('bull','bear','sideways','unknown')}
 btc_times=mark_times.get('BTCUSDT',[]); btc_marks=data.get('BTCUSDT',{}).get('marks',{})
 def regime_at(ts):
  j=bisect.bisect_right(btc_times,ts)-1; k=bisect.bisect_right(btc_times,ts-30*DAY)-1
  if j<0 or k<0:return 'unknown'
  ret=btc_marks[btc_times[j]][3]/btc_marks[btc_times[k]][3]-1
  threshold=regime_threshold_pct/100.0
  return 'bull' if ret>threshold else ('bear' if ret<-threshold else 'sideways')
 rebalances=0; hourly_checks=0; hourly_sideways_exits=0; sideways_streak=0; rebalance_log=[]
 lookback=lookback_days*DAY; interval=rebalance_days*DAY
 for ix,t in enumerate(events):
  # Walk the union of hourly mark candles once; update portfolio equity close-to-close.
  current=prev.copy()
  if ix and current:
   start=events[ix-1]
   for ht in range(start,t,3600000):
    # At ht the current candle has just opened. Only the candle at ht-1h is complete.
    completed_regime=regime_at(ht-3600000)
    if completed_regime=='sideways': sideways_streak += 1
    else: sideways_streak = 0
    if sideways_action=='immediate_flat' and sideways_streak>=sideways_confirm_hours and any(qty[z] for z in symbols):
     # Execute at this hour's OPEN, after N completed sideways candles; account any close-to-open gap.
     gap_step=0.
     for z in symbols:
      bar=data[z]["marks"].get(ht)
      if z in current and bar is not None:
       op=bar[0]
       if qty[z]:
        dp=qty[z]*(op-current[z]);gap_step+=dp;price_by_symbol[z]+=dp
        regime_pnl[completed_regime]['price_pnl_usdt']+=dp
        for cohort,cohort_q in cohort_qty[z].items(): entry_regime_pnl[cohort]['price_pnl_usdt']+=cohort_q*(op-current[z])
       current[z]=op
     equity+=gap_step;price_pnl+=gap_step
     exit_turnover=sum(abs(qty[z]*current[z]) for z in symbols if qty[z] and z in current)
     exit_fee=exit_turnover*fee_bp/10000;exit_slip=exit_turnover*slip_bp/10000
     equity-=exit_fee+exit_slip;fee_total+=exit_fee;slip_total+=exit_slip
     regime_pnl[completed_regime]['fees_usdt']+=exit_fee;regime_pnl[completed_regime]['slippage_usdt']+=exit_slip
     for z in symbols:
      tr=abs(qty[z]*current[z]) if qty[z] and z in current else 0.
      fees_by_symbol[z]+=tr*fee_bp/10000;slippage_by_symbol[z]+=tr*slip_bp/10000
      qty[z]=0.
      for cohort in cohort_qty[z]: cohort_qty[z][cohort]=0.
     hourly_sideways_exits+=1; sideways_streak=0
    worst=equity;notion=0.
    for z in symbols:
     q=qty[z]
     bar=data[z]["marks"].get(ht)
     if not q or z not in current or bar is None:continue
     o,h,l,cl=bar;adverse=l if q>0 else h
     worst+=q*(adverse-current[z]);notion+=abs(q*adverse)
    hourly_checks+=1
    # Track adverse intrabar portfolio equity using simultaneous adverse extremes.
    peak=max(peak,equity)
    maxdd=min(maxdd,(worst/peak-1)*100 if peak else -100)
    if worst<=notion*(mmr+liq_fee):
     equity=max(0.,worst-notion*liq_fee);liquidated=True
     liq_time=datetime.fromtimestamp(ht/1000,timezone.utc).isoformat();liq_equity=equity
     break
    step=0.
    for z in symbols:
     q=qty[z];bar=data[z]["marks"].get(ht)
     if z in current and bar is not None:
      cl=bar[3]
      if q:
       dp=q*(cl-current[z]);step+=dp;price_by_symbol[z]+=dp;regime_pnl[completed_regime]['price_pnl_usdt']+=dp
       for cohort,cohort_q in cohort_qty[z].items(): entry_regime_pnl[cohort]['price_pnl_usdt']+=cohort_q*(cl-current[z])
      current[z]=cl
    equity+=step;price_pnl+=step
   if liquidated:break
  px={}
  for s in symbols:
   if s in current:px[s]=current[s]
   else:
    j=bisect.bisect_left(mark_times[s],t)-1
    if j>=0:px[s]=data[s]["marks"][mark_times[s][j]][3]
  rates={s:data[s]["fund"][t] for s in symbols if t in data[s]["fund"]}
  # Funding cashflow for positions held across this settlement.
  fpnl=0.
  rg=regime_at(t-3600000)  # last fully completed 1h mark candle at settlement time
  for z in symbols:
   if qty[z] and z in px and z in rates:
    v=-qty[z]*px[z]*rates[z];fpnl+=v;funding_by_symbol[z]+=v;regime_pnl[rg]['funding_pnl_usdt']+=v
    for cohort,cohort_q in cohort_qty[z].items(): entry_regime_pnl[cohort]['funding_pnl_usdt']+=-cohort_q*px[z]*rates[z]
  equity+=fpnl;funding_pnl+=fpnl
  if equity<=0:liquidated=True;liq_time=datetime.fromtimestamp(t/1000,timezone.utc).isoformat();liq_equity=0.;equity=0.;break
  if last_rebal is None and t>=first+lookback or last_rebal is not None and (t-last_rebal>=interval or ((regime_filter is not None or regime_policy is not None) and rg!=last_regime)):
   scores={}
   for s in trade_symbols:
    vals=[r for et,r in data[s]["fund"].items() if t-lookback<et<=t]
    if len(vals)>=12 and s in px:scores[s]=sum(vals)
   ordered=sorted(scores,key=lambda s:(scores[s],s));k=max(1,int(len(ordered)*tail_fraction))
   if len(ordered)>=2*k:
    longs=ordered[:k];shorts=ordered[-k:];target={s:0. for s in symbols}
    active_mode=side_mode
    if regime_policy is not None:
     active_mode=regime_policy.get(rg,'flat')
    elif regime_filter is not None and rg!=regime_filter:
     active_mode='flat'
    if rg=='sideways' and sideways_action=='hold':
     # Freeze the existing portfolio: no new entries or additions while sideways.
     target=qty.copy()
    if active_mode!='flat' and not (rg=='sideways' and sideways_action=='hold'):
     leg=max(0.,equity)*lev*(.5 if active_mode=='both' else 1.0)
     if active_mode in ('both','long_only'):
      for s in longs:target[s]=leg/k/px[s]
     if active_mode in ('both','short_only'):
      for s in shorts:target[s]=-leg/k/px[s]
    turnover=sum(abs((target[s]-qty[s])*px[s]) for s in symbols if s in px)
    order_deltas=[{"symbol":z,"delta_notional_usdt":round((target[z]-qty[z])*px[z],6)} for z in symbols if z in px and abs((target[z]-qty[z])*px[z])>1e-12]
    fee=turnover*fee_bp/10000;slip=turnover*slip_bp/10000
    for z in symbols:
     tr=abs((target[z]-qty[z])*px[z]) if z in px else 0.
     fees_by_symbol[z]+=tr*fee_bp/10000;slippage_by_symbol[z]+=tr*slip_bp/10000
     regime_pnl[rg]['fees_usdt']+=tr*fee_bp/10000;regime_pnl[rg]['slippage_usdt']+=tr*slip_bp/10000
    equity-=fee+slip;fee_total+=fee;slip_total+=slip
    for z in symbols:
     old_q=qty[z];new_q=target[z]
     if old_q:
      same_direction=(new_q!=0 and old_q*new_q>0)
      close_amt=(abs(old_q)-abs(new_q)) if same_direction and abs(new_q)<abs(old_q) else (abs(old_q) if not same_direction else 0.)
      if close_amt>0:
       for cohort in cohort_qty[z]:
        cohort_qty[z][cohort]-=math.copysign(close_amt,old_q)*(abs(cohort_qty[z][cohort])/abs(old_q))
      remaining=old_q-math.copysign(close_amt,old_q)
     else: remaining=0.
     add_q=new_q-remaining
     cohort_qty[z][rg]+=add_q
    qty=target;last_rebal=t;last_regime=rg;rebalances+=1
    rebalance_log.append({"timestamp_utc":datetime.fromtimestamp(t/1000,timezone.utc).isoformat(),"regime":rg,"turnover_usdt":round(turnover,6),"orders":order_deltas})
  # Save latest event mark as anchor for next interval.
  prev=px.copy()
  peak=max(peak,equity);maxdd=min(maxdd,(equity/peak-1)*100 if peak else -100)
  if equity<=0:liquidated=True;equity=0.;break
 gross=sum(abs(qty[s]*prev.get(s,0)) for s in symbols)
 return {"leverage":lev,"fee_bp_one_way":fee_bp,"slippage_bp_one_way":slip_bp,
  "maintenance_margin_rate_assumption":mmr,"liquidation_fee_assumption":liq_fee,
  "start_equity_usdt":100.,"end_equity_usdt":round(equity,6),
  "net_return_pct":round((equity/100-1)*100,4),"max_drawdown_pct":round(maxdd,4),
  "liquidated":liquidated,"liquidation_time_utc":liq_time,"equity_at_liquidation_usdt":liq_equity,
  "price_pnl_usdt":round(price_pnl,6),"funding_pnl_usdt":round(funding_pnl,6),
  "trading_fees_usdt":round(fee_total,6),"slippage_usdt":round(slip_total,6),
  "rebalance_count":rebalances,"rebalance_log":rebalance_log,"hourly_adverse_checks":hourly_checks,"hourly_sideways_exits":hourly_sideways_exits,"sideways_action":sideways_action,"lookback_days":lookback_days,"rebalance_days":rebalance_days,"tail_fraction":tail_fraction,"side_mode":side_mode,"regime_filter":regime_filter,"regime_policy":regime_policy,
  "symbol_attribution":{z:{"price_pnl_usdt":round(price_by_symbol[z],6),"funding_pnl_usdt":round(funding_by_symbol[z],6),"fees_usdt":round(fees_by_symbol[z],6),"slippage_usdt":round(slippage_by_symbol[z],6),"net_contribution_usdt":round(price_by_symbol[z]+funding_by_symbol[z]-fees_by_symbol[z]-slippage_by_symbol[z],6)} for z in symbols},
  "market_regime_attribution":{k:{q:round(v,6) for q,v in vals.items()}|{"net_contribution_usdt":round(vals['price_pnl_usdt']+vals['funding_pnl_usdt']-vals['fees_usdt']-vals['slippage_usdt'],6)} for k,vals in regime_pnl.items()},
  "entry_regime_attribution":{k:{q:round(v,6) for q,v in vals.items()}|{"net_contribution_usdt":round(vals['price_pnl_usdt']+vals['funding_pnl_usdt'],6)} for k,vals in entry_regime_pnl.items()},
  "entry_regime_attribution_note":"Price and funding PnL are assigned to the regime in which each incremental position quantity was opened. Fees/slippage remain attributed by execution-time regime in market_regime_attribution.",
  "model_note":"Cross-portfolio conservative hourly OHLC stress approximation; not exact Binance liquidation engine. Uses simultaneous adverse extremes and static 0.5% MMR assumption."}

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--start",default="2023-01");ap.add_argument("--end",default="2026-10")
 ap.add_argument("--symbols",default="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT")
 ap.add_argument("--out",default="research-results/funding_carry_liquidation.json")
 a=ap.parse_args();months=list(months_between(a.start,a.end));symbols=a.symbols.split(",")
 root=Path("research-output");data={};errors={}
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs={ex.submit(load_symbol,s,months,root):s for s in symbols}
  for f in as_completed(fs):
   s=fs[f]
   try:
    _,fund,marks=f.result();data[s]={"fund":fund,"marks":marks}
    print(s,"funding",len(fund),"mark_bars",len(marks),flush=True)
   except Exception as e:errors[s]=str(e);print("SKIP",s,e,flush=True)
 if len(data)<8:raise RuntimeError("Fewer than 8 usable symbols: "+str(errors))
 times=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
 first,last=times[0],times[-1];span=last-first
 cuts={"train":(first+7*DAY,first+int(span*.5)),"validation":(first+int(span*.5),first+int(span*.7)),"oos":(first+int(span*.7),last)}
 results={}
 for name,period in cuts.items():
  results[name]={}
  for lev in LEVERS:
   results[name][f"{lev:g}x"]={}
   for fee in (2,5,8):
    v=run(data,period,lev,fee,slip_bp=2)
    results[name][f"{lev:g}x"][f"fee_{fee}bp"]=v
    print("RESULT",name,lev,fee,json.dumps(v,separators=(",",":")),flush=True)
 # Robustness diagnostics are evaluated only on the fixed OOS window.
 # Long-only and short-only each use 100% notional at 1x; combined uses 50/50.
 oos_sides={}
 for mode in ("both","long_only","short_only"):
  oos_sides[mode]=run(data,cuts["oos"],1.0,5,slip_bp=2,side_mode=mode)
 # Leave-one-symbol-out: recompute cross-sectional ranks on the reduced universe.
 leave_one_out={}
 for excluded in symbols:
  # Keep BTCUSDT in the data as the regime benchmark even when it is
  # excluded from the tradable cross-sectional universe.
  tradable=[s for s in symbols if s!=excluded]
  if len(tradable)>=8:
   leave_one_out[excluded]=run(data,cuts["oos"],1.0,5,slip_bp=2,trade_universe=tradable)
 for label,excluded_set in {
  "without_BCH": {"BCHUSDT"},
  "without_ETH": {"ETHUSDT"},
  "without_BCH_ETH": {"BCHUSDT","ETHUSDT"},
  "without_SOL_AVAX": {"SOLUSDT","AVAXUSDT"},
 }.items():
  # Benchmark data remains available; excluded assets cannot be selected/traded.
  tradable=[s for s in symbols if s not in excluded_set]
  leave_one_out[label]=run(data,cuts["oos"],1.0,5,slip_bp=2,trade_universe=tradable)
 # Independent OOS regime tests: hold the strategy only during one regime, flatten at regime transitions.
 regime_tests={}
 for regime_name in ("bull","bear","sideways"):
  regime_tests[regime_name]=run(data,cuts["oos"],1.0,5,slip_bp=2,regime_filter=regime_name)
 # Regime-aware decision policies are compared on validation only, then frozen for OOS.
 # The regime state uses only BTC mark-price information available at the decision timestamp.
 regime_policies={
  "bull_long_bear_short_sideways_flat":{"bull":"long_only","bear":"short_only","sideways":"flat","unknown":"flat"},
  "bull_both_bear_short_sideways_flat":{"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"},
  "bull_long_bear_both_sideways_flat":{"bull":"long_only","bear":"both","sideways":"flat","unknown":"flat"},
  "bull_both_bear_both_sideways_flat":{"bull":"both","bear":"both","sideways":"flat","unknown":"flat"},
 }
 policy_validation={}
 for policy_name,policy in regime_policies.items():
  policy_validation[policy_name]=run(data,cuts["validation"],1.0,5,slip_bp=2,regime_policy=policy)
 eligible_policies=[(n,v) for n,v in policy_validation.items() if v["max_drawdown_pct"]>=-25 and not v["liquidated"]]
 chosen_policy_name,chosen_policy_result=max(eligible_policies or list(policy_validation.items()),key=lambda x:x[1]["net_return_pct"])
 # Threshold sensitivity: choose threshold on validation only, then freeze before OOS.
 chosen_mapping=regime_policies[chosen_policy_name]
 threshold_validation={}
 for threshold in (3.0,5.0,7.0,10.0):
  v=run(data,cuts["validation"],1.0,5,slip_bp=2,regime_policy=chosen_mapping,regime_threshold_pct=threshold)
  threshold_validation[f"{threshold:g}%"]={"net_return_pct":v["net_return_pct"],"max_drawdown_pct":v["max_drawdown_pct"],"liquidated":v["liquidated"]}
 eligible_thresholds=[(float(k.rstrip("%")),v) for k,v in threshold_validation.items() if v["max_drawdown_pct"]>=-25 and not v["liquidated"]]
 chosen_threshold,chosen_threshold_validation=max(eligible_thresholds or [(float(k.rstrip("%")),v) for k,v in threshold_validation.items()],key=lambda x:x[1]["net_return_pct"])
 threshold_oos={}
 for fee in (2,5,8):
  threshold_oos[f"fee_{fee}bp"]=run(data,cuts["oos"],1.0,fee,slip_bp=2,regime_policy=chosen_mapping,regime_threshold_pct=chosen_threshold)
 # Symbol selection uses two non-overlapping validation slices: rank symbols on
 # the first half, compare candidate portfolio sizes on the second half, then freeze for OOS.
 val_start,val_end=cuts["validation"]; val_mid=(val_start+val_end)//2
 discovery=run(data,(val_start,val_mid),1.0,5,slip_bp=2,regime_policy=chosen_mapping,regime_threshold_pct=chosen_threshold)
 ranked_symbols=sorted(discovery["symbol_attribution"],key=lambda z:discovery["symbol_attribution"][z]["net_contribution_usdt"],reverse=True)
 universe_candidates={}
 for n in (5,7,9,11,13):
  selected_symbols=ranked_symbols[:n]
  v=run(data,(val_mid,val_end),1.0,5,slip_bp=2,regime_policy=chosen_mapping,regime_threshold_pct=chosen_threshold,trade_universe=selected_symbols)
  universe_candidates[str(n)]={"symbols":selected_symbols,"validation_net_return_pct":v["net_return_pct"],"validation_max_drawdown_pct":v["max_drawdown_pct"],"validation_liquidated":v["liquidated"]}
 eligible_universes=[(int(n),v) for n,v in universe_candidates.items() if v["validation_max_drawdown_pct"]>=-25 and not v["validation_liquidated"]]
 chosen_universe_n,chosen_universe_result=max(eligible_universes or [(int(n),v) for n,v in universe_candidates.items()],key=lambda x:x[1]["validation_net_return_pct"])
 frozen_symbols=universe_candidates[str(chosen_universe_n)]["symbols"]
 universe_oos={}
 for fee in (2,5,8):
  universe_oos[f"fee_{fee}bp"]=run(data,cuts["oos"],1.0,fee,slip_bp=2,regime_policy=chosen_mapping,regime_threshold_pct=chosen_threshold,trade_universe=frozen_symbols)
 adaptive_policy_oos={}
 for lev in (1.0,1.25,1.5):
  adaptive_policy_oos[f"{lev:g}x"]={}
  for fee in (2,5,8):
   adaptive_policy_oos[f"{lev:g}x"][f"fee_{fee}bp"]=run(data,cuts["oos"],lev,fee,slip_bp=2,regime_policy=regime_policies[chosen_policy_name],regime_threshold_pct=chosen_threshold)
 # Select parameters on validation only, then freeze before OOS evaluation.
 grid=[]
 val_period=cuts["validation"]
 for lb in (3,7,14,28):
  for rb in (3,7,14):
   for frac in (.10,.20,.30):
    v=run(data,val_period,1.0,5,slip_bp=2,lookback_days=lb,rebalance_days=rb,tail_fraction=frac,regime_policy=chosen_mapping,regime_threshold_pct=chosen_threshold)
    grid.append({"lookback_days":lb,"rebalance_days":rb,"tail_fraction":frac,
                 "validation_net_return_pct":v["net_return_pct"],
                 "validation_max_drawdown_pct":v["max_drawdown_pct"],
                 "validation_liquidated":v["liquidated"]})
 eligible=[x for x in grid if x["validation_max_drawdown_pct"]>=-25 and not x["validation_liquidated"]]
 chosen=max(eligible or grid,key=lambda x:x["validation_net_return_pct"])
 selected_oos={}
 for lev in LEVERS:
  selected_oos[f"{lev:g}x"]={}
  for fee in (2,5,8):
   selected_oos[f"{lev:g}x"][f"fee_{fee}bp"]=run(
    data,cuts["oos"],lev,fee,slip_bp=2,
    lookback_days=chosen["lookback_days"],rebalance_days=chosen["rebalance_days"],
    tail_fraction=chosen["tail_fraction"],regime_policy=chosen_mapping,
    regime_threshold_pct=chosen_threshold)
 # Compare the historical baseline, parameter-only change, and regime-policy change on identical frozen OOS dates.
 regime_side_by_side={}
 for label,kwargs in {
  'baseline_7d_7d_20pct_no_regime':dict(lookback_days=7,rebalance_days=7,tail_fraction=.20),
  'same_parameters_7d_14d_10pct_no_regime':dict(lookback_days=7,rebalance_days=14,tail_fraction=.10),
  'same_parameters_with_regime_policy':dict(lookback_days=7,rebalance_days=14,tail_fraction=.10,regime_policy=chosen_mapping,regime_threshold_pct=chosen_threshold),
 }.items():
  v=run(data,cuts['oos'],1.0,5,slip_bp=2,**kwargs)
  regime_side_by_side[label]={k:v[k] for k in ('net_return_pct','max_drawdown_pct','end_equity_usdt','rebalance_count','market_regime_attribution','entry_regime_attribution')}
 # Re-run the original +52%-era configuration under the corrected hourly adverse drawdown method.
 # Original parameters: 7d funding lookback, 7d rebalance, 20% tails, validation-frozen BTC regime policy.
 original_52_reference=run(data,cuts['oos'],1.0,5,slip_bp=2,
  lookback_days=7,rebalance_days=7,tail_fraction=.20,
  regime_policy=chosen_mapping,regime_threshold_pct=chosen_threshold)
 original_52_reference={k:original_52_reference[k] for k in ('net_return_pct','end_equity_usdt','max_drawdown_pct','rebalance_count','hourly_adverse_checks','hourly_sideways_exits','price_pnl_usdt','funding_pnl_usdt','trading_fees_usdt','slippage_usdt','liquidated','market_regime_attribution','symbol_attribution')}
 # Matched OOS comparison of sideways handling. Parameters, policy, dates and costs are frozen.
 sideways_management={}
 for action in ('flat','hold','immediate_flat'):
  v=run(data,cuts['oos'],1.0,5,slip_bp=2,
   lookback_days=chosen['lookback_days'],rebalance_days=chosen['rebalance_days'],
   tail_fraction=chosen['tail_fraction'],regime_policy=chosen_mapping,
   regime_threshold_pct=chosen_threshold,sideways_action=action)
  sideways_management[action]={k:v[k] for k in ('net_return_pct','end_equity_usdt','max_drawdown_pct','rebalance_count','hourly_sideways_exits','price_pnl_usdt','funding_pnl_usdt','trading_fees_usdt','slippage_usdt','liquidated')}
 # Parameter-matched no-regime reference, to isolate the value of the BTC filter.
 v=run(data,cuts['oos'],1.0,5,slip_bp=2,
  lookback_days=chosen['lookback_days'],rebalance_days=chosen['rebalance_days'],
  tail_fraction=chosen['tail_fraction'])
 sideways_management['no_regime_reference']={k:v[k] for k in ('net_return_pct','end_equity_usdt','max_drawdown_pct','rebalance_count','hourly_sideways_exits','price_pnl_usdt','funding_pnl_usdt','trading_fees_usdt','slippage_usdt','liquidated')}
 # Diagnostics for the validation-selected configuration, all on the already-frozen OOS window.
 selected_config_robustness={"leave_one_symbol_out":{},"slippage_stress":{},"oos_halves":{}}
 for excluded in symbols:
  tradable=[s for s in symbols if s!=excluded]
  if len(tradable)>=8:
   v=run(data,cuts["oos"],1.0,5,slip_bp=2,
    lookback_days=chosen["lookback_days"],rebalance_days=chosen["rebalance_days"],
    tail_fraction=chosen["tail_fraction"],regime_policy=chosen_mapping,
    regime_threshold_pct=chosen_threshold,trade_universe=tradable)
   selected_config_robustness["leave_one_symbol_out"][excluded]={"net_return_pct":v["net_return_pct"],"max_drawdown_pct":v["max_drawdown_pct"],"liquidated":v["liquidated"]}
 for slip in (2,4,6,8):
  v=run(data,cuts["oos"],1.0,5,slip_bp=slip,
   lookback_days=chosen["lookback_days"],rebalance_days=chosen["rebalance_days"],
   tail_fraction=chosen["tail_fraction"],regime_policy=chosen_mapping,
   regime_threshold_pct=chosen_threshold)
  selected_config_robustness["slippage_stress"][f"{slip}bp_one_way"]={"net_return_pct":v["net_return_pct"],"max_drawdown_pct":v["max_drawdown_pct"],"end_equity_usdt":v["end_equity_usdt"],"liquidated":v["liquidated"]}
 oos_start,oos_end=cuts["oos"];oos_mid=(oos_start+oos_end)//2
 for label,period in (("first_half",(oos_start,oos_mid)),("second_half",(oos_mid,oos_end))):
  v=run(data,period,1.0,5,slip_bp=2,
   lookback_days=chosen["lookback_days"],rebalance_days=chosen["rebalance_days"],
   tail_fraction=chosen["tail_fraction"],regime_policy=chosen_mapping,
   regime_threshold_pct=chosen_threshold)
  selected_config_robustness["oos_halves"][label]={"net_return_pct":v["net_return_pct"],"max_drawdown_pct":v["max_drawdown_pct"],"start_utc":datetime.fromtimestamp(period[0]/1000,timezone.utc).isoformat(),"end_utc":datetime.fromtimestamp(period[1]/1000,timezone.utc).isoformat(),"liquidated":v["liquidated"]}
 report={"strategy":"7d trailing funding rank, weekly rebalance, lowest 20% long/highest 20% short",
  "source":"Free official Binance Vision monthly fundingRate + 1h markPriceKlines",
  "period_utc":{"first":datetime.fromtimestamp(first/1000,timezone.utc).isoformat(),"last":datetime.fromtimestamp(last/1000,timezone.utc).isoformat()},
  "universe":list(data),"data_errors":errors,"capital_usdt":100,
  "splits":"chronological 50/20/30; fixed strategy; no OOS tuning",
  "regime_definition":"At each hourly/event timestamp, use trailing 30-day BTC mark-price return: bull > +5%, bear < -5%, otherwise sideways; no future data. Attribution is incremental PnL/cost by timestamp, not a separately rebalanced regime strategy.",
  "assumptions":{"slippage":"2 bp one-way on rebalance turnover, in addition to 2/5/8 bp fee sensitivity",
   "maintenance_margin":"static conservative 0.5% of stressed gross notional; historical symbol-specific Binance brackets unavailable in this public dataset",
   "liquidation_fee":"1% of stressed gross notional proxy",
   "intrabar":"1h mark-price OHLC; simultaneous adverse low for longs and high for shorts, conservative but not tick-accurate",
   "drawdown":"Maximum drawdown now updates at every hourly adverse mark using simultaneous adverse OHLC extremes, as well as funding-event equity; conservative stress estimate.",
   "margin_mode":"cross-portfolio approximation; funding cashflow at settlement; positions resized weekly",
   "limitations":["not exact Binance liquidation engine","static MMR instead of historical symbol-specific tier brackets","hourly OHLC cannot reconstruct tick order or exact liquidation price","spread and market impact beyond fixed slippage are not modeled","static universe survivorship bias"]},
  "regime_tests_oos_1x_5bp_fee_2bp_slippage":regime_tests,
  "matched_regime_comparison_oos_1x_5bp_fee_2bp_slippage":regime_side_by_side,"sideways_management_oos_1x_5bp_fee_2bp_slippage":sideways_management,"original_52_reference_corrected_drawdown_oos_1x_5bp_fee_2bp_slippage":original_52_reference,
  "symbol_universe_selection":{"selection_protocol":"Rank by net symbol contribution on first half of validation; compare top-5/7/9/11/13 portfolios on second half; freeze selected symbols before OOS.","discovery_period_utc":[datetime.fromtimestamp(val_start/1000,timezone.utc).isoformat(),datetime.fromtimestamp(val_mid/1000,timezone.utc).isoformat()],"selection_period_utc":[datetime.fromtimestamp(val_mid/1000,timezone.utc).isoformat(),datetime.fromtimestamp(val_end/1000,timezone.utc).isoformat()],"discovery_ranking":ranked_symbols,"candidate_results":universe_candidates,"chosen_count":chosen_universe_n,"chosen_symbols":frozen_symbols,"chosen_validation":universe_candidates[str(chosen_universe_n)],"frozen_oos_1x":universe_oos},
  "regime_policy_sweep":{"selection_period":"validation only","selection_rule":"Highest validation net return among policies with max drawdown >= -25% and no liquidation; frozen before OOS.","validation_results":{k:{"net_return_pct":v["net_return_pct"],"max_drawdown_pct":v["max_drawdown_pct"],"liquidated":v["liquidated"]} for k,v in policy_validation.items()},"chosen_policy":chosen_policy_name,"chosen_policy_mapping":regime_policies[chosen_policy_name],"chosen_policy_validation":chosen_policy_result,"chosen_policy_oos":adaptive_policy_oos,
   "threshold_sensitivity":{"candidates_pct":[3,5,7,10],"selection_period":"validation only","validation_results":threshold_validation,"chosen_threshold_pct":chosen_threshold,"chosen_threshold_validation":chosen_threshold_validation,"frozen_threshold_oos_1x":threshold_oos}},
  "robustness_tests":{"oos_side_decomposition_1x_5bp_fee_2bp_slippage":oos_sides,"leave_one_symbol_out_1x_5bp_fee_2bp_slippage":leave_one_out,"note":"Each reduced tradable-universe test recalculates cross-sectional ranks using only remaining tradable symbols; BTC mark-price data is retained solely as the ex-ante regime benchmark even when BTCUSDT is excluded from trading; fixed original OOS dates; not re-tuned."},"results":results,"parameter_sweep":{"selection_rule":"Choose highest validation net return at 1x, 5bp fee + 2bp slippage, subject to max drawdown >= -25%; regime policy and threshold frozen from validation; freeze parameters before OOS. If none eligible, choose highest validation return from full grid.","frozen_regime_policy":regime_policies[chosen_policy_name],"frozen_regime_threshold_pct":chosen_threshold,"grid_size":len(grid),"chosen_on_validation":chosen,"validation_top_10":sorted(grid,key=lambda x:x["validation_net_return_pct"],reverse=True)[:10],"selected_configuration_oos":selected_oos,"selected_configuration_robustness_oos":selected_config_robustness}}
 Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
 print("REPORT",a.out,flush=True)
if __name__=="__main__":main()