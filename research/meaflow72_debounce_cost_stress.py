#!/usr/bin/env python3
"""MEAFLOW-72 cost stress: raw regime vs causal 3h debounce."""
import json, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import funding_carry_liquidation_fixed as sim

SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY={"bull":"both","bear":"short_only","sideways":"hold","unknown":"flat"}
WINDOWS={
 "2023_calendar":("2023-01-01T00:00:00+00:00","2024-01-01T00:00:00+00:00"),
 "2024_calendar":("2024-01-01T00:00:00+00:00","2025-01-01T00:00:00+00:00"),
 "2025_jan_to_sep":("2025-01-01T00:00:00+00:00","2025-09-06T18:24:00+00:00"),
 "2025_sep_to_2026_oct":("2025-09-06T18:24:00+00:00","2026-10-31T16:00:00+00:00"),
}
CAPS={"uncapped":None,"bear_cap_20pct":{"bear":.20}}
FEE_GRID=(5,8)
SLIP_GRID=(2,4,6,8)
DEBOUNCE=(0,3)

def ms(s): return int(datetime.fromisoformat(s).timestamp()*1000)
def iso(t): return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()

def main():
 months=list(sim.months_between("2023-01","2026-10"))
 data,errors={},{}
 with ThreadPoolExecutor(max_workers=8) as pool:
  fs={pool.submit(sim.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
  for f in as_completed(fs):
   s=fs[f]
   try:
    _,fund,marks=f.result(); data[s]={"fund":fund,"marks":marks}
    print("LOADED",s,len(fund),len(marks),flush=True)
   except Exception as e:
    errors[s]=str(e); print("SKIP",s,str(e),flush=True)
 if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("insufficient symbols "+json.dumps(errors))
 data={s:data[s] for s in sorted(data)}
 aligned=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
 report={}
 for name,(a,b) in WINDOWS.items():
  ev=[t for t in aligned if ms(a)<=t<=ms(b)]
  if len(ev)<100: report[name]={"error":"insufficient aligned events"}; continue
  report[name]={"period_utc":[iso(ev[0]),iso(ev[-1])],"event_count":len(ev),"configs":{}}
  for fee in FEE_GRID:
   for slip in SLIP_GRID:
    for cap_name,cap in CAPS.items():
     for hours in DEBOUNCE:
      key=f"fee{fee}_slip{slip}_{cap_name}_{'raw' if hours==0 else 'debounce_3h'}"
      res=sim.run(data,(ev[0],ev[-1]),1.0,fee,slip_bp=slip,lookback_days=7,rebalance_days=7,tail_fraction=.20,regime_policy=POLICY,regime_threshold_pct=5.0,sideways_action="hold",sideways_retention_fraction=1.0,max_symbol_exposure_pct=cap,regime_confirmation_hours=hours)
      report[name]["configs"][key]={
       "net_return_pct":res["net_return_pct"],"end_equity_usdt":res["end_equity_usdt"],
       "max_drawdown_pct":res["max_drawdown_pct"],"rebalance_count":res["rebalance_count"],
       "trading_fees_usdt":res["trading_fees_usdt"],"slippage_usdt":res["slippage_usdt"],
       "liquidated":res["liquidated"]}
      print("RESULT",name,key,json.dumps(report[name]["configs"][key],separators=(",",":")),flush=True)
 out={
  "experiment":"MEAFLOW-72 raw vs true causal 3h debounce: fee/slippage stress test",
  "branch":"research/meaflow72-debounce-cost-stress-v1",
  "source":"Free official Binance Vision monthly fundingRate + 1h markPriceKlines",
  "loaded_symbols":list(data),"data_errors":errors,
  "capital_usdt":100,"leverage":1,"fee_bp_one_way":list(FEE_GRID),"slippage_bp_one_way":list(SLIP_GRID),
  "debounce_hours":list(DEBOUNCE),"risk_policies":list(CAPS),
  "strategy":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d mark-price +/-5%; bull both, bear short-only, sideways hold, unknown flat.",
  "debounce_definition":"Causal sequential state machine; new regime must persist for 3 consecutive completed BTC 1h observations.",
  "windows":report,
  "cautions":["Previously inspected historical periods; this is a cost robustness test, not pristine OOS.",
   "1h mark OHLC adverse checks are not exact Binance liquidation engine.",
   "No maker queue/partial fills; fixed slippage stress grid; static 13-symbol universe survivorship bias."]}
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/meaflow72_debounce_cost_stress.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
 print("REPORT research-results/meaflow72_debounce_cost_stress.json",flush=True)

if __name__=="__main__": main()
