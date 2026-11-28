#!/usr/bin/env python3
"""EXP-021: verify free CryptoHFTData Binance Futures L2 files at actual signals.

Downloads only five hourly Parquet files corresponding to the exact BTC/ETH/SOL
orders selected from EXP-019. No API key is used. Files stay in /tmp and are
deleted after metadata/sequence QA; only a compact JSON report is committed.
"""
import json, hashlib, urllib.request, urllib.error, time
from pathlib import Path
import pyarrow.parquet as pq

FILES = [
    ("2026-09-03", "08", "BTCUSDT"),
    ("2026-09-03", "08", "SOLUSDT"),
    ("2026-10-24", "16", "BTCUSDT"),
    ("2026-10-24", "16", "ETHUSDT"),
    ("2026-10-24", "16", "SOLUSDT"),
    ("2025-10-09", "08", "BTCUSDT"),
    ("2025-10-09", "08", "SOLUSDT"),
    ("2026-07-07", "00", "BTCUSDT"),
    ("2026-07-07", "00", "SOLUSDT"),
    ("2026-10-30", "00", "BTCUSDT"),
    ("2026-10-30", "00", "ETHUSDT"),
    ("2026-10-30", "00", "SOLUSDT"),
    ("2026-05-11", "08", "BTCUSDT"),
    ("2026-05-11", "08", "ETHUSDT"),
    ("2026-04-18", "16", "BTCUSDT"),
    ("2026-04-18", "16", "SOLUSDT"),
    ("2026-09-11", "08", "BTCUSDT"),
    ("2026-09-11", "08", "SOLUSDT"),
    ("2026-08-20", "08", "BTCUSDT"),
    ("2026-09-18", "16", "BTCUSDT"),
    ("2026-09-22", "00", "BTCUSDT"),
    ("2026-10-15", "08", "SOLUSDT"),
    ("2026-10-24", "16", "BCHUSDT"),
    ("2026-10-24", "16", "DOTUSDT"),
    ("2026-10-24", "16", "TRXUSDT"),
    ("2026-10-30", "00", "XRPUSDT"),
    ("2026-09-18", "16", "DOGEUSDT"),
    ("2026-09-18", "16", "LTCUSDT"),
    ("2026-09-22", "00", "DOGEUSDT"),
    ("2026-09-22", "00", "LTCUSDT"),
    ("2026-10-15", "08", "LTCUSDT"),
]
BASES = [
    "https://api.cryptohftdata.com/v1/download?file=",
    "https://api.cryptohftdata.com/download?file=",
]

