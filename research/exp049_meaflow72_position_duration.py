#!/usr/bin/env python3
"""EXP-049: MEAFLOW-72 position holding duration diagnostics; isolated copy."""
import argparse,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import funding_carry_duration as sim
SYMBOLS=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","SOLUSDT","LINKUSDT","LTCUSDT","BCHUSDT","DOTUSDT","TRXUSDT","AVAXUSDT"]
POLICY={"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--start",default="2023-01");ap.add_argument("--end",default="2026-10")
 ap.add_argument("--out",default="research-results/exp049_position_duration.json")
 a=ap.parse_args();months=list(sim.months_between(a.start,a.end));root=Path("research-output/exp049-cache")
 data={};errors={}
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs={ex.submit(sim.load_symbol,s,months,root):s for s in SYMBOLS}
  for f,s in fs.items():
   try:
    _,fund,marks=f.result()
    if not fund or not marks:raise RuntimeError("empty data")
    data[s]={"fund":fund,"marks":marks};print("LOADED",s,len(fund),len(marks),flush=True)
   except Exception as e:errors[s]=str(e)
 if errors or len(data)!=len(SYMBOLS):raise RuntimeError("Incomplete universe: "+json.dumps(errors))
 events=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=10)
 period=(events[0],events[-1]);results={}
 for lev in (1.0,1.5,2.0,3.0):
  r=sim.run(data,period,lev,fee_bp=5,slip_bp=2,regime_policy=POLICY,sideways_action="hold")
  results[f"{lev:g}x"]={k:r[k] for k in ("end_equity_usdt","net_return_pct","max_drawdown_pct","liquidated","liquidation_time_utc","rebalance_count","market_regime_attribution","position_duration_diagnostics")}
  print("DURATION_RESULT",lev,json.dumps(results[f"{lev:g}x"],separators=(",",":")),flush=True)
 out={"experiment":"EXP-049","status":"completed_if_workflow_succeeds","parent_strategy_sha":"a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1",
  "strategy_rules":{"lookback_days":7,"rebalance_days":7,"regime_change_rebalance":True,"regime_policy":POLICY,"sideways_action":"hold_existing_positions"},
  "period_utc":{"start":datetime.fromtimestamp(period[0]/1000,timezone.utc).isoformat(),"end":datetime.fromtimestamp(period[1]/1000,timezone.utc).isoformat()},
  "symbols":SYMBOLS,"initial_equity_usdt":100,"costs":{"fee_bp_one_way":5,"slippage_bp_one_way":2},
  "duration_definition":"A continuous non-zero position in a symbol; partial reductions/resizes do not end it; full close or direction flip does. Positions open at period end are reported separately as right-censored.",
  "results":results,"data_errors":errors,
  "limitations":["This measures position episodes, not independent tax-lot holding periods.","No per-lot funding allocation or exact time-to-net-profit is inferred.","Liquidation remains the parent simulator's hourly OHLC approximation, not Binance's exact engine."]}
 p=Path(a.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,indent=2))
 print("REPORT",a.out,flush=True)
if __name__=="__main__":main()
