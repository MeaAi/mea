#!/usr/bin/env python3
"""EXP-047: incremental spot/perpetual basis information beyond settled funding."""
import csv, hashlib, io, json, time, urllib.request, zipfile
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

BASE="https://data.binance.vision"
SYMBOLS=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","SOLUSDT","LINKUSDT","LTCUSDT","BCHUSDT","DOTUSDT","TRXUSDT","AVAXUSDT"]
H=3600000; WEEK=168; DAY=24
START="2023-01"; END="2026-10"
ROOT=Path("exp047-cache")

def months(a,b):
 y,m=map(int,a.split("-"));Y,M=map(int,b.split("-"))
 while (y,m)<=(Y,M):
  yield f"{y:04d}-{m:02d}";m+=1
  if m==13:y,m=y+1,1

def get(url,p):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.stat().st_size:return
 err=None
 for k in range(4):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"MEAFLOW research"}),timeout=120) as r,p.open("wb") as f:
    while True:
     b=r.read(1<<20)
     if not b:break
     f.write(b)
   return
  except Exception as e:err=str(e);p.unlink(missing_ok=True);time.sleep(2**k)
 raise RuntimeError(f"{url}: {err}")

def archive(rel):
 p=ROOT/rel
 url=BASE+"/"+rel
 get(url,p)
 cp=Path(str(p)+".CHECKSUM");get(url+".CHECKSUM",cp)
 expected=cp.read_text().strip().split()[0].lower()
 h=hashlib.sha256(p.read_bytes()).hexdigest()
 if h!=expected:raise RuntimeError("SHA256 mismatch "+rel)
 return p,h

