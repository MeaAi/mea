#!/usr/bin/env python3
"""Matched OOS test of sideways-regime position management; research-only."""
import json, math
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import funding_carry_liquidation_causal as sim

SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY={"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}

def iso(ms):
    return datetime.fromtimestamp(ms/1000, timezone.utc).isoformat()

def compact(x):
    keys=("net_return_pct","end_equity_usdt","max_drawdown_pct","liquidated",
          "rebalance_count","hourly_sideways_exits","price_pnl_usdt",
          "funding_pnl_usdt","trading_fees_usdt","slippage_usdt")
    return {k:x[k] for k in keys}

def main():
    months=list(sim.months_between("2023-01","2026-10"))
    data={}; errors={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(sim.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
        for f in as_completed(futures):
            s=futures[f]
            try:
                _,fund,marks=f.result()
                data[s]={"fund":fund,"marks":marks}
                print("LOADED",s,len(fund),len(marks),flush=True)
            except Exception as e:
                errors[s]=str(e)
                print("SKIP",s,str(e),flush=True)
    if len(data)<8 or "BTCUSDT" not in data:
        raise RuntimeError("Insufficient aligned symbols: "+json.dumps(errors))
    data={s:data[s] for s in sorted(data)}
    events=sorted(t for s in data for t in data[s]["fund"]
                  if sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
    if len(events)<100: raise RuntimeError("Insufficient aligned funding events")
    first,last=events[0],events[-1]
    start=first+int((last-first)*.70)
    end=last
    mid=(start+end)//2
    periods={"full_oos":(start,end),"oos_first_half":(start,mid),"oos_second_half":(mid,end)}
    variants={
        "sideways_flat":("flat",1),
        "sideways_hold_existing":("hold",1),
        "immediate_flat_1h":("immediate_flat",1),
        "immediate_flat_6h":("immediate_flat",6),
        "immediate_flat_24h":("immediate_flat",24),
    }
    out={}
    for period_name,period in periods.items():
        out[period_name]={}
        for label,(action,confirm) in variants.items():
            for fee in (2,5,8):
                result=sim.run(data,period,1.0,fee,slip_bp=2,
                    lookback_days=7,rebalance_days=7,tail_fraction=.20,
                    regime_policy=POLICY,regime_threshold_pct=5.0,
                    sideways_action=action,sideways_confirm_hours=confirm)
                out[period_name].setdefault(label,{})[f"fee_{fee}bp"]=compact(result)
                print("RESULT",period_name,label,fee,json.dumps(compact(result),separators=(",",":")),flush=True)
        # No regime filter reference isolates whether regime-aware sideways handling helps.
        for fee in (2,5,8):
            result=sim.run(data,period,1.0,fee,slip_bp=2,
                lookback_days=7,rebalance_days=7,tail_fraction=.20,
                sideways_action="flat")
            out[period_name].setdefault("no_regime_reference",{})[f"fee_{fee}bp"]=compact(result)
    report={
        "experiment":"Matched OOS sideways-regime transition and position-management test",
        "branch":"research/sideways-transition-management-v1",
        "source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines",
        "loaded_symbols":list(data),"data_errors":errors,
        "period_utc":{"first_available":iso(first),"last_available":iso(last),
                      "oos_start":iso(start),"oos_end":iso(end),
                      "oos_split":iso(mid)},
        "split":"Chronological first 70% excluded from OOS; final 30% fixed OOS. No parameter selection on OOS.",
        "capital_usdt":100,"leverage":1,
        "costs":"2/5/8 bp fee one-way plus 2 bp slippage one-way",
        "fixed_strategy":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d return regime threshold +/-5%; bull both, bear short-only.",
        "variants":variants,
        "periods":out,
        "limitations":["1h OHLC adverse stress is not tick-level liquidation simulation",
          "static 0.5% maintenance margin and 1% liquidation-fee proxy",
          "no maker queue/fill model","static symbol universe survivorship bias",
          "historical data windows have been inspected in prior experiments; this is not pristine unseen OOS"],
        "decision_rule":"Diagnostic only. No promotion to MEAFLOW-52 main branch."
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/sideways_transition_management.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT research-results/sideways_transition_management.json",flush=True)

if __name__=="__main__": main()
