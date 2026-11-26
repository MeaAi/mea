#!/usr/bin/env python3
"""MEAFLOW-72 causal inverse-volatility sizing experiment; isolated research only."""
import json, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import funding_carry_liquidation_volatility as sim

SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY={"bull":"both","bear":"short_only","sideways":"hold","unknown":"flat"}
WINDOWS={
 "2023_calendar":("2023-01-01T00:00:00+00:00","2024-01-01T00:00:00+00:00"),
 "2024_calendar":("2024-01-01T00:00:00+00:00","2025-01-01T00:00:00+00:00"),
 "2025_jan_to_sep_data_cut":("2025-01-01T00:00:00+00:00","2025-09-06T18:24:00+00:00"),
 "2025_sep_to_2026_oct_data_cut":("2025-09-06T18:24:00+00:00","2026-10-31T16:00:00+00:00"),
}
CONFIGS={"baseline_equal_weight":0,"inverse_vol_7d":168,"inverse_vol_30d":720}
def ms(s): return int(datetime.fromisoformat(s).timestamp()*1000)
def iso(t): return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def main():
 months=list(sim.months_between("2023-01","2026-10"))
 data={};errors={}
 with ThreadPoolExecutor(max_workers=8) as pool:
  fs={pool.submit(sim.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
  for f in as_completed(fs):
   s=future_symbol=fs[f]
   try:
    _,fund,marks=f.result();data[s]={"fund":fund,"marks":marks}
    print("LOADED",s,len(fund),len(marks),flush=True)
   except Exception as e:
    errors[s]=str(e);print("SKIP",s,str(e),flush=True)
 if len(data)<8 or "BTCUSDT" not in data:raise RuntimeError("Insufficient aligned symbols: "+json.dumps(errors))
 data={s:data[s] for s in sorted(data)}
 events=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
 report={}
 for name,(a,b) in WINDOWS.items():
  w=[t for t in events if ms(a)<=t<=ms(b)]
  if len(w)<100:
   report[name]={"error":"insufficient aligned events","event_count":len(w)};continue
  report[name]={"period_utc":[iso(w[0]),iso(w[-1])],"event_count":len(w),"configs":{}}
  for label,lookback in CONFIGS.items():
   for fee in (2,5,8):
    v=sim.run(data,(w[0],w[-1]),1.0,fee,slip_bp=2,lookback_days=7,rebalance_days=7,
      tail_fraction=.20,regime_policy=POLICY,regime_threshold_pct=5.0,
      sideways_action="hold",sideways_retention_fraction=1.0,
      volatility_lookback_hours=lookback)
    keys=("net_return_pct","end_equity_usdt","max_drawdown_pct","maxdd_peak_time_utc",
      "maxdd_trough_time_utc","rebalance_count","liquidated","price_pnl_usdt",
      "funding_pnl_usdt","trading_fees_usdt","slippage_usdt","symbol_attribution")
    row={k:v[k] for k in keys}
    row["btc_eth_sol_net_usdt"]={s:v["symbol_attribution"].get(s,{}).get("net_contribution_usdt") for s in ("BTCUSDT","ETHUSDT","SOLUSDT")}
    report[name]["configs"][f"{label}_fee_{fee}bp"]=row
    print("RESULT",name,label,"fee",fee,json.dumps({k:row[k] for k in ("net_return_pct","max_drawdown_pct","end_equity_usdt","liquidated","btc_eth_sol_net_usdt")},separators=(",",":")),flush=True)
 out={
  "experiment":"MEAFLOW-72 causal inverse-volatility portfolio sizing",
  "branch":"research/meaflow72-volatility-sizing-v1",
  "source":"Official free Binance Vision monthly fundingRate + 1h markPriceKlines",
  "loaded_symbols":list(data),"data_errors":errors,"capital_usdt":100,"leverage":1,
  "costs":"2/5/8 bp fee one-way sensitivity + 2 bp slippage one-way",
  "frozen_strategy":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d mark-price +/-5%; bull both, bear short-only; sideways hold; unknown flat.",
  "method":"At each normal rebalance, calculate standard deviation of hourly log close-to-close mark-price returns using only candles strictly earlier than the rebalance timestamp. Apply inverse-volatility weights to the selected long and short baskets separately; cap raw relative weights at 0.5x-2.0x their side mean and renormalize to mean 1.0 so each side's gross notional is preserved. 168h and 720h lookbacks are fixed ex ante. Existing positions are unchanged between normal rebalances; sideways hold remains unchanged.",
  "windows":report,
  "limitations":["Historical windows have been inspected in prior research; not pristine forward OOS.",
   "1h mark OHLC stress is not the exact Binance liquidation engine.",
   "No maker queue/partial fills; fixed slippage; static 13-symbol universe survivorship bias.",
   "Inverse-volatility weights are not a portfolio volatility target and do not guarantee a drawdown cap.",
   "Insufficient history falls back to equal weight for that symbol at that rebalance."]
 }
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/meaflow72_volatility_sizing.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
 print("REPORT research-results/meaflow72_volatility_sizing.json",flush=True)
if __name__=="__main__":main()
