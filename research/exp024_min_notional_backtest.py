#!/usr/bin/env python3
"""EXP-024 full OOS MEAFLOW-72 backtest with Binance minimum-notional filters.

Three execution variants are compared with the frozen baseline:
1) Confirmed BTC/ETH historical min-notional rules only.
2) Same rules plus the general 5 USDT USD-M baseline for other symbols.
3) Same as (2), but no reduce-only minimum-notional exemption.

Historical BTC: 100 USDT before 2026-04-14 06:30 UTC, 50 USDT after.
Historical ETH: 20 USDT since 2023-11-02 (covers the entire OOS period).
Other-symbol 5 USDT is a sensitivity assumption, not a verified historical
per-symbol archive. Quantity step-size rounding is not included because the
public exchangeInfo endpoint returned HTTP 451 from the hosted runner.
"""
import json, math
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import funding_carry_liquidation_causal as sim

SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")
POLICY = {"bull": "both", "bear": "short_only", "sideways": "flat", "unknown": "flat"}
OOS_START = "2025-09-06T18:24:00+00:00"
OOS_END = "2026-10-31T16:00:00+00:00"
BTC_CUTOVER_MS = int(datetime.fromisoformat("2026-04-14T06:30:00+00:00").timestamp()*1000)

def ms(iso):
    return int(datetime.fromisoformat(iso).timestamp()*1000)

def compact(result):
    return {k:result[k] for k in (
        "start_equity_usdt","end_equity_usdt","net_return_pct","max_drawdown_pct",
        "liquidated","trading_fees_usdt","slippage_usdt","rebalance_count",
        "attempted_order_count","rejected_order_count","rejected_order_notional_usdt",
        "rejected_orders_by_symbol"
    )} | {
        "executed_order_count":sum(len(e["orders"]) for e in result["rebalance_log"]),
        "rejected_order_details":[
            {"time_utc":e["time_utc"],"regime":e["regime"],**o}
            for e in result["rebalance_log"] for o in e.get("rejected_orders",[])
        ]
    }

def main():
    months=list(sim.months_between("2023-01","2026-10"))
    data,errors={},{}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(sim.load_symbol,s,months,Path("research-output")):s for s in SYMBOLS}
        for f in as_completed(futures):
            symbol=futures[f]
            try:
                _,funding,marks=f.result()
                data[symbol]={"fund":funding,"marks":marks}
                print("LOADED",symbol,len(funding),len(marks),flush=True)
            except Exception as exc:
                errors[symbol]=str(exc)
                print("SKIP",symbol,str(exc),flush=True)
    if len(data)<8 or "BTCUSDT" not in data:
        raise RuntimeError("Insufficient usable symbols: "+json.dumps(errors))
    data={s:data[s] for s in sorted(data)}
    event_times=sorted(t for s in data for t in data[s]["fund"]
                       if sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
    if len(event_times)<100: raise RuntimeError("Insufficient aligned funding events")
    period=(ms(OOS_START),ms(OOS_END))
    common=dict(lookback_days=7,rebalance_days=7,tail_fraction=.20,
                regime_policy=POLICY,regime_threshold_pct=5.0,sideways_action="hold")
    print("RUN BASELINE",flush=True)
    baseline=sim.run(data,period,1.0,5,slip_bp=2,**common)
    known_policy={"default":0,"symbols":{
        "BTCUSDT":{"before":100,"after":50,"change_time_ms":BTC_CUTOVER_MS},
        "ETHUSDT":20
    }}
    default5_policy={"default":5,"symbols":{
        "BTCUSDT":{"before":100,"after":50,"change_time_ms":BTC_CUTOVER_MS},
        "ETHUSDT":20
    }}
    print("RUN CONFIRMED BTC/ETH FILTERS, REDUCE-ONLY EXEMPT",flush=True)
    known=sim.run(data,period,1.0,5,slip_bp=2,order_min_notional_policy=known_policy,
                  reduce_only_min_notional_exempt=True,**common)
    print("RUN ALL SYMBOLS DEFAULT 5 USDT, REDUCE-ONLY EXEMPT",flush=True)
    default5=sim.run(data,period,1.0,5,slip_bp=2,order_min_notional_policy=default5_policy,
                     reduce_only_min_notional_exempt=True,**common)
    print("RUN ALL SYMBOLS DEFAULT 5 USDT, NO REDUCE-ONLY EXEMPTION",flush=True)
    strict=sim.run(data,period,1.0,5,slip_bp=2,order_min_notional_policy=default5_policy,
                   reduce_only_min_notional_exempt=False,**common)
    report={
        "experiment":"EXP-024-MEAFLOW72-HISTORICAL-MIN-NOTIONAL-SENSITIVITY",
        "status":"completed",
        "strategy_branch":"MEAFLOW-72 (read-only base; no modifications)",
        "research_branch":"research/meaflow-exp024-min-notional-backtest-v1",
        "oos_period_utc":{"start":OOS_START,"end":OOS_END},
        "configuration":{"capital_usdt":100,"leverage":1,"lookback_days":7,
            "rebalance_days":7,"tail_fraction":0.20,"regime_policy":POLICY,
            "btc_regime_threshold_pct":5,"sideways_action":"hold",
            "fee_bp_one_way":5,"slippage_bp_one_way":2},
        "filter_rules":{
            "BTCUSDT":{"min_notional_before_2026_04_14T06_30_UTC":100,
                       "min_notional_from_2026_04_14T06_30_UTC":50},
            "ETHUSDT":{"min_notional_since_2023_11_02":20},
            "other_symbols":{"default_assumption":5,
                "note":"General USD-M baseline from Binance's 2021 rule; no per-symbol historical change audit completed."},
            "reduce_only":"When enabled, a delta that strictly reduces an existing same-direction position is exempted from MIN_NOTIONAL. The actual live order must carry reduceOnly=true for this exemption.",
            "quantity_steps":"Not applied. Binance exchangeInfo returned HTTP 451 from the hosted runner; MARKET_LOT_SIZE rounding is a separate unresolved execution constraint."
        },
        "data_errors":errors,"loaded_symbols":list(data),
        "baseline":compact(baseline),
        "confirmed_btc_eth_reduce_only_exempt":compact(known),
        "default5_all_symbols_reduce_only_exempt":compact(default5),
        "default5_all_symbols_no_reduce_only_exempt":compact(strict),
        "interpretation_limits":[
            "This is a sensitivity backtest using known historical BTC/ETH minimums and a 5 USDT baseline assumption for other symbols.",
            "Other-symbol historical filter changes have not been verified; the default-5 scenarios are not an exact reconstruction of every past Binance filter.",
            "The current exchangeInfo endpoint was blocked with HTTP 451; quantity step-size and minQty rules are not modeled.",
            "The reduce-only exemption is a modeled execution policy; the simulator does not prove the live bot sends reduceOnly=true.",
            "No changes to MEAFLOW-72 or MEAFLOW-52. All code changes are isolated to this research branch."
        ]
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp024_min_notional_backtest.json").write_text(
        json.dumps(report,indent=2),encoding="utf-8")
    print("BASE",json.dumps(report["baseline"]),flush=True)
    print("KNOWN",json.dumps(report["confirmed_btc_eth_reduce_only_exempt"]),flush=True)
    print("DEFAULT5",json.dumps(report["default5_all_symbols_reduce_only_exempt"]),flush=True)
    print("STRICT",json.dumps(report["default5_all_symbols_no_reduce_only_exempt"]),flush=True)

if __name__=="__main__":
    main()