def load_symbol(s,ms):
 spot={};perp={};fund={};hashes={}
 for mo in ms:
  for market,folder,target in [("spot",f"data/spot/monthly/klines/{s}/1h/{s}-1h-{mo}.zip",spot),
                               ("um",f"data/futures/um/monthly/klines/{s}/1h/{s}-1h-{mo}.zip",perp),
                               ("fund",f"data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{mo}.zip",fund)]:
   p,sha=archive(folder);hashes[folder]=sha
   with zipfile.ZipFile(p) as z:
    if z.testzip():raise RuntimeError("ZIP CRC error "+folder)
    raw=z.read(next(n for n in z.namelist() if n.lower().endswith(".csv")))
   for row in csv.reader(io.TextIOWrapper(io.BytesIO(raw),encoding="utf-8-sig")):
    try:
     t=int(float(row[0]))
     if t>=10**17:t//=10**6
     elif t>=10**14:t//=10**3
     if market=="fund":
      # funding archives: calc_time, funding_interval_hours, last_funding_rate or legacy timestamp,symbol,rate
      rate=float(row[2] if len(row)>2 else row[-1])
      fund[t//H]=rate
     else:
      close=float(row[4])
      if close>0:target[t//H]=close
    except (ValueError,IndexError,OverflowError):continue
 return s,spot,perp,fund,hashes

def fit_ols(X,y):
 # X and y already timestamp-demeaned; no intercept.
 return np.linalg.lstsq(X,y,rcond=None)[0]

def block_ci(values,seed=4707,reps=3000,block=4):
 x=np.asarray(values,float);x=x[np.isfinite(x)]
 if len(x)<20:return None
 rng=np.random.default_rng(seed);out=[];n=len(x)
 for _ in range(reps):
  idx=[]
  while len(idx)<n:
   st=int(rng.integers(n));idx.extend((st+np.arange(block))%n)
  out.append(float(np.mean(x[np.asarray(idx[:n])])))
 return [float(np.quantile(out,.025)),float(np.quantile(out,.975))]

def main():
 ms=list(months(START,END));loaded={};errors={}
 with ThreadPoolExecutor(max_workers=6) as ex:
  fs={ex.submit(load_symbol,s,ms):s for s in SYMBOLS}
  for f,s in fs.items():
   try:
    _,sp,pp,fu,hs=f.result();loaded[s]=(sp,pp,fu,hs)
    print("LOADED",s,len(sp),len(pp),len(fu),flush=True)
   except Exception as e:errors[s]=str(e);print("LOAD_ERROR",s,str(e),flush=True)
 if errors or len(loaded)!=len(SYMBOLS):raise RuntimeError("Incomplete universe; refusing partial-universe inference: "+json.dumps(errors))
 common=sorted(set.intersection(*(set(loaded[s][0])&set(loaded[s][1]) for s in SYMBOLS)))
 # weekly snapshots at 00:00 UTC; all inputs use the bar ending at that timestamp (open time t-1).
 snaps=[t for t in common if t%WEEK==0 and t-WEEK*2 in common and t+WEEK in common]
 if len(snaps)<100:raise RuntimeError("Too few weekly observations "+str(len(snaps)))
 feat_names=["basis_level","basis_chg_1d","basis_chg_3d","basis_chg_5d","basis_chg_7d"]
 rows=[]
 for t in snaps:
  vals=[]
  for s in SYMBOLS:
   sp,pp,fu,_=loaded[s]
   # close of last completed hourly candle at t-1; historical levels at t-k.
   def prem(tt):return 10000*(pp[tt]/sp[tt]-1) if tt in pp and tt in sp else np.nan
   basis=prem(t-1)
   changes=[basis-prem(t-1-d) for d in (DAY,3*DAY,5*DAY,7*DAY)]
   events=[v for tt,v in fu.items() if t-7*24 < tt <= t]
   funding=float(np.sum(events)) if len(events)>=12 else np.nan
   target=np.log(pp[t+WEEK]/pp[t]) if t+WEEK in pp and t in pp else np.nan
   vals.append([funding,basis,*changes,target])
  a=np.asarray(vals,float)
  if np.isfinite(a).all():rows.append((t,a))
 if len(rows)<100:raise RuntimeError("Too few complete cross-sections after alignment: "+str(len(rows)))
 n=len(rows);b1=int(.5*n);b2=int(.7*n)
 # Each cross-section is demeaned before pooling, removing common timestamp return shocks.
 Xfund=[];Xall={k:[] for k in feat_names};Y=[];dates=[]
 for t,a in rows:
  z=a-a.mean(axis=0,keepdims=True)
  Xfund.append(z[:,0:1]);Y.append(z[:,-1]);dates.append(t)
  for j,k in enumerate(feat_names):Xall[k].append(z[:,[0,j+1]])
 Xfund=np.asarray(Xfund);Y=np.asarray(Y);Xall={k:np.asarray(v) for k,v in Xall.items()}
 results={}
 for name,X in [("funding_only",Xfund)]+[(k,Xall[k]) for k in feat_names]:
  # Scale on training data only.
  scale=np.std(X[:b1].reshape(-1,X.shape[-1]),axis=0);scale[scale==0]=1
  Z=X/scale
  beta=fit_ols(Z[:b1].reshape(-1,Z.shape[-1]),Y[:b1].reshape(-1))
  pred=np.einsum("tsp,p->ts",Z[b2:],beta)
  yy=Y[b2:];num=np.mean((yy-pred)**2,axis=1);den=np.mean(yy**2,axis=1)
  r2=1-float(np.sum((yy-pred)**2)/np.sum(yy**2))
  results[name]={"oos_r2_vs_timestamp_mean":r2,"weekly_n":len(yy),"beta_scaled":beta.tolist(),"scale_train_only":scale.tolist(),"weekly_squared_error":num.tolist()}
 base=np.array(results["funding_only"]["weekly_squared_error"])
 for k in feat_names:
  cand=np.array(results[k]["weekly_squared_error"])
  delta=base-cand
  results[k]["incremental_mse_reduction_mean"]=float(delta.mean())
  results[k]["incremental_mse_reduction_95pct_block_ci"]=block_ci(delta)
 # regime and structural break diagnostics, based on BTC spot trailing 30d return at snapshot.
 regime_rows={}
 for t,a in rows[b2:]:
  btc=loaded["BTCUSDT"][0]
  old=t-30*DAY
  if t-1 not in btc or old not in btc:rg="warmup"
  else:
   rr=btc[t-1]/btc[old]-1
   rg="bull" if rr>.05 else "bear" if rr<-.05 else "sideways"
  regime_rows[str(t)]=rg
 out={"experiment":"EXP-047","status":"signal_screen_only_not_portfolio_backtest","period":{"start":datetime.fromtimestamp(dates[0]*H/1000,timezone.utc).isoformat(),"end":datetime.fromtimestamp(dates[-1]*H/1000,timezone.utc).isoformat()},"symbols":SYMBOLS,"weekly_observations":n,"split":{"train":b1,"validation":b2-b1,"oos":n-b2},"definition":"basis premium bp=10000*(USD-M perp close/spot close-1); completed hourly bars only","features":feat_names,"target":"next 7d perp log return; weekly non-overlapping observations","models":results,"oos_structural_break":{"pre_2025_09_18":sum(1 for t in dates[b2:] if t*H<1758182460000),"post_2025_09_18":sum(1 for t in dates[b2:] if t*H>=1758182460000)},"oos_regime_counts":{k:list(regime_rows.values()).count(k) for k in ("bull","bear","sideways","warmup")},"archive_sha256":{s:loaded[s][3] for s in SYMBOLS},"load_errors":errors,"limitations":["Fixed-universe survivorship bias","Panel OLS is a research diagnostic, not executable portfolio simulation","No final capital or account-level drawdown","Funding event archive schema and timestamp QA are mandatory before interpreting results","No explicit transaction-cost portfolio yet; second-stage portfolio is gated on this screen"]}
 Path("exp047_results.json").write_text(json.dumps(out,indent=2))
 print(json.dumps(out,indent=2),flush=True)
if __name__=="__main__":main()
