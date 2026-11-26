#!/usr/bin/env python3
"""Attribution-only replay of fixed causal MEAFLOW-52 strategy; no tuning."""
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
 keys=("net_return_pct","end_equity_usdt","max_drawdown_pct","liquidated","rebalance_count","hourly_adverse_checks","price_pnl_usdt","funding_pnl_usdt","trading_fees_usdt","slippage_usdt")
 out={k:v.get(k) for k in keys}
 for k in ("symbol_attribution","market_regime_attribution","entry_regime_attribution","entry_regime_attribution_note"):
  out[k]=v.get(k)
 return out
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
 policy={"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}
 common=dict(slip_bp=2,lookback_days=7,rebalance_days=7,tail_fraction=.20,regime_policy=policy,regime_threshold_pct=5.0,sideways_action="flat")
 results={}
 for name,start,end in PERIODS:
  period=(ms(start),ms(end))
  aligned=sum(1 for t in data["BTCUSDT"]["fund"] if period[0]<=t<period[1] and sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
  if aligned<20:
   results[name]={"start":start,"end_exclusive":end,"aligned_funding_events":aligned,"status":"skipped_insufficient_data"}
   continue
  results[name]={"start":start,"end_exclusive":end,"aligned_funding_events":aligned,"fees":{}}
  for fee in (2,5,8):
   out=base.run(data,period,1.0,fee,**common)
   results[name]["fees"][f"{fee}bp_commission_plus_2bp_slippage_per_side"]=compact(out)
   print("PERIOD",name,"FEE",fee,json.dumps(compact(out),separators=(",",":")),flush=True)
 report={
  "experiment":"MEAFLOW-52 fixed causal calendar-period loss attribution; diagnostic only",
  "parent_snapshot":"research/causal-period-robustness-v1",
  "isolated_branch":"research/causal-loss-attribution-v1",
  "baseline_strategy":"7d funding rank, 7d rebalance, 20% tails; bull both sides, bear short-only, sideways/unknown flat; BTC 30d mark return regime thresholds +/-5%",
  "no_parameter_search":True,
  "purpose":"Decompose existing fixed-strategy outcomes by traded symbol, contemporaneous market regime, and position-entry regime. No candidate or policy change is tested.",
  "period_method":"Same five chronological calendar windows as prior fixed causal robustness report; each window independently starts with 100 USDT.",
  "capital_usdt":100,"leverage":1,"fees_one_way_bp":[2,5,8],"slippage_one_way_bp":2,
  "data_source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines; ZIP CRC checked by loader; no interpolation.",
  "data_errors":errors,"loaded_symbols":list(data),
  "drawdown":"Hourly adverse mark using simultaneous low for longs/high for shorts plus event-time equity; conservative OHLC stress, not tick-accurate.",
  "timestamp_semantics":"At decision timestamp t, regime uses BTC mark-price candle at t-1h, the last fully completed hourly candle.",
  "limitations":["Previously inspected periods; sequential diagnostic, not pristine unseen OOS.","Static symbol universe has survivorship bias.","Hourly OHLC adverse stress is not tick-level liquidation simulation.","No maker queue/fill modelling.","Attribution is accounting decomposition, not causal proof; execution costs are allocated by execution-time regime while position PnL is also shown by entry regime."],
  "periods":results,
  "decision_rule":"Diagnostic only. Do not select parameters, infer causal alpha, or promote any strategy from this report."
 }
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/causal_loss_attribution.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
 print("REPORT research-results/causal_loss_attribution.json",flush=True)
if __name__=="__main__": main()
