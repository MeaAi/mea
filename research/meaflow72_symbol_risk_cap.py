#!/usr/bin/env python3
"""MEAFLOW-72 isolated per-symbol notional-cap experiment; no main-strategy edits."""
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
CAPS={"uncapped":None,"50pct":.50,"40pct":.40,"30pct":.30,"25pct":.25,"20pct":.20,"15pct":.15}
def ms(s): return int(datetime.fromisoformat(s).timestamp()*1000)
def iso(t): return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def main():
 months=list(sim.months_between("2023-01","2026-10"))
 data={}; errors={}
 with ThreadPoolExecutor(max_workers=8) as pool:
  fs={pool.submit(sim.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
  for f in as_completed(fs):
   s=fs[f]
   try:
    _,fund,marks=f.result(); data[s]={"fund":fund,"marks":marks}
    print("LOADED",s,len(fund),len(marks),flush=True)
   except Exception as e:
    errors[s]=str(e); print("SKIP",s,str(e),flush=True)
 if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("Insufficient symbols: "+json.dumps(errors))
 data={s:data[s] for s in sorted(data)}
 events=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
 report={}
 for name,(a,b) in WINDOWS.items():
  lo,hi=ms(a),ms(b); w=[t for t in events if lo<=t<=hi]
  if len(w)<100:
   report[name]={"error":"insufficient aligned events","event_count":len(w)}; continue
  period=(w[0],w[-1]); report[name]={"period_utc":[iso(w[0]),iso(w[-1])],"event_count":len(w),"caps":{}}
  for label,cap in CAPS.items():
   v=sim.run(data,period,1.0,5,slip_bp=2,lookback_days=7,rebalance_days=7,
    tail_fraction=.20,regime_policy=POLICY,regime_threshold_pct=5.0,
    sideways_action="hold",sideways_retention_fraction=1.0,
    max_symbol_exposure_pct=cap)
   report[name]["caps"][label]={k:v[k] for k in (
    "net_return_pct","end_equity_usdt","max_drawdown_pct","maxdd_peak_time_utc",
    "maxdd_trough_time_utc","rebalance_count","liquidated","price_pnl_usdt",
    "funding_pnl_usdt","trading_fees_usdt","slippage_usdt","max_symbol_exposure_pct")}
   print("RESULT",name,label,json.dumps(report[name]["caps"][label],separators=(",",":")),flush=True)
 out={
  "experiment":"MEAFLOW-72 per-symbol notional cap; isolated copy; no parameter tuning or main-branch changes",
  "branch":"research/meaflow72-symbol-risk-cap-v1",
  "parent":"research/meaflow72-dd-interval-attribution-v1; MEAFLOW-72 main branch unchanged",
  "source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines",
  "loaded_symbols":list(data),"data_errors":errors,"capital_usdt":100,"leverage":1,
  "costs":"5 bp fee one-way + 2 bp slippage one-way",
  "frozen_strategy":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d mark-price regime +/-5%; bull both, bear short-only; sideways hold existing positions at 100% of entry exposure, no new/additional exposure; unknown flat.",
  "cap_definition":"At each rebalance, newly formed target notional per symbol is clipped to cap_fraction * current equity. Uncapped baseline has no per-symbol limit. Frozen sideways holdings are not resized by the cap, preserving the MEAFLOW-72 sideways-hold rule. No leverage change; unused notional remains cash.",
  "windows":report,
  "limitations":[
   "These historical windows were previously inspected and are not pristine forward OOS.",
   "1h OHLC adverse stress is not tick-level liquidation simulation; static 0.5% MMR and 1% liquidation-fee proxy.",
   "No maker queue/fill model, fixed slippage only, static 13-symbol universe survivorship bias.",
   "Per-symbol cap changes gross exposure and therefore return opportunity; compare return and drawdown jointly, not drawdown alone."
  ]
 }
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/meaflow72_symbol_risk_cap.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
 print("REPORT research-results/meaflow72_symbol_risk_cap.json",flush=True)
if __name__=="__main__": main()
