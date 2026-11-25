#!/usr/bin/env python3
"""Free Binance Vision spot/perpetual/premium/funding archive acquisition and QA.
Pilot is intentionally capped at two months; no strategy result is claimed here.
"""
import argparse,csv,hashlib,io,json,urllib.request,zipfile
from pathlib import Path
from datetime import datetime,timezone

BASE="https://data.binance.vision/data"
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"research-only"})
    with urllib.request.urlopen(req,timeout=120) as r:return r.read()
def months(a,b):
    y,m=map(int,a.split("-")); ey,em=map(int,b.split("-"))
    while (y,m)<=(ey,em):
        yield f"{y:04d}-{m:02d}"
        m+=1
        if m==13:y,m=y+1,1
def archive_url(kind,symbol,month):
    if kind=="spot":
        return f"{BASE}/spot/monthly/klines/{symbol}/1m/{symbol}-1m-{month}.zip"
    if kind=="perp":
        return f"{BASE}/futures/um/monthly/klines/{symbol}/1m/{symbol}-1m-{month}.zip"
    if kind=="premium":
        return f"{BASE}/futures/um/monthly/premiumIndexKlines/{symbol}/1m/{symbol}-1m-{month}.zip"
    if kind=="funding":
        return f"{BASE}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
    raise ValueError(kind)
def verify(blob,checksum,label):
    expected=checksum.decode().strip().split()[0].lower()
    actual=hashlib.sha256(blob).hexdigest()
    if expected!=actual:raise RuntimeError(f"SHA256 mismatch: {label}")
    return actual
def inspect_csv(blob,kind):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names=[n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:raise RuntimeError("CSV not found in archive")
        raw=z.read(names[0]).decode("utf-8-sig").splitlines()
    if not raw:raise RuntimeError("empty CSV")
    first=next(csv.reader([raw[0]]))
    has_header=not first[0].strip().replace(".","",1).isdigit()
    rows=raw[1:] if has_header else raw
    if not rows:raise RuntimeError("no data rows")
    # Klines have 12 fields; funding rows have 3-4 fields. Preserve schema/count only.
    parsed=0; first_ts=None; last_ts=None
    for line in rows:
        cols=next(csv.reader([line]))
        if not cols:continue
        try:t=int(float(cols[0]))
        except ValueError:continue
        if t>10**17:t//=10**6
        elif t>10**14:t//=10**3
        first_ts=t if first_ts is None else min(first_ts,t)
        last_ts=t if last_ts is None else max(last_ts,t)
        parsed+=1
    return {"csv_name":names[0],"header":first if has_header else None,
            "data_rows":parsed,"first_timestamp_ms":first_ts,"last_timestamp_ms":last_ts}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",default="2024-05");p.add_argument("--end",default="2024-06")
    p.add_argument("--symbols",default="BTCUSDT,ETHUSDT,SOLUSDT");p.add_argument("--out",default="basis-output")
    a=p.parse_args(); ms=list(months(a.start,a.end)); syms=[s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    if len(ms)>2:raise SystemExit("Pilot cap: max two months per run")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    report={"source":"Binance Vision public archives","period":[a.start,a.end],"symbols":{},"datasets":{},
      "checks":"Every archive and its .CHECKSUM are downloaded; SHA256 must match.",
      "limitations":["This is data QA, not a profitability backtest.","Spot, USD-M perpetual and premium-index kline timestamps are checked independently; exact common-minute alignment is required downstream.","Funding archives are event observations; funding cashflows must be applied only at actual funding timestamps."]}
    for sym in syms:
      report["symbols"][sym]={}
      for month in ms:
       for kind in ("spot","perp","premium","funding"):
        url=archive_url(kind,sym,month); label=f"{sym}:{kind}:{month}"
        blob=get(url); chk=get(url+".CHECKSUM"); digest=verify(blob,chk,label)
        meta=inspect_csv(blob,kind)
        report["symbols"][sym].setdefault(month,{})[kind]={**meta,"sha256":digest,"archive_bytes":len(blob)}
        print(f"QA OK {label}: {meta['data_rows']:,} rows",flush=True)
    (out/"basis_data_qa.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
