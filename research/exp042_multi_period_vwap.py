#!/usr/bin/env python3
"""EXP-042: matched VWAP candidate tests across distinct historical calendar periods."""
import json, math
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import funding_carry_liquidation_causal as base
import exp039_binance_vwap as exp039

SYMBOLS=exp039.SYMBOLS
POLICY=exp039.POLICY
FEE_BP=5
SLIP_BP=2
WINDOWS=(135,155,175)

def ms(s):
    return int(datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)

def iso(t):
    return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()

def compact(v):
    keys=("start_equity_usdt","end_equity_usdt","net_return_pct","max_drawdown_pct",
          "liquidated","rebalance_count","hourly_adverse_checks","price_pnl_usdt",
          "funding_pnl_usdt","trading_fees_usdt","slippage_usdt","market_regime_attribution")
    return {k:v[k] for k in keys}

def compare(b,c):
    return {
      "return_delta_pp":round(c["net_return_pct"]-b["net_return_pct"],4),
      "drawdown_improvement_pp":round(c["max_drawdown_pct"]-b["max_drawdown_pct"],4),
      "return_pass":c["net_return_pct"]>b["net_return_pct"],
      "drawdown_pass":c["max_drawdown_pct"]>b["max_drawdown_pct"],
      "no_liquidation":not c["liquidated"],
      "joint_pass":c["net_return_pct"]>b["net_return_pct"] and c["max_drawdown_pct"]>b["max_drawdown_pct"] and not c["liquidated"]
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
                _,fund,marks=f.result()
                data[s]={"fund":fund,"marks":marks}
                print("LOADED",s,len(fund),len(marks),flush=True)
            except Exception as e:
                errors[s]=str(e); print("SKIP",s,str(e),flush=True)
    if len(data)<8 or "BTCUSDT" not in data:
        raise RuntimeError("Insufficient symbols: "+json.dumps(errors))
    data={s:data[s] for s in sorted(data)}
    events=sorted(t for s in data for t in data[s]["fund"]
                  if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
    vwap_raw=exp039.load_btc_vwap(months,root)
    vwap=exp039.make_vwap_series(vwap_raw)
    sim=exp039.make_sim(vwap)

    # Calendar windows are fixed before looking at outcomes. All have >=155d VWAP warmup.
    requested={
      "2023H2_to_2024H1":("2023-07-01","2024-07-01"),
      "2024H2_to_2025H1":("2024-07-01","2025-07-01"),
      "2025H2_to_2026Oct":("2025-07-01","2026-11-01")
    }
    # Retain the previously used final-30%-of-overlap OOS as a direct reference.
    first=max(events[0],vwap["times"][0]+155*exp039.DAY)
    last=events[-1]
    oos_start=first+int((last-first)*.70)
    requested["latest_30pct_oos"]=(datetime.fromtimestamp(oos_start/1000,timezone.utc).strftime("%Y-%m-%d"),
                                    datetime.fromtimestamp(last/1000,timezone.utc).strftime("%Y-%m-%d"))
    periods={}
    for name,(a,b) in requested.items():
        p=(ms(a),ms(b))
        eligible=[t for t in events if p[0]<=t<=p[1]]
        if len(eligible)<100:
            raise RuntimeError(f"Insufficient funding events for {name}: {len(eligible)}")
        if p[0]<vwap["times"][0]+155*exp039.DAY:
            raise RuntimeError(f"Insufficient 155d VWAP warmup for {name}")
        periods[name]=(p[0],p[1])
    results={}
    for name,period in periods.items():
        out={}
        baseline=sim(data,period,1.0,FEE_BP,slip_bp=SLIP_BP,lookback_days=7,
                     rebalance_days=7,tail_fraction=.20,regime_policy=POLICY,
                     regime_threshold_pct=5.0,sideways_action="hold",
                     vwap_series=vwap,vwap_days=155,vwap_mode="baseline")
        baseline=compact(baseline)
        out["baseline"]=baseline
        out["windows"]={}
        for days in WINDOWS:
            candidate=sim(data,period,1.0,FEE_BP,slip_bp=SLIP_BP,lookback_days=7,
                          rebalance_days=7,tail_fraction=.20,regime_policy=POLICY,
                          regime_threshold_pct=5.0,sideways_action="hold",
                          vwap_series=vwap,vwap_days=days,vwap_mode="short_only_below")
            candidate=compact(candidate)
            out["windows"][f"{days}d"]={"candidate":candidate,"comparison":compare(baseline,candidate)}
            print("PERIOD",name,"WINDOW",days,json.dumps(out["windows"][f"{days}d"]["comparison"]),flush=True)
        actual=[t for t in events if period[0]<=t<=period[1]]
        out["period_utc"]={"requested_start":iso(period[0]),"requested_end":iso(period[1]),
                           "first_funding_event":iso(actual[0]),"last_funding_event":iso(actual[-1]),
                           "aligned_event_count":len(actual)}
        results[name]=out

    report={
      "experiment":"EXP-042 multi-period VWAP validation against frozen MEAFLOW-72",
      "branch":"research/exp042-multi-period-vwap",
      "reference_base_sha":"a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1",
      "candidate_reference":"EXP-039 BTC USD-M 1h close*quote-volume rolling VWAP; short-only overlay when BTC close is below VWAP",
      "data_source":"Binance Vision USD-M monthly 1h markPriceKlines and fundingRate for 13 symbols; BTCUSDT 1h kline close and quote volume",
      "loaded_symbols":list(data),"data_errors":errors,
      "vwap_rows":len(vwap["times"]),"vwap_first_bar":iso(vwap["times"][0]),"vwap_last_bar":iso(vwap["times"][-1]),
      "capital_usdt":100,"leverage":1,"fee_bp_one_way":FEE_BP,"slippage_bp_one_way":SLIP_BP,
      "strategy_parameters":"Frozen MEAFLOW-72: 7d funding lookback, 7d rebalance, 20% tails, BTC 30d regime +/-5%, bull both/bear short-only/sideways hold",
      "periods":results,
      "decision_rule":"For every period, a VWAP window passes only if final capital/net return is higher AND hourly adverse-mark maximum drawdown is less negative than matched baseline, with no liquidation. No promotion based on pooled return alone.",
      "limitations":[
        "Calendar periods are fixed historical samples, not statistically independent market cycles.",
        "VWAP is a traded-volume price proxy, not holder cost basis or on-chain realized price.",
        "USD-M quote-volume VWAP is used as an overlay on a mark-price funding simulator.",
        "Static 13-symbol universe has survivorship bias.",
        "Hourly adverse drawdown and liquidation are conservative portfolio OHLC approximations, not Binance's exact liquidation engine."
      ]
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp042_multi_period_vwap.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT_READY research-results/exp042_multi_period_vwap.json",flush=True)

if __name__=="__main__": main()
