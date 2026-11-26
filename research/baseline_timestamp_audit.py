#!/usr/bin/env python3
"""Audit the frozen MEAFLOW-52 regime timestamp for 1h candle look-ahead."""
import json, math
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import funding_carry_liquidation as legacy
import funding_carry_liquidation_causal as causal
SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
def compact(v):
    keys=("net_return_pct","end_equity_usdt","max_drawdown_pct","liquidated","rebalance_count","hourly_adverse_checks","price_pnl_usdt","funding_pnl_usdt","trading_fees_usdt","slippage_usdt")
    return {k:v.get(k) for k in keys}
def main():
    months=list(legacy.months_between("2023-01","2026-10")); data={}; errors={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(legacy.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
        for f in as_completed(fs):
            s=futures_symbol=fs[f]
            try:
                _,fund,marks=f.result(); data[s]={"fund":fund,"marks":marks}
                print("LOADED",s,"funding",len(fund),"mark_bars",len(marks),flush=True)
            except Exception as e:
                errors[s]=str(e); print("SKIP",s,str(e),flush=True)
    if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("Insufficient symbols: "+json.dumps(errors))
    times=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
    if len(times)<100: raise RuntimeError("Insufficient aligned funding events")
    first,last=times[0],times[-1]; span=last-first
    cuts={"train":(first+7*legacy.DAY,first+int(span*.5)),"validation":(first+int(span*.5),first+int(span*.7)),"oos":(first+int(span*.7),last)}
    policy={"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}
    common=dict(lev=1.0,slip_bp=2,lookback_days=7,rebalance_days=7,tail_fraction=.20,regime_policy=policy,regime_threshold_pct=5.0,sideways_action="flat")
    results={}
    for split,period in cuts.items():
        results[split]={}
        for fee in (2,5,8):
            old=legacy.run(data,period,1.0,fee,**{k:v for k,v in common.items() if k!="lev"})
            new=causal.run(data,period,1.0,fee,**common)
            results[split][f"fee_{fee}bp"]={"legacy_open_time_close_used_at_open":compact(old),"causal_last_completed_candle":compact(new),
              "delta_causal_minus_legacy":{"net_return_pp":round(new["net_return_pct"]-old["net_return_pct"],5),
                                           "max_drawdown_pp":round(new["max_drawdown_pct"]-old["max_drawdown_pct"],5)}}
            print("AUDIT",split,fee,json.dumps(results[split][f"fee_{fee}bp"],separators=(",",":")),flush=True)
    report={
      "experiment":"MEAFLOW-52 frozen baseline hourly regime timestamp audit",
      "parent_snapshot":"archive/baseline-7d-7d-20pct-2026-11-25",
      "isolated_branch":"research/baseline-timestamp-audit-v1",
      "strategy":"Frozen 7d funding rank, 7d rebalance, 20% tails; bull both, bear short-only, sideways/unknown flat",
      "legacy_semantics":"At funding event t, legacy regime_at(t) selects the 1h mark candle whose OPEN timestamp is t and reads its CLOSE; that close is not available at t.",
      "causal_semantics":"At decision timestamp t, use regime_at(t-1h), i.e. the last fully completed 1h mark candle. No look-ahead; same positions, universe, sizing, costs and data otherwise.",
      "split":"Chronological 50/20/30; OOS is a sequential audit only because the period was previously inspected in MEAFLOW-52 research.",
      "periods_utc":{k:{"start":datetime.fromtimestamp(v[0]/1000,timezone.utc).isoformat(),"end":datetime.fromtimestamp(v[1]/1000,timezone.utc).isoformat()} for k,v in cuts.items()},
      "capital_usdt":100,"leverage":1,"fees_one_way_bp":[2,5,8],"slippage_one_way_bp":2,
      "data_source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines; ZIP CRC checked",
      "data_errors":errors,"loaded_symbols":list(data),
      "drawdown":"Hourly adverse mark using simultaneous low for longs/high for shorts plus event-time equity; conservative OHLC stress, not tick-accurate.",
      "results":results,
      "decision":"Legacy baseline results require revalidation; causal run is the reference for further research. This audit does not modify MEAFLOW-52."
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/baseline_timestamp_audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT research-results/baseline_timestamp_audit.json",flush=True)
if __name__=="__main__": main()