def download(date, hour, symbol, path):
    rel = f"binance_futures/{date}/{hour}/{symbol}_orderbook.parquet"
    errors = []
    for base in BASES:
        url = base + urllib.parse.quote(rel, safe="/")
        req = urllib.request.Request(url, headers={"User-Agent":"MEAFLOW-research/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=180) as response, open(path,"wb") as f:
                h=hashlib.sha256()
                size=0
                while True:
                    b=response.read(1024*1024)
                    if not b: break
                    f.write(b); h.update(b); size+=len(b)
                return {"url":url,"http_status":response.status,"bytes":size,"sha256":h.hexdigest()}
        except urllib.error.HTTPError as e:
            errors.append({"url":url,"http_status":e.code,"message":str(e)})
        except Exception as e:
            errors.append({"url":url,"error":repr(e)})
    raise RuntimeError(json.dumps(errors))

def qa(path, date, hour, symbol):
    pf=pq.ParquetFile(path)
    table=pf.read()
    cols=set(table.column_names)
    required={"received_time","event_time","transaction_time","symbol","event_type",
              "first_update_id","final_update_id","prev_final_update_id","last_update_id",
              "side","price","quantity"}
    missing=sorted(required-cols)
    if missing:
        raise RuntimeError(f"missing columns: {missing}")
    df=table.to_pandas()
    if len(df)==0:
        raise RuntimeError("empty Parquet file")
    if set(df["symbol"].dropna().unique()) != {symbol}:
        raise RuntimeError("symbol mismatch")
    counts=df["event_type"].value_counts(dropna=False).to_dict()
    snaps=df[df["event_type"]=="snapshot"]
    updates=df[df["event_type"]=="update"]
    # Group rows by one original exchange message; the archive retains published order.
    groups=updates.drop_duplicates(["received_time","first_update_id","final_update_id","prev_final_update_id"])
    group_records=groups[["received_time","event_time","transaction_time","first_update_id","final_update_id","prev_final_update_id"]].to_dict("records")
    gaps=[]
    for prev,cur in zip(group_records,group_records[1:]):
        if cur["prev_final_update_id"] is not None and prev["final_update_id"] is not None:
            if int(cur["prev_final_update_id"]) != int(prev["final_update_id"]):
                gaps.append({"prev_final":int(prev["final_update_id"]),
                             "current_prev":int(cur["prev_final_update_id"]),
                             "current_final":int(cur["final_update_id"])})
    # Check whether the file starts with a checkpoint snapshot at the hour boundary.
    first_recv=int(df["received_time"].min())
    hour_start_ns=int(__import__("datetime").datetime.fromisoformat(
        f"{date}T{hour}:00:00+00:00").timestamp()*1_000_000_000)
    first_group=df[df["received_time"]==first_recv]
    first_group_snapshot=bool((first_group["event_type"]=="snapshot").any())
    # Count distinct snapshot message groups; pre-2026-09-30 duplicate REST copies are documented.
    snapshot_groups=snaps.drop_duplicates(["received_time","last_update_id","final_update_id"])
    snapshot_details=[]
    for _, row in snapshot_groups.head(10).iterrows():
        snapshot_details.append({
            "received_time_ns": int(row["received_time"]),
            "event_time_ms": int(row["event_time"]),
            "last_update_id": int(row["last_update_id"]) if row["last_update_id"] is not None else None,
            "final_update_id": int(row["final_update_id"]) if row["final_update_id"] is not None else None,
            "side": str(row["side"]),
        })
    first_rows=df.head(5)[["received_time","event_time","transaction_time","event_type","first_update_id","final_update_id","prev_final_update_id","last_update_id","side"]].to_dict("records")
    return {
        "date":date,"hour_utc":hour,"symbol":symbol,
        "rows":len(df),"event_type_counts":{str(k):int(v) for k,v in counts.items()},
        "snapshot_rows":len(snaps),"snapshot_groups":len(snapshot_groups),
        "first_snapshot_received_time_ns":int(snapshot_groups["received_time"].min()) if len(snapshot_groups) else None,
        "last_snapshot_received_time_ns":int(snapshot_groups["received_time"].max()) if len(snapshot_groups) else None,
        "snapshot_details":snapshot_details,
        "first_rows":first_rows,
        "first_received_time_ns":first_recv,"hour_start_ns":hour_start_ns,
        "first_group_is_snapshot":first_group_snapshot,
        "first_group_rows":len(first_group),
        "min_event_time_ms":int(df["event_time"].min()),
        "max_event_time_ms":int(df["event_time"].max()),
        "min_transaction_time_ms":int(df["transaction_time"].dropna().min()) if df["transaction_time"].notna().any() else None,
        "max_transaction_time_ms":int(df["transaction_time"].dropna().max()) if df["transaction_time"].notna().any() else None,
        "update_message_groups":len(group_records),
        "sequence_gaps_within_file":len(gaps),
        "first_sequence_gaps":gaps[:5],
        "has_hour_start_checkpoint":first_group_snapshot and first_recv <= hour_start_ns+5_000_000_000,
        "schema_columns":table.column_names,
    }

def main():
    report={"experiment":"EXP-021-CRYPTOHFTDATA-BINANCE-FUTURES-L2-SOURCE-QA",
            "status":"running","access":"anonymous, no API key",
            "source":"CryptoHFTData hourly Binance USD-M orderbook Parquet",
            "source_path_pattern":"binance_futures/{date}/{hour}/{symbol}_orderbook.parquet",
            "orders_selected_from":"EXP-019 actual OOS order events",
            "files":[],"limitations":[
                "This is source and sequence QA only; it does not calculate execution costs or fills.",
                "L2 is aggregate quantity per price level, not L3/FIFO queue position.",
                "Binance reconnects can create short sequence gaps; books must be invalidated at a gap until a new snapshot.",
                "Provider documents duplicate REST snapshot rows in some pre-2026-09-30 files; replay must treat identical snapshots safely.",
                "Provider documents historical empty-snapshot omissions before its 2026-10 data-quality release; any affected stale book must be rejected."
            ]}
    for date,hour,symbol in FILES:
        path=Path(f"/tmp/exp021_{date}_{hour}_{symbol}.parquet")
        print("DOWNLOAD",date,hour,symbol,flush=True)
        try:
            meta=download(date,hour,symbol,path)
            checks=qa(path,date,hour,symbol)
            report["files"].append({"download":meta,"qa":checks,"status":"ok"})
            print("OK",date,hour,symbol,"rows",checks["rows"],"gaps",checks["sequence_gaps_within_file"],flush=True)
        except Exception as e:
            report["files"].append({"date":date,"hour_utc":hour,"symbol":symbol,"status":"error","error":str(e)})
            print("ERROR",date,hour,symbol,repr(e),flush=True)
        finally:
            path.unlink(missing_ok=True)
        time.sleep(0.2)
    ok=[x for x in report["files"] if x["status"]=="ok"]
    report["summary"]={
        "files_tested":len(FILES),"files_downloaded_and_read":len(ok),
        "files_with_sequence_gaps":sum(x["qa"]["sequence_gaps_within_file"]>0 for x in ok),
        "files_with_hour_start_checkpoint":sum(x["qa"]["has_hour_start_checkpoint"] for x in ok),
        "total_rows":sum(x["qa"]["rows"] for x in ok),
        "failed_files":len(FILES)-len(ok)
    }
    report["status"]="completed" if len(ok)==len(FILES) else "partial"
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp021_cryptohftdata_l2_source_qa.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("SUMMARY",json.dumps(report["summary"]),flush=True)

if __name__=="__main__":
    import urllib.parse
    main()
