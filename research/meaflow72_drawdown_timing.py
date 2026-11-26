#!/usr/bin/env python3
"""MEAFLOW-72 copied-branch diagnostic: max drawdown timing on frozen retention strategy."""
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
    _,fund,marks=f.result();data[s]={"fund":fund,"marks":marks}
    print("LOADED",s,len(fund),len(marks),flush=True)
   except Exception as e:
    errors[s]=str(e);print("SKIP",s,str(e),flush=True)
 if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("Insufficient symbols: "+json.dumps(errors))
 data={s:data[s] for s in sorted(data)}
 events=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
 output={}
 for name,(a,b) in WINDOWS.items():
  lo,hi=ms(a),ms(b); window=[t for t in events if lo<=t<=hi]
  if len(window)<100:
   output[name]={"error":"insufficient events","event_count":len(window)};continue
  result=sim.run(data,(window[0],window[-1]),1.0,5,slip_bp=2,
   lookback_days=7,rebalance_days=7,tail_fraction=.20,
   regime_policy=POLICY,regime_threshold_pct=5.0,
   sideways_action="hold",sideways_retention_fraction=1.0)
  output[name]={
   "period_utc":[iso(window[0]),iso(window[-1])],
   "event_count":len(window),
   "headline":{k:result[k] for k in ("net_return_pct","end_equity_usdt","max_drawdown_pct","maxdd_peak_time_utc","maxdd_trough_time_utc","maxdd_peak_equity_usdt","maxdd_trough_equity_usdt","liquidated","rebalance_count","price_pnl_usdt","funding_pnl_usdt","trading_fees_usdt","slippage_usdt","hourly_adverse_checks")},
   "symbol_attribution":result["symbol_attribution"],
   "market_regime_attribution":result["market_regime_attribution"],
   "entry_regime_attribution":result["entry_regime_attribution"],
   "entry_regime_attribution_note":result["entry_regime_attribution_note"],
   "model_note":result["model_note"]
  }
  print("DIAGNOSTIC",name,json.dumps(output[name],separators=(",",":")),flush=True)
 report={
  "experiment":"MEAFLOW-72 max drawdown timing (frozen 100% sideways retention strategy; no parameter sweep)",
  "branch":"research/meaflow72-drawdown-timing-v1",
  "parent":"research/meaflow72-retention-multiwindow-v1; MEAFLOW-72 main branch unchanged",
  "source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines",
  "loaded_symbols":list(data),"data_errors":errors,"capital_usdt":100,"leverage":1,
  "costs":"5 bp fee one-way + 2 bp slippage one-way",
  "frozen_strategy":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d mark-price regime +/-5%; bull both, bear short-only; sideways hold existing positions at 100% of entry exposure, no new/additional exposure; unknown flat.",
  "windows":output,
  "interpretation_caveats":[
   "Symbol net contribution is cumulative attribution, not a standalone counterfactual; interactions and changing portfolio weights matter.",
   "Market-regime attribution assigns hourly price PnL and funding cashflow to the regime at the relevant completed hour; execution costs are assigned to execution-time regime.",
   "Entry-regime attribution assigns price and funding PnL to the regime in which incremental quantity was opened; costs are excluded from this cohort view.",
   "1h OHLC adverse stress is not tick-level liquidation simulation; static 0.5% maintenance margin and 1% liquidation-fee proxy.",
   "No maker queue/fill model; static 13-symbol universe survivorship bias; historical windows already inspected, not pristine forward OOS."
  ]
 }
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/meaflow72_drawdown_timing.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
 print("REPORT research-results/meaflow72_drawdown_timing.json",flush=True)
if __name__=="__main__":main()

# Trigger diagnostic workflow after registration.

# Trigger timing diagnostics after workflow registration; strategy policy corrected to match retention baseline.
