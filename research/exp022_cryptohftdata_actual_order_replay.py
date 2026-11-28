#!/usr/bin/env python3
"""EXP-022 actual MEAFLOW-72 order replay using CryptoHFTData Binance L2.

Uses five actual BTC/ETH/SOL order deltas on 2026-09-03 (bull) and
2026-10-24 (bear). Reconstructs the order book from hourly snapshots and
sequence-checked updates. For 2026-09-03, the previous hour is also loaded
because the 08:00 file has no hour-start checkpoint.

For each signal, report both:
- as-of state known to the collector at the signal time (no look-ahead);
- first complete message received after the signal (latency sensitivity).

No strategy code is changed. Raw Parquet files are deleted after processing.
"""
import json, hashlib, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

BASES = [
    "https://api.cryptohftdata.com/v1/download?file=",
    "https://api.cryptohftdata.com/download?file=",
]
SOURCE = Path("research-results/exp019_full_oos_order_events.json")
OUT = Path("research-results/exp022_cryptohftdata_actual_order_replay.json")
SELECT_DATES = {"2026-09-03", "2026-10-24"}
SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
COLUMNS = [
    "received_time","event_time","transaction_time","symbol","event_type",
    "first_update_id","final_update_id","prev_final_update_id","last_update_id",
    "side","price","quantity"
]

def ns_from_iso(value):
    return int(datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()*1_000_000_000)

def download_hour(date,hour,symbol):
    rel=f"binance_futures/{date}/{hour:02d}/{symbol}_orderbook.parquet"
    path=Path(f"/tmp/exp022_{date}_{hour:02d}_{symbol}.parquet")
    errors=[]
    for base in BASES:
        url=base+urllib.parse.quote(rel,safe="/")
        req=urllib.request.Request(url,headers={"User-Agent":"MEAFLOW-research/1.0"})
        try:
            h=hashlib.sha256(); size=0
            with urllib.request.urlopen(req,timeout=180) as response, open(path,"wb") as f:
                while True:
                    b=response.read(1024*1024)
                    if not b: break
                    f.write(b); h.update(b); size+=len(b)
            return path,{"path":rel,"http_status":200,"bytes":size,"sha256":h.hexdigest()}
        except urllib.error.HTTPError as e:
            errors.append({"status":e.code,"url":url})
        except Exception as e:
            errors.append({"error":repr(e),"url":url})
    raise RuntimeError(json.dumps(errors))

def as_int(value):
    if pd.isna(value): return None
    return int(value)

def apply_message(group,state):
    etype=str(group.iloc[0]["event_type"])
    recv=int(group.iloc[0]["received_time"])
    event_ms=as_int(group.iloc[0]["event_time"])
    tx_ms=as_int(group.iloc[0]["transaction_time"])
    if etype=="snapshot":
        state["bids"].clear(); state["asks"].clear()
        state["valid"]=True
        state["snapshot_count"]+=1
        row0=group.iloc[0]
        last=as_int(row0["last_update_id"])
        if last is None: last=as_int(row0["final_update_id"])
        state["last_update_id"]=last
        for row in group.itertuples(index=False):
            side=str(row.side).lower()
            if side not in ("bid","ask"): continue
            p=float(row.price); q=float(row.quantity)
            book=state["bids"] if side=="bid" else state["asks"]
            if q>0: book[p]=q
            else: book.pop(p,None)
        state["last_event_time_ms"]=event_ms
        state["last_transaction_time_ms"]=tx_ms if tx_ms is not None else event_ms
        state["last_received_time_ns"]=recv
        return "snapshot"
    if etype!="update": return "other"
    if not state["valid"] or state["last_update_id"] is None:
        state["updates_ignored_invalid"]+=1
        return "ignored_invalid"
    row0=group.iloc[0]
    first=as_int(row0["first_update_id"])
    final=as_int(row0["final_update_id"])
    prev=as_int(row0["prev_final_update_id"])
    last=state["last_update_id"]
    bridge=(first is not None and final is not None and first<=last<=final)
    contiguous=(prev is not None and prev==last)
    if not (bridge or contiguous):
        state["valid"]=False
        state["gap_count"]+=1
        state["gap_examples"].append({"last_update_id":last,"first_update_id":first,
                                      "prev_final_update_id":prev,"final_update_id":final,
                                      "received_time_ns":recv})
        return "gap"
    for row in group.itertuples(index=False):
        side=str(row.side).lower()
        if side not in ("bid","ask"): continue
        p=float(row.price); q=float(row.quantity)
        book=state["bids"] if side=="bid" else state["asks"]
        if q>0: book[p]=q
        else: book.pop(p,None)
    state["last_update_id"]=final
    state["last_event_time_ms"]=event_ms
    state["last_transaction_time_ms"]=tx_ms if tx_ms is not None else event_ms
    state["last_received_time_ns"]=recv
    return "update"

