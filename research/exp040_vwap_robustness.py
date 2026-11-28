#!/usr/bin/env python3
"""EXP-040: robustness validation of EXP-039 VWAP candidate vs frozen MEAFLOW-72."""
import json, math
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import funding_carry_liquidation_causal as base
import exp039_binance_vwap as exp039

SYMBOLS = exp039.SYMBOLS
POLICY = exp039.POLICY

def iso(ms):
    return datetime.fromtimestamp(ms/1000, timezone.utc).isoformat()

def metrics(v):
    return {k:v[k] for k in (
        "start_equity_usdt","end_equity_usdt","net_return_pct","max_drawdown_pct",
        "liquidated","rebalance_count","hourly_adverse_checks","trading_fees_usdt",
        "slippage_usdt","price_pnl_usdt","funding_pnl_usdt","market_regime_attribution"
    )}

def compare(base_result, candidate):
    return {
        "return_delta_pp": round(candidate["net_return_pct"]-base_result["net_return_pct"],4),
        "drawdown_improvement_pp": round(candidate["max_drawdown_pct"]-base_result["max_drawdown_pct"],4),
        "return_pass": candidate["net_return_pct"] > base_result["net_return_pct"],
        "drawdown_pass": candidate["max_drawdown_pct"] > base_result["max_drawdown_pct"],
        "no_liquidation": not candidate["liquidated"],
        "joint_pass": (
            candidate["net_return_pct"] > base_result["net_return_pct"]
            and candidate["max_drawdown_pct"] > base_result["max_drawdown_pct"]
            and not candidate["liquidated"]
        )
    }

def main():
    months=list(base.months_between("2023-01","2026-10"))
    root=Path("research-output"); root.mkdir(exist_ok=True)
    data={}; errors={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs={pool.submit(base.load_symbol,s,months,root):s for s in SYMBOLS}
        for f in as_completed(futs):
            s=futs[f]
            try:
                _,fund,marks=f.result(); data[s]={"fund":fund,"marks":marks}
                print("LOADED",s,len(fund),len(marks),flush=True)
            except Exception as e:
                errors[s]=str(e); print("SKIP",s,str(e),flush=True)
    if len(data)<8 or "BTCUSDT" not in data:
        raise RuntimeError("Insufficient symbols: "+json.dumps(errors))
    data={s:data[s] for s in sorted(data)}
    events=sorted(t for s in data for t in data[s]["fund"]
                  if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
    first,last=events[0],events[-1]
    vwap_raw=exp039.load_btc_vwap(months,root)
    vwap=exp039.make_vwap_series(vwap_raw)
    warm_start=vwap["times"][0]+155*exp039.DAY
    first=max(first,warm_start)
    oos_start=first+int((last-first)*.70)
    end=last
    cuts=[oos_start+(end-oos_start)*i//3 for i in range(4)]
    periods={
        "full_oos":(oos_start,end),
        "time_block_1":(cuts[0],cuts[1]),
        "time_block_2":(cuts[1],cuts[2]),
        "time_block_3":(cuts[2],cuts[3])
    }
    run=exp039.make_sim(vwap)

    def execute(period, fee, slip, days, mode):
        r=run(data,period,1.0,fee,slip_bp=slip,lookback_days=7,
              rebalance_days=7,tail_fraction=.20,regime_policy=POLICY,
              regime_threshold_pct=5.0,sideways_action="hold",
              vwap_series=vwap,vwap_days=days,vwap_mode=mode)
        return metrics(r)

    results={}
    # Matched baseline/candidate comparisons over three independent time blocks.
    for pname in ("full_oos","time_block_1","time_block_2","time_block_3"):
        period=periods[pname]
        b=execute(period,5,2,155,"baseline")
        c=execute(period,5,2,155,"short_only_below")
        results[pname]={
            "period_utc":{"start":iso(period[0]),"end":iso(period[1])},
            "baseline":b,"candidate_155d":c,
            "comparison":compare(b,c)
        }
        print("TIME_BLOCK",pname,json.dumps(results[pname]["comparison"]),flush=True)

    # Transaction-cost stress: same OOS dates and same 155d candidate signal.
    cost_stress={}
    for fee,slip in ((5,2),(10,4),(15,6)):
        b=execute(periods["full_oos"],fee,slip,155,"baseline")
        c=execute(periods["full_oos"],fee,slip,155,"short_only_below")
        cost_stress[f"fee_{fee}bp_slippage_{slip}bp"]={
            "baseline":b,"candidate_155d":c,
            "comparison":compare(b,c)
        }
        print("COST",fee,slip,json.dumps(cost_stress[f"fee_{fee}bp_slippage_{slip}bp"]["comparison"]),flush=True)

    # Parameter sensitivity: retain same rule, perturb only VWAP rolling window.
    window_sensitivity={}
    b=results["full_oos"]["baseline"]
    for days in (135,155,175):
        c=execute(periods["full_oos"],5,2,days,"short_only_below")
        window_sensitivity[f"{days}d"]={
            "candidate":c,"comparison":compare(b,c)
        }
        print("WINDOW",days,json.dumps(window_sensitivity[f"{days}d"]["comparison"]),flush=True)

    report={
        "experiment":"EXP-040 VWAP candidate robustness vs frozen MEAFLOW-72",
        "branch":"research/exp040-vwap-robustness",
        "reference_base_sha":"a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1",
        "candidate_source_branch":"research/exp039-binance-vwap",
        "candidate_rule":"When BTC close is below trailing BTC USD-M 1h close*quote-volume VWAP, allow short positions only; otherwise preserve frozen MEAFLOW-72 regime policy.",
        "baseline":"Frozen MEAFLOW-72, unmodified simulator from reference base; 100 USDT, 1x, 7d funding lookback, 7d rebalance, 20% tails, BTC 30d regime +/-5%, bull both/bear short-only/sideways hold-flat policy.",
        "data_source":"Official Binance Vision USD-M monthly 1h markPriceKlines and fundingRate for 13-symbol portfolio; BTCUSDT 1h klines close and quote volume for VWAP.",
        "loaded_symbols":list(data),"data_errors":errors,
        "oos_utc":{"start":iso(oos_start),"end":iso(end)},
        "time_blocks":results,
        "cost_stress":cost_stress,
        "window_sensitivity":window_sensitivity,
        "assumptions":{"capital_usdt":100,"leverage":1,"base_costs":"5bp one-way fee + 2bp one-way slippage","stress_costs":["10bp + 4bp","15bp + 6bp"],"windows_days":[135,155,175]},
        "decision_rule":"Pass only if candidate net return is greater AND hourly adverse-mark max drawdown is less negative than matched baseline, with no liquidation. Robust promotion requires full OOS, each time block, all tested cost levels, and parameter-neighbourhood evidence.",
        "limitations":[
            "VWAP is a traded-volume price proxy, not holder cost basis or on-chain realized price.",
            "USD-M quote volume and mark-price portfolio accounting are different series.",
            "13-symbol static universe has survivorship bias.",
            "Hourly adverse drawdown and liquidation are conservative portfolio OHLC approximations, not Binance's exact liquidation engine.",
            "Time blocks are contiguous portions of the same historical sample, not independent market cycles."
        ]
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp040_vwap_robustness.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT_READY research-results/exp040_vwap_robustness.json",flush=True)

if __name__=="__main__": main()
