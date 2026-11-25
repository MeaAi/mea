#!/usr/bin/env python3
"""Free Binance Vision spot/perpetual/premium/funding archive acquisition and QA.
Pilot is intentionally capped at two months; no strategy result is claimed here.
"""
import argparse,csv,hashlib,io,json,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

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
    if kind=="spot":return f"{BASE}/spot/monthly/klines/{symbol}/1m/{symbol}-1m-{month}.zip"
    if kind=="perp":return f"{BASE}/futures/um/monthly/klines/{symbol}/1m/{symbol}-1m-{month}.zip"
    if kind=="premium":return f"{BASE}/futures/um/monthly/premiumIndexKlines/{symbol}/1m/{symbol}-1m-{month}.zip"
    if kind=="funding":return f"{BASE}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
    raise ValueError(kind)
def verify(blob,checksum,label):
    expected=checksum.decode().strip().split()[0].lower()
    actual=hashlib.sha256(blob).hexdigest()
    if expected!=actual:raise RuntimeError(f"SHA256 mismatch: {label}")
    return actual
def parse_ts(value):
    s=value.strip()
    try:t=int(float(s))
    except ValueError:
        dt=datetime.strptime(s,"%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp()*1000)
    if t>10**17:return t//10**6
    if t>10**14:return t//10**3
    return t
def inspect_csv(blob,kind):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names=[n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:raise RuntimeError("CSV not found in archive")
        rows=list(csv.reader(io.TextIOWrapper(z.open(names[0]),encoding="utf-8-sig",newline="")))
    if not rows:raise RuntimeError("empty CSV")
    first=rows[0]
    try:parse_ts(first[0]);has_header=False
    except (ValueError,IndexError):has_header=True
    data=rows[1:] if has_header else rows
    parsed=[]; bad=0
    for cols in data:
        if not cols:continue
        try:parsed.append(parse_ts(cols[0]))
        except (ValueError,IndexError):bad+=1
    if not parsed:raise RuntimeError(f"No parseable timestamps in {kind} CSV")
    return {"csv_name":names[0],"header":first if has_header else None,
            "data_rows":len(parsed),"bad_timestamp_rows":bad,
            "first_timestamp_ms":min(parsed),"last_timestamp_ms":max(parsed)}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",default="2024-05");p.add_argument("--end",default="2024-06")
    p.add_argument("--symbols",default="BTCUSDT,ETHUSDT,SOLUSDT");p.add_argument("--out",default="basis-output")
    a=p.parse_args();ms=list(months(a.start,a.end));syms=[s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    if len(ms)>2:raise SystemExit("Pilot cap: max two months per run")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    report={"source":"Binance Vision public archives","period":[a.start,a.end],"symbols":{},
      "checks":"Every archive and .CHECKSUM are downloaded; SHA256 must match.",
      "limitations":["This is data QA, not a profitability backtest.","Spot, USD-M perpetual and premium-index timestamps are checked independently; exact common-minute alignment is required downstream.","Funding archives are event observations; funding cashflows must be applied only at actual funding timestamps."]}
    for sym in syms:
      report["symbols"][sym]={}
      for month in ms:
       for kind in ("spot","perp","premium","funding"):
        url=archive_url(kind,sym,month);label=f"{sym}:{kind}:{month}"
        blob=get(url);chk=get(url+".CHECKSUM");digest=verify(blob,chk,label)
        meta=inspect_csv(blob,kind)
        report["symbols"][sym].setdefault(month,{})[kind]={**meta,"sha256":digest,"archive_bytes":len(blob)}
        print(f"QA OK {label}: {meta['data_rows']:,} rows",flush=True)
    (out/"basis_data_qa.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
