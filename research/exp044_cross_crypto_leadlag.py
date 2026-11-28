#!/usr/bin/env python3
"""EXP-044 cross-crypto lead-lag screen. Public Binance Vision data only."""
import argparse, csv, hashlib, io, json, math, time, urllib.request, zipfile
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np

BASE="https://data.binance.vision/data/futures/um/monthly/klines"
SYMBOLS=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","SOLUSDT","LINKUSDT","LTCUSDT","BCHUSDT","DOTUSDT","TRXUSDT","AVAXUSDT"]

def months(start,end):
    y,m=map(int,start.split("-")); ey,em=map(int,end.split("-"))
    while (y,m)<=(ey,em):
        yield f"{y:04d}-{m:02d}"
        m+=1
        if m==13:y,m=y+1,1

def get(url,path):
    if path.exists() and path.stat().st_size:return
    path.parent.mkdir(parents=True,exist_ok=True)
    err=None
    for k in range(4):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=120) as r, path.open("wb") as f:
                while True:
                    b=r.read(1024*1024)
                    if not b:break
                    f.write(b)
            return
        except Exception as e:
            err=str(e); path.unlink(missing_ok=True); time.sleep(2**k)
    raise RuntimeError(f"{url}: {err}")

def load_month(sym,month,root):
    name=f"{sym}-1h-{month}.zip"; p=root/"cache"/sym/name
    url=f"{BASE}/{sym}/1h/{name}"
    get(url,p); cp=Path(str(p)+".CHECKSUM"); get(url+".CHECKSUM",cp)
    expected=cp.read_text().strip().split()[0].lower()
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    if h!=expected: raise RuntimeError(f"checksum mismatch {name}")
    out={}
    with zipfile.ZipFile(p) as z:
        fn=next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(fn) as raw:
            for row in csv.reader(io.TextIOWrapper(raw,encoding="utf-8")):
                if len(row)<7:continue
                try:
                    ts=int(row[0]); ts=ts//1000 if ts>10**14 else ts
                    out[ts//3600000]=(float(row[1]),float(row[4]))
                except (ValueError,IndexError):pass
    return out,h

def corr(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float)
    ok=np.isfinite(a)&np.isfinite(b)
    if ok.sum()<30:return None
    a=a[ok];b=b[ok]
    if np.std(a)==0 or np.std(b)==0:return None
    return float(np.corrcoef(a,b)[0,1])

def block_ci(x,seed=44044,reps=2000,block=24):
    x=np.asarray([v for v in x if np.isfinite(v)],float)
    if len(x)<100:return [None,None]
    rng=np.random.default_rng(seed); n=len(x); vals=[]
    for _ in range(reps):
        ids=[]
        while len(ids)<n:
            s=int(rng.integers(0,n))
            ids.extend((s+j)%n for j in range(block))
        vals.append(float(np.mean(x[np.array(ids[:n])])))
    return [float(np.quantile(vals,.025)),float(np.quantile(vals,.975))]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",default="2023-01");ap.add_argument("--end",default="2026-10")
    ap.add_argument("--out",default="exp044_results.json");ap.add_argument("--data",default="exp044-data")
    a=ap.parse_args(); root=Path(a.data); root.mkdir(parents=True,exist_ok=True)
    months_list=list(months(a.start,a.end)); prices={s:{} for s in SYMBOLS}; hashes={}
    for s in SYMBOLS:
        for m in months_list:
            bars,digest=load_month(s,m,root); prices[s].update(bars); hashes[f"{s}:{m}"]=digest
        print(f"loaded {s}: {len(prices[s])} hourly bars",flush=True)
    common=sorted(set.intersection(*(set(prices[s]) for s in SYMBOLS)))
    if len(common)<10000:raise RuntimeError(f"too few aligned hours: {len(common)}")
    close=np.array([[prices[s][t][1] for s in SYMBOLS] for t in common],float)
    if not np.all(close>0):raise RuntimeError("nonpositive close")
    ret=np.full_like(close,np.nan); ret[1:]=np.log(close[1:]/close[:-1])
    # Use t-1 completed-hour returns to forecast returns beginning at t.
    # Cross-sectional peer mean excludes target; BTC is a separate predeclared leader.
    peer=np.empty_like(ret)
    for j in range(len(SYMBOLS)):peer[:,j]=np.nanmean(np.delete(ret,j,axis=1),axis=1)
    results={"method":"At timestamp t, use fully completed return ending t-1 to predict t..t+h-1 return. Monthly Binance Vision USD-M 1h klines; strict 13-symbol timestamp intersection; all archives SHA256 checked.",
      "period_utc":[datetime.fromtimestamp(common[0]*3600,timezone.utc).isoformat(),datetime.fromtimestamp(common[-1]*3600,timezone.utc).isoformat()],
      "symbols":SYMBOLS,"aligned_hours":len(common),"archives_verified":len(hashes),"sha256":hashes,
      "splits":{},"limitations":["Static 13-symbol universe; survivorship bias.","Hourly bars cannot resolve sub-hour lead-lag effects.","Predictive screen only; no funding-adjusted regression or account portfolio simulation yet.","Common-time intersection discards hours missing for any symbol."]}
    n=len(common); tr=int(n*.5); va=int(n*.7)
    for split,lo,hi in [("train",1,tr),("validation",tr,va),("oos",va,n-24)]:
        sp={}
        for h in (1,4,24):
            # cross-sectional IC at each timestamp; own-lag and BTC lag benchmarks.
            ics_peer=[];ics_btc=[];ics_own=[]; dates=[]
            pooled_peer=[];pooled_btc=[];pooled_own=[];pooled_y=[]
            for t in range(lo,hi-h):
                y=np.log(close[t+h]/close[t])
                xpeer=peer[t-1]; xbtc=np.repeat(ret[t-1,0],len(SYMBOLS)); xown=ret[t-1]
                c1=corr(xpeer,y); c2=corr(xbtc,y); c3=corr(xown,y)
                if c1 is not None:ics_peer.append(c1);dates.append(t)
                if c2 is not None:ics_btc.append(c2)
                if c3 is not None:ics_own.append(c3)
                pooled_peer.extend(xpeer.tolist());pooled_btc.extend(xbtc.tolist());pooled_own.extend(xown.tolist());pooled_y.extend(y.tolist())
            sp[str(h)]={"n_timestamps":len(ics_peer),
              "peer_ex_target_mean_cs_ic":float(np.mean(ics_peer)) if ics_peer else None,
              "peer_ex_target_median_cs_ic":float(np.median(ics_peer)) if ics_peer else None,
              "peer_ic_95pct_block_ci":block_ci(ics_peer),
              "btc_lag_mean_cs_ic":float(np.mean(ics_btc)) if ics_btc else None,
              "own_lag_mean_cs_ic":float(np.mean(ics_own)) if ics_own else None,
              "pooled_peer_predictor_corr":corr(pooled_peer,pooled_y),
              "pooled_btc_predictor_corr":corr(pooled_btc,pooled_y),
              "pooled_own_predictor_corr":corr(pooled_own,pooled_y)}
        results["splits"][split]=sp
    # Per-target OOS correlations; evaluate breadth not just aggregate.
    target={}
    for j,s in enumerate(SYMBOLS):
        target[s]={}
        for h in (1,4,24):
            lo=va; hi=n-h
            x=peer[lo-1:hi-1,j]; y=np.log(close[lo+h:hi+h,j]/close[lo:hi,j])
            target[s][str(h)]={"peer_lag_oos_corr":corr(x,y)}
    results["target_oos"]=target
    Path(a.out).write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in results.items() if k!="sha256"},indent=2),flush=True)
if __name__=="__main__":main()
