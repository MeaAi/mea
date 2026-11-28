#!/usr/bin/env python3
import argparse,csv,hashlib,io,json,time,urllib.request,zipfile
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from sklearn.linear_model import LinearRegression,Lasso
from sklearn.model_selection import GridSearchCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
BASE="https://data.binance.vision/data/futures/um/monthly"; H=3600000; D=24*H
S=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","SOLUSDT","LINKUSDT","LTCUSDT","BCHUSDT","DOTUSDT","TRXUSDT","AVAXUSDT"]
L=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","LTCUSDT"]; F=["ADAUSDT","DOGEUSDT","SOLUSDT","LINKUSDT","BCHUSDT","DOTUSDT","TRXUSDT","AVAXUSDT"]
def months(a,b):
 y,m=map(int,a.split("-"));Y,M=map(int,b.split("-"))
 while (y,m)<=(Y,M):
  yield f"{y:04d}-{m:02d}";m+=1
  if m==13:y,m=y+1,1
def get(url,p):
 if p.exists() and p.stat().st_size:return
 p.parent.mkdir(parents=True,exist_ok=True);err=None
 for q in range(4):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=120) as r,p.open("wb") as f:
    while z:=r.read(1<<20):f.write(z)
   return
  except Exception as e:err=str(e);p.unlink(missing_ok=True);time.sleep(2**q)
 raise RuntimeError(url+" "+str(err))
