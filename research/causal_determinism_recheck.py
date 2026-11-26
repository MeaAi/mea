#!/usr/bin/env python3
"""MEAFLOW-52 deterministic replay and matched regime/sleeve recheck."""
import json, math
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import funding_carry_liquidation_causal as base

SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
PERIODS=[
 ("2024_H1","2024-01-01","2024-07-01"),
 ("2024_H2","2024-07-01","2025-01-01"),
 ("2025_H1","2025-01-01","2025-07-01"),
 ("2025_H2","2025-07-01","2026-01-01"),
 ("2026_JAN_OCT","2026-01-01","2026-11-01"),
]
POLICIES={
 "combined_reference":{"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"},
 "bull_long_sleeve":{"bull":"long_only","bear":"flat","sideways":"flat","unknown":"flat"},
 "bear_short_sleeve":{"bull":"flat","bear":"short_only","sideways":"flat","unknown":"flat"},
 "bull_long_plus_bear_short":{"bull":"long_only","bear":"short_only","sideways":"flat","unknown":"flat"},
}
def ms(d): return int(datetime.strptime(d,"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)
def compact(v):
 return {k:v.get(k) for k in ("net_return_pct","end_equity_usdt","max_drawdown_pct","liquidated","rebalance_count","hourly_adverse_checks","price_pnl_usdt","funding_pnl_usdt","trading_fees_usdt","slippage_usdt")}
def main():
 months=list(base.months_between("2023-01","2026-10")); loaded={}; errors={}
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs={ex.submit(base.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
  for f in as_completed(fs):
   s=fs[f]
   try:
    _,fund,marks=f.result(); loaded[s]={"fund":fund,"marks":marks}
    print("LOADED",s,"funding",len(fund),"mark_bars",len(marks),flush=True)
   except Exception as e: errors[s]=str(e); print("SKIP",s,str(e),flush=True)
 if len(loaded)<8 or "BTCUSDT" not in loaded: raise RuntimeError("Insufficient data "+json.dumps(errors))
 data={s:loaded[s] for s in sorted(loaded)}
 reversed_data={s:loaded[s] for s in reversed(sorted(loaded))}
 common=dict(slip_bp=2,lookback_days=7,rebalance_days=7,tail_fraction=.20,regime_threshold_pct=5.0,sideways_action="flat")
 results={}; determinism=[]
 for name,start,end in PERIODS:
  period=(ms(start),ms(end))
  aligned=sum(1 for t in data["BTCUSDT"]["fund"] if period[0]<=t<period[1] and sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
  row={"start":start,"end_exclusive":end,"aligned_funding_events":aligned,"fees":{}}
  if aligned<20: row["status"]="skipped_insufficient_data"; results[name]=row; continue
  for fee in (2,5,8):
   key=f"{fee}bp_commission_plus_2bp_slippage_per_side"
   row["fees"][key]={}
   for label,policy in POLICIES.items():
    a=base.run(data,period,1.0,fee,regime_policy=policy,**common)
    b=base.run(reversed_data,period,1.0,fee,regime_policy=policy,**common)
    ca,cb=compact(a),compact(b)
    same=ca==cb
    determinism.append({"period":name,"fee_bp":fee,"policy":label,"identical_under_reversed_load_order":same})
    if not same: raise RuntimeError("Non-deterministic replay "+name+" "+str(fee)+" "+label+" "+json.dumps({"a":ca,"b":cb}))
    row["fees"][key][label]=ca
    print("RESULT",name,fee,label,json.dumps(ca,separators=(",",":")),flush=True)
  results[name]=row
 report={
  "experiment":"MEAFLOW-52 deterministic replay and matched directional sleeve recheck",
  "branch":"research/causal-determinism-recheck-v1",
  "base_simulator_sha_note":"Simulator sorts symbols and breaks tied funding scores lexicographically; identical results are required under reversed dictionary insertion order.",
  "strategy":"7d trailing funding rank, 7d rebalance, 20% tails; BTC trailing 30d mark return thresholds +/-5%; bull both, bear short-only, sideways/unknown flat for combined reference.",
  "capital_usdt":100,"leverage":1,"fees_one_way_bp":[2,5,8],"slippage_one_way_bp":2,
  "data_source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines; ZIP CRC checked; no interpolation.",
  "loaded_symbols":sorted(loaded),"data_errors":errors,
  "timestamp_semantics":"Regime at each decision/funding timestamp uses last completed BTC 1h mark candle at t-1h.",
  "drawdown":"Hourly adverse mark using simultaneous low for longs/high for shorts plus funding-event equity; conservative OHLC stress, not tick accurate.",
  "period_method":"Five fixed chronological calendar windows; each starts from independent 100 USDT. These dates were previously inspected, so this is sequential revalidation, not pristine OOS.",
  "determinism_check":{"cases":len(determinism),"all_identical":all(x["identical_under_reversed_load_order"] for x in determinism),"results":determinism},
  "policies":{
   "combined_reference":"Bull both directions, bear short-only; sideways/unknown flat.",
   "bull_long_sleeve":"Only bull-regime long positions; otherwise flat.",
   "bear_short_sleeve":"Only bear-regime short positions; otherwise flat.",
   "bull_long_plus_bear_short":"Bull long-only, bear short-only; otherwise flat.",
   "note":"Sleeves independently start with 100 USDT and use full 1x notional when active; returns are not additive."
  },
  "limitations":["Static 13-symbol universe has survivorship bias.","Hourly OHLC adverse stress is not tick-level liquidation simulation.","No maker queue/fill model.","Not an untouched OOS test."],
  "periods":results,
  "decision_rule":"Diagnostic only; no strategy promotion or main-branch changes."
 }
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/causal_determinism_recheck.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
 print("REPORT research-results/causal_determinism_recheck.json",flush=True)
if __name__=="__main__": main()