def state_copy(state,recv_ns,signal_ns,tag):
    bids=sorted(state["bids"].items(),reverse=True)[:100]
    asks=sorted(state["asks"].items())[:100]
    return {
        "tag":tag,"valid":state["valid"],"last_update_id":state["last_update_id"],
        "received_time_ns":state["last_received_time_ns"],
        "delay_ms":(state["last_received_time_ns"]-signal_ns)/1_000_000 if state["last_received_time_ns"] is not None else None,
        "last_event_time_ms":state["last_event_time_ms"],
        "last_transaction_time_ms":state["last_transaction_time_ms"],
        "book_age_ms":(signal_ns/1_000_000-state["last_transaction_time_ms"])
            if state["last_transaction_time_ms"] is not None else None,
        "bids":bids,"asks":asks,
        "gap_count_before_capture":state["gap_count"],
        "snapshot_count_before_capture":state["snapshot_count"],
    }

def process_file(path,state,signal_ns=None,stop_at_first_after=False):
    df=pd.read_parquet(path,columns=COLUMNS)
    if len(df)==0: raise RuntimeError("empty parquet")
    recv_values=df["received_time"].to_numpy()
    if (recv_values[1:]<recv_values[:-1]).any():
        raise RuntimeError("received_time moved backwards; refusing to reorder")
    meta={"rows":len(df),"first_received_time_ns":int(recv_values[0]),
          "last_received_time_ns":int(recv_values[-1]),
          "snapshot_messages":int((df["event_type"]=="snapshot").sum())}
    before=None; after=None; after_recv=None
    for recv,group in df.groupby("received_time",sort=False):
        recv=int(recv)
        if signal_ns is not None and recv>signal_ns and before is None:
            if state["valid"]:
                before=state_copy(state,state["last_received_time_ns"],signal_ns,"asof_before_first_post_signal_message")
        kind=apply_message(group,state)
        if signal_ns is not None and recv>=signal_ns and after is None and state["valid"]:
            after=state_copy(state,recv,signal_ns,"after_first_message_at_or_after_signal")
            after_recv=recv
            if recv==signal_ns and before is None:
                before=after
            if stop_at_first_after:
                break
    return meta,before,after,after_recv

def sweep(levels,qty):
    rem=qty; filled=0.0; notional=0.0
    for price,avail in levels:
        take=min(rem,avail)
        if take>0:
            filled+=take; notional+=take*price; rem-=take
        if rem<=max(1e-12,qty*1e-10):
            rem=0.0; break
    return {"filled_qty":filled,"remaining_qty":max(0.0,rem),
            "vwap":notional/filled if filled>0 else None,"execution_notional_usdt":notional}

def execute(order,book,signal_ns):
    if not book or not book["valid"]:
        return {"status":"invalid_or_missing_book"}
    bids=book["bids"]; asks=book["asks"]
    if not bids or not asks: return {"status":"empty_or_one_sided_book"}
    side=order["side"]; qty=abs(float(order["quantity_delta"]))
    levels=asks if side=="BUY" else bids
    ex=sweep(levels,qty)
    mid=(bids[0][0]+asks[0][0])/2
    vwap=ex["vwap"]; ref=float(order["reference_price"])
    cost_mid=((vwap/mid-1) if side=="BUY" else (mid/vwap-1))*10000 if vwap else None
    cost_mark=((vwap/ref-1) if side=="BUY" else (ref-vwap)/ref)*10000 if vwap else None
    spread=(asks[0][0]-bids[0][0])/mid*10000
    full=ex["remaining_qty"]<=max(1e-12,qty*1e-10)
    return {
        "status":"full_depth_sweep" if full else "insufficient_displayed_depth",
        "side":side,"quantity":qty,"strategy_order_notional_usdt":float(order["notional_usdt"]),
        "reference_mark_price":ref,"best_bid":bids[0][0],"best_ask":asks[0][0],
        "mid":mid,"spread_bp":spread,"vwap":vwap,
        "filled_qty":ex["filled_qty"],"remaining_qty":ex["remaining_qty"],
        "market_cost_vs_mid_bp":cost_mid,"market_cost_vs_mark_bp":cost_mark,
        "book_delay_ms":book["delay_ms"],"book_age_ms":book["book_age_ms"],
        "sequence_gaps_before_capture":book["gap_count_before_capture"],
        "snapshots_before_capture":book["snapshot_count_before_capture"],
        "last_update_id":book["last_update_id"]
    }

