#!/usr/bin/env python3
"""Download and QA Binance USD-M daily bookDepth archives for a bounded month range.
Produces compact per-minute depth-band features; these are coarse depth bands,
NOT per-price-level L2 or queue data.
"""
import argparse, calendar, csv, gzip, hashlib, io, json, time, urllib.request, zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = "https://data.binance.vision/data/futures/um/daily/bookDepth"

def days_between(start, end):
    sy, sm = map(int, start.split("-")); ey, em = map(int, end.split("-"))
    d = date(sy, sm, 1); last = date(ey, em, calendar.monthrange(ey, em)[1])
    while d <= last:
        yield d.isoformat()
        d += timedelta(days=1)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 research-only"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

def verify(data, checksum_data, label):
    token = checksum_data.decode("utf-8").strip().split()[0].lower()
    actual = hashlib.sha256(data).hexdigest()
    if actual != token:
        raise RuntimeError(f"SHA256 mismatch {label}: {actual} != {token}")
    return actual

def parse_timestamp_ms(value):
    """Binance bookDepth CSV timestamps are UTC datetime strings, not integer ms."""
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        pass
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def read_zip(data, label):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names: raise RuntimeError(f"No CSV in {label}")
        with z.open(names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            reader = csv.DictReader(text)
            fields = {x.lower(): x for x in (reader.fieldnames or [])}
            required = {"timestamp", "percentage", "depth", "notional"}
            if not required.issubset(fields):
                raise RuntimeError(f"Unexpected bookDepth columns {reader.fieldnames} in {label}")
            rows = []
            for r in reader:
                rows.append((parse_timestamp_ms(r[fields["timestamp"]]), float(r[fields["percentage"]]),
                             float(r[fields["depth"]]), float(r[fields["notional"]])))
            return rows, reader.fieldnames

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-05")
    ap.add_argument("--end", default="2024-06")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--out", default="research-output")
    args=ap.parse_args()
    symbols=[x.strip().upper() for x in args.symbols.split(",") if x.strip()]
    if len(symbols)>3 or not symbols: raise SystemExit("Provide 1-3 symbols")
    days=list(days_between(args.start,args.end))
    if len(days)>62: raise SystemExit("Pilot limited to 62 days")
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    report={"source":"Binance Vision official USD-M Futures daily bookDepth archives",
            "start":args.start,"end":args.end,"sampling_seconds":30,
            "interpretation":"Cumulative/aggregated percentage-band depth proxy; not full L2 price levels, order additions/cancellations, or queue position.",
            "symbols":{}}
    wanted={-2.0,-1.0,-0.2,0.2,1.0,2.0}
    for symbol in symbols:
        report["symbols"][symbol]={}
        monthly=defaultdict(dict); month_meta=defaultdict(lambda:{"days":0,"rows":0,"checksums_verified":0,"missing_days":[],"band_rows":defaultdict(int),"bad_timestamp_days":[]})
        for day in days:
            name=f"{symbol}-bookDepth-{day}.zip"
            url=f"{BASE}/{symbol}/{name}"
            try:
                blob=get(url); checksum=get(url+".CHECKSUM")
            except Exception as e:
                month=day[:7]; month_meta[month]["missing_days"].append(day)
                continue
            digest=verify(blob,checksum,name)
            rows,fields=read_zip(blob,name)
            by_minute={}
            per_band=defaultdict(list)
            for ts,pct,depth,notional in rows:
                if pct not in wanted: continue
                per_band[pct].append(ts)
                minute=ts//60000
                slot=by_minute.setdefault(minute,{})
                old=slot.get(pct)
                if old is None or ts>old[0]: slot[pct]=(ts,depth,notional)
            for pct in wanted:
                tslist=per_band[pct]
                if any(b<=a for a,b in zip(tslist,tslist[1:])):
                    month_meta[day[:7]]["bad_timestamp_days"].append(day)
                month_meta[day[:7]]["band_rows"][str(pct)]+=len(tslist)
            month=day[:7]; meta=month_meta[month]
            meta["days"]+=1; meta["rows"]+=len(rows); meta["checksums_verified"]+=1
            for minute,vals in by_minute.items():
                monthly[month][minute]=vals
        for month, mins in monthly.items():
            path=out/f"{symbol}-{month}-bookdepth-1m.csv.gz"
            bands=sorted(wanted)
            with gzip.open(path,"wt",encoding="utf-8",newline="") as gz:
                w=csv.writer(gz)
                header=["open_time_ms"]
                for p in bands: header += [f"depth_{p:g}pct",f"notional_{p:g}pct"]
                w.writerow(header)
                for minute,vals in sorted(mins.items()):
                    row=[minute*60000]
                    for p in bands:
                        x=vals.get(p); row += [x[1],x[2]] if x else ["",""]
                    w.writerow(row)
            m=month_meta[month]
            y, mo = map(int, month.split("-"))
            month_start = datetime(y, mo, 1, tzinfo=timezone.utc)
            if mo == 12:
                month_end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
            else:
                month_end = datetime(y, mo + 1, 1, tzinfo=timezone.utc)
            start_minute = int(month_start.timestamp() * 1000) // 60000
            end_minute = int(month_end.timestamp() * 1000) // 60000
            expected_minutes = end_minute - start_minute
            actual_minutes = {x for x in mins if start_minute <= x < end_minute}
            missing_minute_ranges = []
            run_start = None
            prev = None
            for minute in range(start_minute, end_minute):
                if minute not in actual_minutes:
                    if run_start is None: run_start = minute
                elif run_start is not None:
                    missing_minute_ranges.append({
                        "start_utc": datetime.fromtimestamp(run_start * 60, timezone.utc).isoformat(),
                        "end_utc_exclusive": datetime.fromtimestamp(minute * 60, timezone.utc).isoformat(),
                        "missing_minutes": minute - run_start
                    })
                    run_start = None
            if run_start is not None:
                missing_minute_ranges.append({
                    "start_utc": datetime.fromtimestamp(run_start * 60, timezone.utc).isoformat(),
                    "end_utc_exclusive": month_end.isoformat(),
                    "missing_minutes": end_minute - run_start
                })
            report["symbols"][symbol][month]={
                "days_found":m["days"],"days_missing":m["missing_days"],
                "archive_rows":m["rows"],"checksums_verified":m["checksums_verified"],
                "minute_feature_rows":len(actual_minutes),
                "expected_minutes_for_month":expected_minutes,
                "missing_minutes_total":expected_minutes-len(actual_minutes),
                "coverage_pct":round(100*len(actual_minutes)/expected_minutes,4) if expected_minutes else 0,
                "first_feature_utc":datetime.fromtimestamp(min(actual_minutes)*60,timezone.utc).isoformat() if actual_minutes else None,
                "last_feature_utc":datetime.fromtimestamp(max(actual_minutes)*60,timezone.utc).isoformat() if actual_minutes else None,
                "missing_minute_ranges":missing_minute_ranges,
                "selected_band_rows":dict(m["band_rows"]),
                "timestamp_order_issues":m["bad_timestamp_days"],
                "feature_file":path.name,
                "note":"Minute feature retains the last available 30s snapshot in each minute for each selected band. Coverage is checked against every UTC calendar minute in the month."
            }
    (out/"bookdepth_qa_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
