#!/usr/bin/env python3
"""EXP-023: current Binance USD-M order-filter audit of all MEAFLOW-72 OOS deltas.

Fetches public /fapi/v1/exchangeInfo (no API key) and checks all actual order
deltas exported by EXP-019 against current MARKET_LOT_SIZE and MIN_NOTIONAL.
This is a current-rule feasibility audit, not a historical exchange-filter
reconstruction and not a PnL backtest.
"""
import json, urllib.request
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
from pathlib import Path

SOURCE=Path("research-results/exp019_full_oos_order_events.json")
OUT=Path("research-results/exp023_binance_filter_audit.json")
URL="https://fapi.binance.com/fapi/v1/exchangeInfo"

def D(v):
    return Decimal(str(v)) if v is not None else None

def floor_allowed(qty,min_qty,step):
    if qty < min_qty:
        return Decimal("0")
    if step is None or step == 0:
        return qty
    units=((qty-min_qty)/step).to_integral_value(rounding=ROUND_DOWN)
    return min_qty+units*step

def fetch_exchange_info():
    req=urllib.request.Request(URL,headers={"User-Agent":"MEAFLOW-research/1.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        payload=json.loads(r.read().decode("utf-8"))
        status=r.status
    if status!=200:
        raise RuntimeError(f"exchangeInfo HTTP {status}")
    return payload

def reduce_only_candidate(order):
    before=D(order.get("from_notional_usdt") or 0)
    after=D(order.get("to_notional_usdt") or 0)
    if before is None or after is None or before==0:
        return False
    # A net delta strictly reduces the existing signed position without crossing zero.
    same_side=(after==0) or (before>0 and after>0) or (before<0 and after<0)
    return bool(same_side and abs(after)<abs(before))

def main():
    src=json.loads(SOURCE.read_text(encoding="utf-8"))
    info=fetch_exchange_info()
    server_time_ms=info.get("serverTime")
    symbols={x["symbol"]:x for x in info.get("symbols",[])}
    events=src["all_oos_order_events"]
    orders=[]
    for event in events:
        for o in event.get("orders",[]):
            orders.append({**o,"time_utc":event["time_utc"],"regime":event.get("regime")})
    result=[]
    filter_summary={}
    for order in orders:
        symbol=order["symbol"]
        meta=symbols.get(symbol)
        if not meta:
            result.append({"time_utc":order["time_utc"],"symbol":symbol,
                           "notional_usdt":order.get("notional_usdt"),
                           "status":"symbol_not_in_current_exchange_info"})
            continue
        filters={f["filterType"]:f for f in meta.get("filters",[])}
        lot=filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE")
        min_filter=filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL")
        min_qty=D(lot.get("minQty","0")) if lot else Decimal("0")
        step=D(lot.get("stepSize","0")) if lot else Decimal("0")
        max_qty=D(lot.get("maxQty")) if lot and lot.get("maxQty") is not None else None
        min_notional=D(min_filter.get("notional",min_filter.get("minNotional","0"))) if min_filter else Decimal("0")
        qty=abs(D(order["quantity_delta"]))
        price=D(order["reference_price"])
        original_notional=abs(D(order.get("notional_usdt",qty*price)))
        rounded=floor_allowed(qty,min_qty,step)
        rounded_notional=rounded*price
        qty_pass=(rounded>=min_qty and rounded>0 and (max_qty is None or rounded<=max_qty))
        reduce_candidate=reduce_only_candidate(order)
        min_notional_pass=(rounded_notional>=min_notional) or reduce_candidate
        status="pass"
        if not qty_pass: status="fail_market_lot_size"
        elif not min_notional_pass: status="fail_min_notional"
        result.append({
            "time_utc":order["time_utc"],"regime":order.get("regime"),
            "symbol":symbol,"side":order["side"],
            "original_delta_notional_usdt":float(original_notional),
            "quantity":str(qty),"rounded_quantity":str(rounded),
            "rounded_notional_usdt":float(rounded_notional),
            "quantity_reduction_usdt":float((qty-rounded)*price),
            "market_min_qty":str(min_qty),"market_step_size":str(step),
            "min_notional_usdt":float(min_notional),
            "reduce_only_candidate":reduce_candidate,
            "qty_filter_pass":qty_pass,
            "min_notional_pass_with_reduce_only_candidate":min_notional_pass,
            "min_notional_pass_without_reduce_only":rounded_notional>=min_notional,
            "status":status
        })
    for symbol,meta in symbols.items():
        if symbol not in {o["symbol"] for o in orders}: continue
        filters={f["filterType"]:f for f in meta.get("filters",[])}
        lot=filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE")
        nf=filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL")
        filter_summary[symbol]={
            "status":meta.get("status"),
            "market_min_qty":lot.get("minQty") if lot else None,
            "market_step_size":lot.get("stepSize") if lot else None,
            "market_max_qty":lot.get("maxQty") if lot else None,
            "min_notional_usdt":(nf.get("notional",nf.get("minNotional")) if nf else None),
            "lot_filter_used":"MARKET_LOT_SIZE" if "MARKET_LOT_SIZE" in filters else "LOT_SIZE_fallback"
        }
    statuses={}
    for x in result: statuses[x["status"]]=statuses.get(x["status"],0)+1
    summary={
        "total_oos_order_deltas":len(orders),
        "current_exchange_symbols_matched":sum(x["status"]!="symbol_not_in_current_exchange_info" for x in result),
        "orders_pass_current_filters_with_reduce_only_candidate":sum(x["status"]=="pass" for x in result),
        "orders_fail_market_lot_size":sum(x["status"]=="fail_market_lot_size" for x in result),
        "orders_fail_min_notional":sum(x["status"]=="fail_min_notional" for x in result),
        "orders_below_min_notional_but_reduce_only_candidate":sum(
            x.get("reduce_only_candidate") and not x.get("min_notional_pass_without_reduce_only",True) for x in result),
        "orders_requiring_quantity_rounding":sum(
            x.get("quantity") is not None and x.get("rounded_quantity")!=x.get("quantity") for x in result),
        "status_counts":statuses
    }
    report={
        "experiment":"EXP-023-BINANCE-USD-M-CURRENT-ORDER-FILTER-AUDIT",
        "status":"completed","source":"Public Binance USD-M GET /fapi/v1/exchangeInfo",
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
        "binance_server_time_ms":server_time_ms,
        "order_source":"EXP-019 all 268 actual MEAFLOW-72 OOS order deltas",
        "order_type_assumption":"MARKET_LOT_SIZE used for market-order feasibility; LOT_SIZE fallback only if market filter absent.",
        "reduce_only_assumption":"Candidate classification is based on signed from/to notional. It does not prove the eventual live order will carry reduceOnly=true.",
        "historical_limitations":[
            "exchangeInfo is current, not a historical archive of per-date symbol filters.",
            "Binance announced BTCUSDT USD-M minimum notional changed from 100 to 50 USDT effective 2026-04-14; this date-specific rule is known from the official notice.",
            "Other symbols may have changed filters over the historical OOS period; current values must not be projected backwards without historical evidence.",
            "No order is sent. No strategy simulator or main branch is modified."
        ],
        "summary":summary,"current_symbol_filters":filter_summary,"orders":result
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("SUMMARY",json.dumps(summary),flush=True)

if __name__=="__main__":
    main()
