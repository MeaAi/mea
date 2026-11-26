#!/usr/bin/env python3
"""MEAFLOW-72 portfolio drawdown-based position scaling; isolated experiment."""
import json, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import funding_carry_liquidation_drawdown as sim

SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY={"bull":"both","bear":"short_only","sideways":"hold","unknown":"flat"}
WINDOWS={
 "2023_calendar":("2023-01-01T00:00:00+00:00","2024-01-01T00:00:00+00:00"),
 "2024_calendar":("2024-01-01T00:00:00+00:00","2025-01-01T00:00:00+00:00"),
 "2025_jan_to_sep":("2025-01-01T00:00:00+00:00","2025-09-06T18:24:00+00:00"),
 "2025_sep_to_2026_oct":("2025-09-06T18:24:00+00:00","2026-10-31T16:00:00+00:00"),
}
# Predeclared controls: thresholds are based on peak-to-current equity drawdown.
# The first matching (most severe) threshold determines the new target-size multiplier.
CONTROLS={
 "baseline":None,
 "gentle":[(-10.0,.75),(-15.0,.50),(-20.0,.25)],
 "moderate":[(-8.0,.75),(-12.0,.50),(-16.0,.25)],
}
def ms(s): return int(datetime.fromisoformat(s).timestamp()*1000)
def iso(t): return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def main():
 months=list(sim.months_between("2023-01","2026-10"))
 data={};errors={}
 with ThreadPoolExecutor(max_workers=8) as pool:
  fs={pool.submit(sim.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
  for f in as_completed(fs):
   s=fs[f]
   try:
    _,fund,marks=f.result();data[s]={"fund":fund,"marks":marks}
    print("LOADED",s,len(fund),len(marks),flush=True)
   except Exception as e:
    errors[s]=str(e);print("SKIP",s,str(e),flush=True)
 if len(data)<8 or "BTCUSDT" not in data:raise RuntimeError("Insufficient symbols "+json.dumps(errors))
 data={s:data[s] for s in sorted(data)}
 events=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
 report={}
 for name,(a,b) in WINDOWS.items():
  w=[t for t in events if ms(a)<=t<=ms(b)]
  if len(w)<100:report[name]={"error":"insufficient aligned events","event_count":len(w)};continue
  report[name]={"period_utc":[iso(w[0]),iso(w[-1])],"event_count":len(w),"configs":{}}
  for label,steps in CONTROLS.items():
   v=sim.run(data,(w[0],w[-1]),1.0,5,slip_bp=2,lookback_days=7,rebalance_days=7,
    tail_fraction=.20,regime_policy=POLICY,regime_threshold_pct=5.0,
    sideways_action="hold",sideways_retention_fraction=1.0,
    drawdown_scale_steps=steps)
   keys=("net_return_pct","end_equity_usdt","max_drawdown_pct","maxdd_peak_time_utc",
    "maxdd_trough_time_utc","rebalance_count","liquidated","price_pnl_usdt",
    "funding_pnl_usdt","trading_fees_usdt","slippage_usdt","drawdown_scale_steps")
   report[name]["configs"][label]={k:v[k] for k in keys}
   print("RESULT",name,label,json.dumps(report[name]["configs"][label],separators=(",",":")),flush=True)
 out={
  "experiment":"MEAFLOW-72 portfolio drawdown-based exposure scaling",
  "branch":"research/meaflow72-drawdown-scaling-v1",
  "source":"Official free Binance Vision monthly fundingRate + 1h markPriceKlines",
  "loaded_symbols":list(data),"data_errors":errors,"capital_usdt":100,"leverage":1,
  "costs":"5 bp fee one-way + 2 bp slippage one-way",
  "frozen_strategy":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d mark-price +/-5%; bull both, bear short-only; sideways hold; unknown flat.",
  "controls":CONTROLS,
  "method":"At each normal rebalance, new target gross exposure is multiplied by the scale selected from current equity versus the running equity peak. Existing positions are resized only at the strategy's next normal rebalance; sideways hold freezes positions, so this overlay does not force exits during sideways regimes. The same fixed controls are applied in all four periods.",
  "windows":report,
  "limitations":["These historical windows were previously inspected; this is not pristine forward OOS.",
   "The control only changes target sizing at rebalance; it is not an intrabar stop or guaranteed drawdown limit.",
   "1h OHLC adverse stress is not the exact Binance liquidation engine.",
   "No maker queue/partial-fill model; fixed slippage; static 13-symbol universe survivorship bias.",
   "A drawdown overlay can reduce exposure after losses and may also delay recovery or increase turnover."]}
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/meaflow72_drawdown_scaling.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
 print("REPORT research-results/meaflow72_drawdown_scaling.json",flush=True)
if __name__=="__main__":main()