def main():
    src=json.loads(SOURCE.read_text(encoding="utf-8"))
    events=[e for e in src["all_oos_order_events"] if e["time_utc"][:10] in SELECT_DATES]
    orders=[]
    for event in events:
        for o in event["orders"]:
            if o["symbol"] in SYMBOLS:
                orders.append({**o,"time_utc":event["time_utc"],"regime":event["regime"],
                               "active_mode":event["active_mode"]})
    grouped={}
    for o in orders:
        grouped.setdefault((o["time_utc"][:10],o["time_utc"][11:13],o["symbol"]),[]).append(o)
    report={"experiment":"EXP-022-CRYPTOHFTDATA-ACTUAL-MEAFLOW72-ORDER-REPLAY",
            "status":"running","source":"CryptoHFTData Binance USD-M L2 hourly Parquet, anonymous access",
            "order_source":"EXP-019 full OOS event export",
            "execution_method":"Rebuild from snapshots and sequence-checked updates in published row order; sweep exact actual order delta against visible bid/ask levels.",
            "signal_state_methods":{
                "asof":"Last valid book state known by collector at signal timestamp (no look-ahead).",
                "first_after":"Book after first complete message received at or after signal; delay is measured from received_time."
            },
            "assumptions":{"fee_bp_one_way":5,"existing_model_slippage_bp_one_way":2,
                           "capital_reference_usdt":100,"leverage":1},
            "limitations":[
                "L2 is aggregated price-level data, not L3/FIFO queue position.",
                "A displayed-depth sweep is a snapshot taker-cost estimate, not a guarantee of live fills.",
                "No network delay beyond the archive receive timestamp, hidden liquidity, impact after the snapshot, or exchange liquidation engine is modeled.",
                "The two dates are a small bull/bear execution sample, not all 268 OOS order deltas.",
                "No profitability, final capital, or strategy drawdown is recalculated."
            ],
            "files":[],"orders":[]}
    for (date,hour,symbol),sym_orders in sorted(grouped.items()):
        target_ns=ns_from_iso(sym_orders[0]["time_utc"])
        state={"bids":{},"asks":{},"valid":False,"last_update_id":None,
               "last_event_time_ms":None,"last_transaction_time_ms":None,
               "last_received_time_ns":None,"gap_count":0,"gap_examples":[],
               "snapshot_count":0,"updates_ignored_invalid":0}
        hours=[hour]
        if date=="2026-09-03" and hour=="08": hours=[ "06","07","08" ]
        file_meta=[]; before=None; after=None
        for h in hours:
            path,meta=download_hour(date,int(h),symbol)
            try:
                fm,b,a,ar=process_file(path,state,target_ns if h==hour else None,
                                       stop_at_first_after=(h==hour))
                file_meta.append({**meta,**fm})
                if h==hour:
                    before=b; after=a
            finally:
                path.unlink(missing_ok=True)
        report["files"].append({"date":date,"hour":hour,"symbol":symbol,
                                "metadata":file_meta,"sequence_gaps":state["gap_count"],
                                "gap_examples":state["gap_examples"][:5],
                                "snapshots_applied":state["snapshot_count"],
                                "updates_ignored_invalid":state["updates_ignored_invalid"]})
        for o in sym_orders:
            asof_result=execute(o,before,target_ns) if before else {"status":"no_valid_asof_book"}
            after_result=execute(o,after,target_ns) if after else {"status":"no_valid_post_signal_book"}
            report["orders"].append({
                "time_utc":o["time_utc"],"regime":o["regime"],"symbol":symbol,
                "side":o["side"],"order_delta_notional_usdt":o["notional_usdt"],
                "asof_execution":asof_result,"first_after_execution":after_result
            })
        print("DONE",date,hour,symbol,"orders",len(sym_orders),
              "gaps",state["gap_count"],"snapshots",state["snapshot_count"],flush=True)
    def aggregate(which):
        valid=[o[which] for o in report["orders"] if o[which].get("status")=="full_depth_sweep"]
        if not valid: return {"valid_orders":0}
        costs=[x["market_cost_vs_mid_bp"] for x in valid]
        mark=[x["market_cost_vs_mark_bp"] for x in valid]
        notionals=[x["strategy_order_notional_usdt"] for x in valid]
        return {
            "valid_orders":len(valid),
            "all_orders":len(report["orders"]),
            "full_depth_fill_count":len(valid),
            "median_cost_vs_mid_bp":sorted(costs)[len(costs)//2],
            "max_cost_vs_mid_bp":max(costs),
            "median_cost_vs_mark_bp":sorted(mark)[len(mark)//2],
            "max_cost_vs_mark_bp":max(mark),
            "notional_weighted_cost_vs_mid_bp":sum(c*n for c,n in zip(costs,notionals))/sum(notionals),
            "notional_weighted_cost_vs_mark_bp":sum(c*n for c,n in zip(mark,notionals))/sum(notionals)
        }
    report["summary"]={
        "orders":len(report["orders"]),
        "asof":aggregate("asof_execution"),
        "first_after":aggregate("first_after_execution")
    }
    report["status"]="completed"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print("SUMMARY",json.dumps(report["summary"]),flush=True)

if __name__=="__main__":
    main()
