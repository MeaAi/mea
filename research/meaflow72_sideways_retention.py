#!/usr/bin/env python3
"""MEAFLOW-72 copy experiment: retain 100/75/50/25/0 percent of exposure in sideways regimes."""
import json, math
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import funding_carry_liquidation_fixed as sim

SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY={"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}
FRACTIONS=(1.00,0.75,0.50,0.25,0.00)

def iso(ms):
    return datetime.fromtimestamp(ms/1000, timezone.utc).isoformat()

def compact(x):
    keys=("net_return_pct","end_equity_usdt","max_drawdown_pct","liquidated",
          "rebalance_count","price_pnl_usdt","funding_pnl_usdt",
          "trading_fees_usdt","slippage_usdt")
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
    periods={"full_window":(start,end),"first_half":(start,mid),"second_half":(mid,end)}
    out={}
    for period_name,period in periods.items():
        out[period_name]={}
        for fraction in FRACTIONS:
            label=f"retain_{int(fraction*100)}pct"
            fees=(2,5,8) if period_name=="full_window" else (5,)
            out[period_name][label]={}
            for fee in fees:
                result=sim.run(data,period,1.0,fee,slip_bp=2,
                    lookback_days=7,rebalance_days=7,tail_fraction=.20,
                    regime_policy=POLICY,regime_threshold_pct=5.0,
                    sideways_action="flat",sideways_retention_fraction=fraction)
                out[period_name][label][f"fee_{fee}bp"]=compact(result)
                print("RESULT",period_name,label,fee,json.dumps(compact(result),separators=(",",":")),flush=True)
    report={
        "experiment":"MEAFLOW-72 copied-branch sideways position retention sweep",
        "branch":"research/meaflow72-sideways-retention-fixed-v1",
        "parent":"MEAFLOW-72 (unchanged)",
        "source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines",
        "loaded_symbols":list(data),"data_errors":errors,
        "period_utc":{"first_available":iso(first),"last_available":iso(last),
                      "window_start":iso(start),"window_end":iso(end),"split":iso(mid)},
        "window_rule":"Same fixed final 30% window as prior sideways-management experiment; already inspected historically, not pristine unseen OOS.",
        "capital_usdt":100,"leverage":1,
        "strategy_frozen":"7d funding lookback, 7d rebalance, 20% tails; BTC trailing 30d mark-price regime threshold +/-5%; bull both, bear short-only, sideways retains stated fraction of existing quantity and opens/adds nothing, unknown flat.",
        "costs":"2/5/8 bp fee one-way plus 2 bp slippage one-way; split periods use 5 bp fee + 2 bp slippage.",
        "retention_semantics":"At first rebalance after entering sideways, capture pre-sideways quantity as anchor; target is a fixed fraction of that entry exposure at every sideways rebalance. Reduction is not compounded. No new/additional exposure is opened while sideways.",
        "variants":list(FRACTIONS),"periods":out,
        "limitations":["1h OHLC adverse stress is not tick-level liquidation simulation",
          "static 0.5% maintenance margin and 1% liquidation-fee proxy",
          "no maker queue/fill model","static symbol universe survivorship bias",
          "historical data window inspected in prior experiments; not pristine forward OOS"]
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/meaflow72_sideways_retention.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT research-results/meaflow72_sideways_retention.json",flush=True)

if __name__=="__main__": main()
