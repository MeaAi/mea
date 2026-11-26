#!/usr/bin/env python3
"""MEAFLOW-52 bear-to-sideways hourly short-exit confirmation experiment."""
import json, math
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import funding_carry_exit_confirmation as base
SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
def compact(v):
    keys=("net_return_pct","end_equity_usdt","max_drawdown_pct","liquidated","rebalance_count","hourly_adverse_checks","hourly_sideways_exits","price_pnl_usdt","funding_pnl_usdt","trading_fees_usdt","slippage_usdt")
    return {k:v.get(k) for k in keys}
def main():
    months=list(base.months_between("2023-01","2026-10")); data={}; errors={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(base.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
        for f in as_completed(fs):
            s=fs[f]
            try:
                _,fund,marks=f.result(); data[s]={"fund":fund,"marks":marks}
                print("LOADED",s,"funding",len(fund),"mark_bars",len(marks),flush=True)
            except Exception as e:
                errors[s]=str(e); print("SKIP",s,str(e),flush=True)
    if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("Insufficient symbols: "+json.dumps(errors))
    times=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
    if len(times)<100: raise RuntimeError("Insufficient aligned funding events")
    first,last=times[0],times[-1]; span=last-first
    cuts={"train":(first+7*base.DAY,first+int(span*.5)),"validation":(first+int(span*.5),first+int(span*.7)),"oos":(first+int(span*.7),last)}
    policy={"bull":"both","bear":"short_only","sideways":"flat","unknown":"flat"}
    common=dict(slip_bp=2,lookback_days=7,rebalance_days=7,tail_fraction=.20,regime_policy=policy,regime_threshold_pct=5.0)
    validation={}
    for fee in (2,5,8):
        control=base.run(data,cuts["validation"],1.0,fee,**common,sideways_action="flat")
        validation[f"fee_{fee}bp"]={"control_flat":compact(control),"confirmations":{}}
        for n in (1,2,3):
            candidate=base.run(data,cuts["validation"],1.0,fee,**common,sideways_action="immediate_flat",sideways_confirm_hours=n)
            validation[f"fee_{fee}bp"]["confirmations"][str(n)]=compact(candidate)
            print("VALIDATION",fee,n,json.dumps(compact(candidate),separators=(",",":")),flush=True)
    control5=validation["fee_5bp"]["control_flat"]; eligible=[]
    for n in (1,2,3):
        v=validation["fee_5bp"]["confirmations"][str(n)]
        if not v["liquidated"] and v["net_return_pct"]>control5["net_return_pct"] and v["max_drawdown_pct"]>control5["max_drawdown_pct"]:
            eligible.append((n,v))
    chosen=max(eligible,key=lambda x:x[1]["net_return_pct"])[0] if eligible else None
    oos={}
    if chosen is not None:
        for fee in (2,5,8):
            control=base.run(data,cuts["oos"],1.0,fee,**common,sideways_action="flat")
            candidate=base.run(data,cuts["oos"],1.0,fee,**common,sideways_action="immediate_flat",sideways_confirm_hours=chosen)
            oos[f"fee_{fee}bp"]={"control_flat":compact(control),f"chosen_confirmation_{chosen}h":compact(candidate)}
            print("OOS",fee,chosen,json.dumps(oos[f"fee_{fee}bp"],separators=(",",":")),flush=True)
    report={
      "experiment":"MEAFLOW-52 bear-to-sideways hourly short-exit confirmation",
      "parent_snapshot":"archive/baseline-7d-7d-20pct-2026-11-25",
      "isolated_branch":"research/bear-sideways-exit-confirm-v1",
      "strategy":"Frozen 7d funding rank, 7d rebalance, 20% tails; bull both, bear short-only, sideways/unknown flat; causal BTC 30d mark return thresholds +/-5%",
      "change":"During an open position, count consecutive completed hourly BTC regime marks classified sideways; flatten at close of hour 1, 2, or 3. Counter resets if regime leaves sideways.",
      "selection_rule":"Choose only candidates that improve BOTH validation net return and hourly adverse-mark max drawdown versus the same-parameter flat control at 5bp fee + 2bp slippage. If none qualify, no OOS candidate is promoted.",
      "split":"Chronological 50/20/30. Validation chooses candidate; final 30% is sequential robustness only because this date range was previously inspected for MEAFLOW-52.",
      "periods_utc":{k:{"start":datetime.fromtimestamp(v[0]/1000,timezone.utc).isoformat(),"end":datetime.fromtimestamp(v[1]/1000,timezone.utc).isoformat()} for k,v in cuts.items()},
      "capital_usdt":100,"leverage":1,"fees_one_way_bp":[2,5,8],"slippage_one_way_bp":2,
      "data_source":"Official free Binance Vision monthly fundingRate and 1h markPriceKlines; ZIP CRC checked by loader",
      "data_errors":errors,"loaded_symbols":list(data),
      "drawdown":"Hourly adverse mark: simultaneous low for longs/high for shorts, plus event-time equity; conservative OHLC stress, not tick-accurate",
      "limitations":["1h OHLC cannot identify intrahour event order","BTC regime is a market-state proxy","static universe survivorship bias","not Binance's exact liquidation engine"],
      "validation":validation,"selected_confirmation_hours":chosen,"oos_sequential_robustness":oos,
      "decision":"No candidate passed both validation gates" if chosen is None else "Candidate selected on validation only; OOS is sequential robustness, not pristine unseen OOS"
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/bear_sideways_exit_confirmation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT research-results/bear_sideways_exit_confirmation.json",flush=True)
if __name__=="__main__": main()

# Triggered after isolated simulator syntax correction; no strategy logic change.
