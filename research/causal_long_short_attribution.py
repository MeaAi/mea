#!/usr/bin/env python3
"""MEAFLOW-52 directional sleeve diagnostic. Fixed policy; no tuning."""
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
def ms(date):
 return int(datetime.strptime(date,"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)
def compact(v):
 return {k:v.get(k) for k in ("net_return_pct","end_equity_usdt","max_drawdown_pct","liquidated","rebalance_count","price_pnl_usdt","funding_pnl_usdt","trading_fees_usdt","slippage_usdt","symbol_attribution")}
def main():
 months=list(base.months_between("2023-01","2026-10")); data={}; errors={}
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs={ex.submit(base.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
  for f in as_completed(fs):
   sym=fs[f]
   try:
    _,fund,marks=f.result(); data[sym]={"fund":fund,"marks":marks}
    print("LOADED",sym,"funding",len(fund),"mark_bars",len(marks),flush=True)
   except Exception as e:
    errors[sym]=str(e); print("SKIP",sym,str(e),flush=True)
 if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("Insufficient data: "+json.dumps(errors))
 policies={
  "combined_reference":{"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"},
  "bull_long_sleeve":{"bull":"long_only","bear":"flat","sideways":"flat","unknown":"flat"},
  "bear_short_sleeve":{"bull":"flat","bear":"short_only","sideways":"flat","unknown":"flat"},
  "bull_long_plus_bear_short":{"bull":"long_only","bear":"short_only","sideways":"flat","unknown":"flat"},
 }
 common=dict(slip_bp=2,lookback_days=7,rebalance_days=7,tail_fraction=.20,regime_threshold_pct=5.0,sideways_action="flat")
 results={}
 for name,start,end in PERIODS:
  period=(ms(start),ms(end))
  aligned=sum(1 for t in data["BTCUSDT"]["fund"] if period[0]<=t<period[1] and sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
  entry={"start":start,"end_exclusive":end,"aligned_funding_events":aligned,"fees":{}}
  if aligned<20:
   entry["status"]="skipped_insufficient_data";results[name]=entry;continue
  for fee in (2,5,8):
   entry["fees"][f"{fee}bp_commission_plus_2bp_slippage_per_side"]={}
   for label,policy in policies.items():
    v=base.run(data,period,1.0,fee,regime_policy=policy,**common)
    entry["fees"][f"{fee}bp_commission_plus_2bp_slippage_per_side"][label]=compact(v)
    print("RESULT",name,fee,label,json.dumps(compact(v),separators=(",",":")),flush=True)
  results[name]=entry
 report={
  "experiment":"MEAFLOW-52 causal long/short sleeve diagnostic; no tuning",
  "branch":"research/causal-long-short-attribution-v1",
  "parent":"research/causal-loss-attribution-v1",
  "strategy":"7d funding rank, 7d rebalance, 20% tails; BTC 30d mark return thresholds +/-5%; bull/short policy fixed",
  "capital_usdt":100,"leverage":1,"fees_one_way_bp":[2,5,8],"slippage_one_way_bp":2,
  "data_source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines; ZIP CRC checked; no interpolation.",
  "loaded_symbols":list(data),"data_errors":errors,
  "timestamp_semantics":"Regime at decision t uses last fully completed BTC 1h mark candle at t-1h.",
  "drawdown":"Hourly adverse mark using simultaneous low for longs/high for shorts plus funding-event equity; OHLC stress, not tick accurate.",
  "method":{
   "combined_reference":"Bull both directions (50% long/50% short); bear short-only.",
   "bull_long_sleeve":"Only bull-regime long book; all bear/sideways/unknown periods flat.",
   "bear_short_sleeve":"Only bear-regime short book; all bull/sideways/unknown periods flat.",
   "bull_long_plus_bear_short":"Bull long-only plus bear short-only.",
   "important":"Each sleeve is independently initialized with 100 USDT and uses 100% notional at 1x when active. Sleeve returns are not additive and are not a decomposition of the combined portfolio. They test standalone directional sleeve quality under identical signal ranking and costs."
  },
  "limitations":["Previously inspected calendar periods; sequential diagnostic, not pristine OOS.","Static 13-symbol universe has survivorship bias.","Hourly OHLC adverse stress is not tick-level liquidation simulation.","No maker queue/fill model.","Separate sleeve portfolios have independent 100 USDT equity and full notional; cannot add sleeve returns to recover combined portfolio return."],
  "periods":results,
  "decision_rule":"Diagnostic only. No parameter selection or strategy promotion from this report."
 }
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/causal_long_short_attribution.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
 print("REPORT research-results/causal_long_short_attribution.json",flush=True)
if __name__=="__main__":main()
