#!/usr/bin/env python3
"""EXP-048: MEAFLOW-72 isolated leverage sweep with regime attribution.
Parent is the immutable MEAFLOW-72 SHA. Public Binance Vision data only.
"""
import json, argparse, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import funding_carry_liquidation as sim

SYMBOLS=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","SOLUSDT","LINKUSDT","LTCUSDT","BCHUSDT","DOTUSDT","TRXUSDT","AVAXUSDT"]
LEVERAGES=[1.0,1.5,2.0,3.0]
POLICY={"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",default="2023-01")
    ap.add_argument("--end",default="2026-10")
    ap.add_argument("--out",default="research-output/exp048_leverage_regimes.json")
    a=ap.parse_args()
    months=list(sim.months_between(a.start,a.end))
    root=Path("research-output/exp048-cache")
    data={}; errors={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(sim.load_symbol,s,months,root):s for s in SYMBOLS}
        for f,s in fs.items():
            try:
                _,fund,marks=f.result()
                if not fund or not marks: raise RuntimeError("empty funding or mark-price data")
                data[s]={"fund":fund,"marks":marks}
                print("LOADED",s,"funding",len(fund),"mark_bars",len(marks),flush=True)
            except Exception as e:
                errors[s]=str(e); print("LOAD_ERROR",s,str(e),flush=True)
    if errors or len(data)!=len(SYMBOLS):
        raise RuntimeError("Refusing incomplete universe: "+json.dumps(errors))
    events=sorted(t for s in data for t in data[s]["fund"]
                  if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=10)
    if len(events)<100: raise RuntimeError("Insufficient aligned funding events")
    period=(events[0],events[-1])
    results={}
    for lev in LEVERAGES:
        r=sim.run(data,period,lev,fee_bp=5,slip_bp=2,regime_policy=POLICY,sideways_action="hold")
        results[f"{lev:g}x"]=r
        print("RESULT",lev,json.dumps(r,separators=(",",":")),flush=True)
    # Per-regime isolated diagnostics are not used for promotion: the strategy's
    # sideways rule carries pre-existing positions, so regime PnL attribution
    # from the continuous portfolio is the faithful sideways measure.
    out={
      "experiment":"EXP-048",
      "status":"completed_portfolio_leverage_sweep",
      "parent_strategy_sha":"a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1",
      "strategy_rules":{"funding_lookback_days":7,"rebalance_days":7,"regime_change_rebalance":True,
        "regime_policy":POLICY,"sideways_action":"hold_existing_positions","unknown":"flat"},
      "period_utc":{"first":datetime.fromtimestamp(period[0]/1000,timezone.utc).isoformat(),
                    "last":datetime.fromtimestamp(period[1]/1000,timezone.utc).isoformat()},
      "symbols":SYMBOLS,"initial_equity_usdt":100,
      "costs":{"fee_bp_one_way":5,"slippage_bp_one_way":2},
      "regime_method":"Run the unchanged MEAFLOW-72 policy continuously; report bull/bear/sideways incremental PnL and costs by regime. Do not reset to flat at regime boundaries because sideways holds inherited positions.",
      "leverage_results":results,
      "data_errors":errors,
      "limitations":["Public hourly mark OHLC stress approximation, not Binance exact liquidation engine",
        "Static 0.5% maintenance-margin and 1% liquidation-fee assumptions in parent simulator",
        "Hourly adverse drawdown uses simultaneous adverse extremes; conservative stress estimate",
        "Fixed 13-symbol universe survivorship bias",
        "Historical period has already been examined; this is a risk-sizing comparison, not pristine OOS validation"]
    }
    p=Path(a.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,indent=2))
    print("SUMMARY",json.dumps({k:{q:v.get(q) for q in ("end_equity_usdt","net_return_pct","max_drawdown_pct","liquidated","liquidation_time_utc","rebalance_count","hourly_adverse_checks","market_regime_attribution")} for k,v in results.items()},indent=2),flush=True)
if __name__=="__main__": main()
