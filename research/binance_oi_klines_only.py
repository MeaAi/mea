#!/usr/bin/env python3
"""Free Binance USD-M monthly 1m kline downloader for OI research.
Downloads only klines (no aggTrades), verifies official SHA256 checksums,
and emits the compact CSV schema consumed by oi_positioning_shock.py.
"""
import argparse,csv,gzip,hashlib,io,re,time,urllib.request,zipfile
from pathlib import Path

BASE="https://data.binance.vision/data/futures/um/monthly/klines"
def months_between(start,end):
    y,m=map(int,start.split("-")); ey,em=map(int,end.split("-"))
    while (y,m)<=(ey,em):
        yield f"{y:04d}-{m:02d}"
        m+=1
        if m==13:y,m=y+1,1
def fetch(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size:return
    tmp=Path(str(path)+".part")
    err=None
    for attempt in range(5):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 research-only"})
            with urllib.request.urlopen(req,timeout=180) as r,tmp.open("wb") as f:
                while True:
                    chunk=r.read(1024*1024)
                    if not chunk:break
                    f.write(chunk)
            tmp.replace(path);return
        except Exception as e:
            err=e;tmp.unlink(missing_ok=True);time.sleep(2**attempt)
    raise RuntimeError(f"download failed {url}: {err}")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True,help="YYYY-MM")
    ap.add_argument("--end",required=True,help="YYYY-MM")
    ap.add_argument("--symbols",default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--out",default="research-output")
    a=ap.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}",a.start) or not re.fullmatch(r"\d{4}-\d{2}",a.end):ap.error("start/end must be YYYY-MM")
    months=list(months_between(a.start,a.end))
    if len(months)>48:ap.error("maximum 48 months per run")
    root=Path(a.out);cache=root/"cache";root.mkdir(parents=True,exist_ok=True)
    for sym in [x.strip().upper() for x in a.symbols.split(",") if x.strip()]:
        for month in months:
            name=f"{sym}-1m-{month}.zip"; url=f"{BASE}/{sym}/1m/{name}"
            zp=cache/sym/name; cp=Path(str(zp)+".CHECKSUM")
            print(f"[{sym} {month}] fetching klines",flush=True)
            fetch(url,zp);fetch(url+".CHECKSUM",cp)
            expected=cp.read_text().strip().split()[0].lower()
            h=hashlib.sha256()
            with zp.open("rb") as f:
                for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
            if h.hexdigest()!=expected:raise RuntimeError(f"SHA256 mismatch: {name}")
            out=root/f"{sym}-{month}-1m-orderflow.csv.gz"
            with zipfile.ZipFile(zp) as z:
                fn=next(n for n in z.namelist() if n.lower().endswith(".csv"))
                with z.open(fn) as raw,io.TextIOWrapper(raw,encoding="utf-8",newline="") as src,gzip.open(out,"wt",encoding="utf-8",newline="") as dst:
                    reader=csv.reader(src);writer=csv.writer(dst)
                    writer.writerow(["open_time_ms","open","high","low","close"])
                    count=0
                    for r in reader:
                        if len(r)<5:continue
                        try:
                            t=int(r[0])
                            if t>=10**17:t//=10**6
                            elif t>=10**14:t//=10**3
                            writer.writerow([t,*r[1:5]]);count+=1
                        except (ValueError,IndexError):continue
            if count<1000:raise RuntimeError(f"too few kline rows {name}: {count}")
            print(f"[{sym} {month}] verified; {count:,} bars",flush=True)
    print("KLINE-ONLY DATA ACQUISITION COMPLETE",flush=True)
if __name__=="__main__":main()