def load(s,ms,root):
 mark={};fund={};qa={}
 for mo in ms:
  for kind,folder in [("m","markPriceKlines"),("f","fundingRate")]:
   fn=f"{s}-1h-{mo}.zip" if kind=="m" else f"{s}-fundingRate-{mo}.zip"
   url=f"{BASE}/{folder}/{s}/"+(f"1h/{fn}" if kind=="m" else fn);p=root/s/kind/fn;get(url,p)
   with zipfile.ZipFile(p) as z:
    if z.testzip():raise RuntimeError("ZIP CRC "+str(p))
    raw=z.read(next(x for x in z.namelist() if x.endswith(".csv")))
   qa[kind+mo]=hashlib.sha256(p.read_bytes()).hexdigest()
   for row in csv.reader(io.TextIOWrapper(io.BytesIO(raw),encoding="utf-8-sig")):
    try:
     t=int(float(row[0]));t=t//1000 if t>10**14 else t
     if kind=="m":
      c=float(row[4])
      if c>0:mark[t//H]=c
     else:fund[t]=float(row[2])
    except (ValueError,IndexError):pass
 return s,mark,fund,qa
def fit(x,y,lasso=False):
 if lasso:
  m=GridSearchCV(make_pipeline(StandardScaler(),Lasso(max_iter=30000)),{"lasso__alpha":np.logspace(-7,1,60)},cv=TimeSeriesSplit(n_splits=5),scoring="neg_mean_squared_error",n_jobs=-1,refit=True)
 else:m=LinearRegression()
 return m.fit(x,y)
def r2(y,p):return float(1-np.sum((y-p)**2)/np.sum(y*y))
def boot_ci(num,den,seed,reps=1200,block=24):
 n=len(num);rng=np.random.default_rng(seed);v=[]
 for _ in range(reps):
  ix=[]
  while len(ix)<n:
   st=int(rng.integers(n));ix.extend((st+q)%n for q in range(block))
  ix=np.asarray(ix[:n]);d=den[ix].sum()
  if d>0:v.append(num[ix].sum()/d)
 return [float(np.quantile(v,.025)),float(np.quantile(v,.975))]
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--start",default="2023-01");ap.add_argument("--end",default="2026-10");ap.add_argument("--out",default="exp046_results.json");ap.add_argument("--data",default="exp046-data");a=ap.parse_args()
 root=Path(a.data);root.mkdir(parents=True,exist_ok=True);ms=list(months(a.start,a.end));loaded={};errors={}
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs={ex.submit(load,s,ms,root):s for s in S}
  for f in as_completed(fs):
   s=fs[f]
   try:loaded[s]=f.result()[1:];print("LOADED",s,len(loaded[s][0]),flush=True)
   except Exception as e:errors[s]=str(e);print("ERROR",s,str(e),flush=True)
 if len(loaded)!=len(S):raise RuntimeError("Incomplete universe "+json.dumps(errors))
 ts=sorted(set.intersection(*(set(loaded[s][0]) for s in S)));n=len(ts);ix={s:i for i,s in enumerate(S)}
 C=np.array([[loaded[s][0][t] for s in S] for t in ts]);R=np.full_like(C,np.nan);R[1:]=np.log(C[1:]/C[:-1])
 U=np.full_like(C,np.nan);fc={}
 for j,s in enumerate(S):
  ev=sorted(loaded[s][1]);et=np.array(ev,dtype=np.int64);v=np.array([loaded[s][1][t] for t in ev]);cs=np.r_[0.,np.cumsum(v)]
  for i,t in enumerate(ts):
   rr=np.searchsorted(et,t*H,"right");ll=np.searchsorted(et,t*H-7*D,"right")
   if rr-ll>=12:U[i,j]=cs[rr]-cs[ll]
  fc[s]={"events":len(ev),"valid_scores":int(np.isfinite(U[:,j]).sum())}
 b1=int(.5*n);b2=int(.7*n);end=n-5
 regime=np.full(n,"unknown",object)
 btc=np.full(n,np.nan);btc[721:]=C[720:-1,ix["BTCUSDT"]]/C[:-721,ix["BTCUSDT"]]-1
 regime[btc>=.05]="bull";regime[btc<=-.05]="bear";regime[(btc>-.05)&(btc<.05)]="sideways"
 out={"experiment":"EXP-046","symbols":S,"leaders":L,"followers":F,"common_hours":n,"start_utc":datetime.fromtimestamp(ts[0]*H/1000,timezone.utc).isoformat(),"end_utc":datetime.fromtimestamp(ts[-1]*H/1000,timezone.utc).isoformat(),"archive_sha256":{s:loaded[s][2] for s in S},"funding_qa":fc,"load_errors":errors,"split_indices":{"train":[0,b1],"validation":[b1,b2],"oos":[b2,end]},"horizons":{},"limitations":["Static 13-symbol universe survivorship bias","LTC is an available-universe proxy for EOS in the paper's historical leader set","Hourly predictive diagnostics are not executable trading results","No portfolio simulation; no final equity or drawdown"]}
 for h in (1,4):
  per={};ys=[];pb_all=[];pc_all=[];num_t=np.zeros((end-b2,len(F)));den_t=np.zeros_like(num_t);third=[]
  for fj,s in enumerate(F):
   j=ix[s];y=np.full(n,np.nan);y[h:]=np.log(C[h:,j]/C[:-h,j])
   own=np.r_[np.nan,R[:-1,j]];leaders=np.column_stack([np.r_[np.nan,R[:-1,ix[z]]] for z in L]);X=np.column_stack([own,U[:,j],leaders])
   valid=np.isfinite(y)&np.all(np.isfinite(X),axis=1);tr=np.where(valid&(np.arange(n)<b1))[0];va=np.where(valid&(np.arange(n)>=b1)&(np.arange(n)<b2))[0];te=np.where(valid&(np.arange(n)>=b2)&(np.arange(n)<end))[0]
   if len(tr)<3000 or len(te)<500:raise RuntimeError(f"Too few rows {s} train={len(tr)} oos={len(te)}")
   mb=fit(X[tr,:2],y[tr]);mc=fit(X[tr],y[tr],True);pb=mb.predict(X[te,:2]);pc=mc.predict(X[te])
   num=(y[te]-pb)**2-(y[te]-pc)**2;den=y[te]**2;loc=te-b2
   np.add.at(num_t[:,fj],loc,num);np.add.at(den_t[:,fj],loc,den)
   per[s]={"train_n":len(tr),"validation_n":len(va),"oos_n":len(te),"baseline_r2":r2(y[te],pb),"candidate_r2":r2(y[te],pc),"incremental_r2":float(num.sum()/den.sum()),"baseline_mse":float(np.mean((y[te]-pb)**2)),"candidate_mse":float(np.mean((y[te]-pc)**2)),"alpha":float(mc.best_params_["lasso__alpha"]),"leader_coefficients":{z:float(c) for z,c in zip(L,mc[-1].coef_[2:])}}
   ys.extend(y[te]);pb_all.extend(pb);pc_all.extend(pc)
   for q in range(3):
    lo=b2+q*(end-b2)//3;hi=b2+(q+1)*(end-b2)//3;kk=(te>=lo)&(te<hi)
    if kk.any():third.append({"follower":s,"third":q+1,"incremental_r2":float((np.sum((y[te[kk]]-pb[kk])**2)-np.sum((y[te[kk]]-pc[kk])**2))/np.sum(y[te[kk]]**2))})
  Y=np.array(ys);PB=np.array(pb_all);PC=np.array(pc_all);nt=num_t.sum(axis=1);dt=den_t.sum(axis=1)
  regimes={}
  for rg in ("bull","bear","sideways"):
   keep=np.array([regime[t]==rg for t in range(b2,end)])
   regimes[rg]={"timestamps":int(keep.sum()),"incremental_r2":float(num_t[keep].sum()/den_t[keep].sum()) if den_t[keep].sum()>0 else None}
  out["horizons"][str(h)]={"pooled":{"n":len(Y),"baseline_r2":r2(Y,PB),"candidate_r2":r2(Y,PC),"incremental_r2":float(nt.sum()/dt.sum()),"paired_24h_block_bootstrap_ci":boot_ci(nt,dt,46000+h)},"followers_lower_mse":sum(v["candidate_mse"]<v["baseline_mse"] for v in per.values()),"per_follower":per,"oos_thirds":third,"regimes":regimes}
 Path(a.out).write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2),flush=True)
if __name__=="__main__":main()
