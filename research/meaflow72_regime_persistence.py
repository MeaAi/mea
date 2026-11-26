#!/usr/bin/env python3
"""Causal BTC regime persistence confirmation sensitivity for MEAFLOW-72 copy."""
import json, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import funding_carry_liquidation_fixed as sim

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull":"both", "bear":"short_only", "sideways":"hold", "unknown":"flat"}
WINDOWS = {
 "2023_calendar":("2023-01-01T00:00:00+00:00","2024-01-01T00:00:00+00:00"),
 "2024_calendar":("2024-01-01T00:00:00+00:00","2025-01-01T00:00:00+00:00"),
 "2025_jan_to_sep":("2025-01-01T00:00:00+00:00","2025-09-06T18:24:00+00:00"),
 "2025_sep_to_2026_oct":("2025-09-06T18:24:00+00:00","2026-10-31T16:00:00+00:00"),
}
CAPS={"uncapped":None,"bear_cap_20pct":{"bear":.20}}
CONFIRM_HOURS=[0,6,24,72]
def ms(s): return int(datetime.fromisoformat(s).timestamp()*1000)
def iso(t): return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()

def main():
 months=list(sim.months_between("2023-01","2026-10"))
 data,errors={},{}
 with ThreadPoolExecutor(max_workers=8) as pool:
  futures={pool.submit(sim.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
  for f in as_completed(futures):
   sym=futures[f]
   try:
    _,fund,marks=f.result();data[sym]={"fund":fund,"marks":marks}
    print("LOADED",sym,len(fund),len(marks),flush=True)
   except Exception as e:
    errors[sym]=str(e);print("SKIP",sym,str(e),flush=True)
 if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("Insufficient symbols "+json.dumps(errors))
 data={s:data[s] for s in sorted(data)}
 aligned=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
 report={}
 keep=("net_return_pct","end_equity_usdt","max_drawdown_pct","maxdd_peak_time_utc","maxdd_trough_time_utc","rebalance_count","liquidated","price_pnl_usdt","funding_pnl_usdt","trading_fees_usdt","slippage_usdt","market_regime_attribution","regime_confirmation_hours")
 for name,(a,b) in WINDOWS.items():
  events=[t for t in aligned if ms(a)<=t<=ms(b)]
  if len(events)<100: report[name]={"error":"insufficient aligned events"};continue
  report[name]={"period_utc":[iso(events[0]),iso(events[-1])],"event_count":len(events),"configs":{}}
  for cap_name,cap in CAPS.items():
   for hours in CONFIRM_HOURS:
    result=sim.run(data,(events[0],events[-1]),1.0,5,slip_bp=2,lookback_days=7,rebalance_days=7,tail_fraction=.20,regime_policy=POLICY,regime_threshold_pct=5.0,sideways_action="hold",sideways_retention_fraction=1.0,max_symbol_exposure_pct=cap,regime_confirmation_hours=hours)
    key=f"{cap_name}_confirm_{hours}h"
    report[name]["configs"][key]={k:result[k] for k in keep}
    print("RESULT",name,key,json.dumps(report[name]["configs"][key],separators=(",",":")),flush=True)
 output={
  "experiment":"MEAFLOW-72 causal BTC regime persistence confirmation",
  "branch":"research/meaflow72-bear-cohort-attribution-v1",
  "purpose":"Test whether requiring the BTC trailing-30d +/-5% regime label to persist for 0, 6, 24, or 72 completed hourly observations reduces regime whipsaw. During confirmation, retain the raw regime observed at the start of the confirmation interval. This is causal and uses no future data.",
  "source":"Free official Binance Vision monthly fundingRate + 1h markPriceKlines",
  "loaded_symbols":list(data),"data_errors":errors,"capital_usdt":100,"leverage":1,
  "costs":"5 bp fee one-way + 2 bp slippage one-way",
  "base_strategy":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d mark-price +/-5%; bull both, bear short-only, sideways hold, unknown flat.",
  "confirmation_hours":CONFIRM_HOURS,"risk_policies":CAPS,"windows":report,
  "cautions":["Previously inspected historical periods; exploratory, not pristine OOS.","Confirmation delays regime transitions; this is a causal delay test, not a new predictive indicator.","1h mark OHLC adverse-extreme stress, not Binance tick-level liquidation engine; static 0.5% MMR and 1% liquidation-fee proxy.","No maker queue/partial fills; fixed slippage; static 13-symbol universe survivorship bias."]
 }
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/meaflow72_regime_persistence.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
 print("REPORT research-results/meaflow72_regime_persistence.json",flush=True)
if __name__=="__main__":main()
