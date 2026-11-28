#!/usr/bin/env python3
"""EXP-045 funding-conditioned cross-crypto lead-lag diagnostic."""
import argparse, csv, hashlib, io, json, time, urllib.request, zipfile
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

BASE="https://data.binance.vision/data/futures/um/monthly"
SYMBOLS=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","SOLUSDT","LINKUSDT","LTCUSDT","BCHUSDT","DOTUSDT","TRXUSDT","AVAXUSDT"]
HOUR=3600000
DAY=24*HOUR

def months(start,end):
 y,m=map(int,start.split("-")); ey,em=map(int,end.split("-"))
 while (y,m)<=(ey,em):
  yield f"{y:04d}-{m:02d}"; m+=1
  if m==13:y,m=y+1,1

def fetch(url,path):
 if path.exists() and path.stat().st_size:return
 path.parent.mkdir(parents=True,exist_ok=True); err=None
 for k in range(4):
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
   with urllib.request.urlopen(req,timeout=120) as r,path.open("wb") as f:
    while True:
     b=r.read(1<<20)
     if not b:break
     f.write(b)
   return
  except Exception as e:
   err=str(e); path.unlink(missing_ok=True); time.sleep(2**k)
 raise RuntimeError(f"{url}: {err}")

def archive(url,path,strict=True):
 fetch(url,path)
 with zipfile.ZipFile(path) as z:
  if z.testzip() is not None: raise RuntimeError("ZIP CRC failure: "+str(path))
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 cp=Path(str(path)+".CHECKSUM")
 try:
  fetch(url+".CHECKSUM",cp); expected=cp.read_text().strip().split()[0].lower()
  if digest!=expected: raise RuntimeError("SHA256 mismatch: "+str(path))
  status="sha256_verified"
 except Exception as e:
  if strict: raise
  status="zip_crc_only:"+str(e)
 return digest,status

def load_symbol(sym,moons,root):
 marks={}; funding={}; hashes={}; qa={}
 for mo in moons:
  for kind,folder in [("mark","markPriceKlines"),("fund","fundingRate")]:
   fn=f"{sym}-1h-{mo}.zip" if kind=="mark" else f"{sym}-fundingRate-{mo}.zip"
   url=f"{BASE}/{folder}/{sym}/"+(f"1h/{fn}" if kind=="mark" else fn)
   p=root/"cache"/sym/kind/fn
   digest,status=archive(url,p,strict=False); hashes[f"{sym}:{kind}:{mo}"]=digest; qa[f"{sym}:{kind}:{mo}"]=status
   with zipfile.ZipFile(p) as z:
    name=next(n for n in z.namelist() if n.endswith(".csv"))
    with z.open(name) as raw:
     for row in csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig")):
      try:
       ts=int(float(row[0])); ts=ts//1000 if ts>10**14 else ts
       if kind=="mark":
        # markPriceKlines OHLC: open, high, low, close
        vals=tuple(float(row[i]) for i in (1,2,3,4))
        if all(np.isfinite(v) and v>0 for v in vals): marks[ts//HOUR]=vals
       else:
        rate=float(row[2])
        if np.isfinite(rate): funding[ts]=rate
      except (ValueError,IndexError): pass
 return sym,marks,funding,hashes,qa

def ols_fit_predict(xtr,ytr,xte):
 # Intercept plus ridge-free least squares; predictors are standardized on train.
 mu=xtr.mean(axis=0); sd=xtr.std(axis=0); sd[sd<1e-12]=1.
 a=(xtr-mu)/sd; b=(xte-mu)/sd
 a=np.column_stack([np.ones(len(a)),a]); b=np.column_stack([np.ones(len(b)),b])
 beta=np.linalg.lstsq(a,ytr,rcond=None)[0]
 return b@beta,beta,mu,sd

def block_ci(improvement, total_variation, seed, reps=1500, block=24):
 # Paired moving-block bootstrap of the OOS incremental R2 ratio.
 # Resample timestamp rows and recompute sum(error improvement)/sum(y^2)
 # within each draw; this avoids scaling a mean CI by an approximate sample count.
 x=np.asarray(improvement,float); d=np.asarray(total_variation,float); n=len(x)
 if n<200:return [None,None]
 rng=np.random.default_rng(seed); out=[]
 for _ in range(reps):
  ids=[]
  while len(ids)<n:
   s=int(rng.integers(0,n)); ids.extend((s+j)%n for j in range(block))
  ix=np.asarray(ids[:n]); num=float(np.nansum(x[ix])); den=float(np.nansum(d[ix]))
  if den>0: out.append(num/den)
 if len(out)<reps*.9:return [None,None]
 return [float(np.quantile(out,.025)),float(np.quantile(out,.975))]

def metrics(y,p1,p2):
 mask=np.isfinite(y)&np.isfinite(p1)&np.isfinite(p2)
 yy=y[mask]; a=p1[mask]; b=p2[mask]
 if len(yy)==0:return {}
 sst=float(np.sum(yy**2))
 e1=(yy-a)**2; e2=(yy-b)**2
 r1=1-float(e1.sum())/sst if sst else None
 r2=1-float(e2.sum())/sst if sst else None
 return {"n_asset_hours":int(mask.sum()),"m1_oos_r2":r1,"m2_oos_r2":r2,
         "incremental_oos_r2":(r2-r1) if r1 is not None and r2 is not None else None,
         "m1_mse":float(e1.mean()),"m2_mse":float(e2.mean())}

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--start",default="2023-01");ap.add_argument("--end",default="2026-10")
 ap.add_argument("--out",default="exp045_results.json");ap.add_argument("--data",default="exp045-data")
 a=ap.parse_args(); out_path=a.out; data_path=a.data; root=Path(data_path); root.mkdir(parents=True,exist_ok=True)
 ms=list(months(a.start,a.end)); loaded={}; errors={}
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs={ex.submit(load_symbol,s,ms,root):s for s in SYMBOLS}
  for f in as_completed(fs):
   s=fs[f]
   try:
    z=f.result(); loaded[s]=z[1:]; print("LOADED",s,len(z[1]),len(z[2]),flush=True)
   except Exception as e: errors[s]=str(e); print("ERROR",s,str(e),flush=True)
 if len(loaded)!=len(SYMBOLS): raise RuntimeError("All 13 symbols required for strict paired panel: "+json.dumps(errors))
 # Strict intersection across 13 mark-price hourly bars.
 common=sorted(set.intersection(*(set(loaded[s][0]) for s in SYMBOLS)))
 if len(common)<10000: raise RuntimeError("Insufficient common hourly bars")
 close=np.array([[loaded[s][0][t][3] for s in SYMBOLS] for t in common],float)
 if not np.all(np.isfinite(close)) or np.any(close<=0):raise RuntimeError("Invalid aligned mark prices")
 n,k=close.shape; ret=np.full((n,k),np.nan); ret[1:]=np.log(close[1:]/close[:-1])
 # Peer return excludes target. Market lag is absorbed by timestamp fixed effects;
 # cross-sectional demeaning implements those time effects without a singular market regressor.
 peer=np.empty_like(ret)
 for j in range(k): peer[:,j]=np.nanmean(np.delete(ret,j,axis=1),axis=1)
 # funding score at hourly timestamp: sum of all settled events in (t-7d,t].
 fundscore=np.full((n,k),np.nan); fund_counts={}
 for j,s in enumerate(SYMBOLS):
  f=loaded[s][1]; events=sorted(f); vals=np.array([f[t] for t in events],float)
  pref=np.concatenate([[0.],np.cumsum(vals)])
  ts=np.asarray(events,dtype=np.int64)
  for i,t in enumerate(common):
   right=np.searchsorted(ts,t*HOUR,side="right")
   left=np.searchsorted(ts,t*HOUR-7*DAY,side="right")
   if right-left>=12: fundscore[i,j]=pref[right]-pref[left]
  fund_counts[s]={"funding_events":len(events),"valid_7d_scores":int(np.isfinite(fundscore[:,j]).sum())}
 # Outcome t..t+h-1; predictors from completed bar ending t-1.
 splits={"train":(1,int(n*.5)),"validation":(int(n*.5),int(n*.7)),"oos":(int(n*.7),n-24)}
 ooslo,ooshi=splits["oos"]; edges=np.linspace(ooslo,ooshi,4,dtype=int)
 btc30=np.full(n,np.nan); btc30[720:]=close[720:,0]/close[:-720,0]-1
 output={"experiment":"EXP-045","symbols":SYMBOLS,"period_utc":[datetime.fromtimestamp(common[0]*HOUR/1000,timezone.utc).isoformat(),datetime.fromtimestamp(common[-1]*HOUR/1000,timezone.utc).isoformat()],
 "aligned_hours":n,"archives":sum(len(v[2]) for v in loaded.values()),"archive_qa":{s:loaded[s][3] for s in SYMBOLS},"funding_counts":fund_counts,"load_errors":errors,
 "model_note":"Per-timestamp cross-sectional demeaning is equivalent to timestamp fixed effects. Therefore common market lag is absorbed by time effects and is not separately estimated; own lag, 7d funding score and peer-ex-target lag are demeaned predictors. M0=own lag; M1=own lag+funding; M2=M1+peer lag.",
 "splits":{},"oos_subperiods":{},"oos_regimes":{},"per_symbol":{},"limitations":["Funding archives with missing SHA256 sidecar are recorded as ZIP-CRC-only; no silent claim of SHA256 verification.","Static 13-symbol universe has survivorship bias.","Predictive panel screen only; no portfolio simulation, final equity or drawdown.","Hourly data cannot identify sub-hour lead-lag.","Timestamp fixed effects absorb the market-wide lag return."]}
 # Precompute valid timestamp rows for each horizon and run pooled panel OLS.
 for h in (1,4):
  Y=np.full((n,k),np.nan); Y[h:]=np.log(close[h:]/close[:-h])
  Xown=np.full((n,k),np.nan); Xfund=fundscore.copy(); Xpeer=peer.copy()
  Xown[1:]=ret[:-1]
  # Peer signal must use only the last fully completed bar (t-1), exactly
  # matching own-lag timing. Using peer[t] would leak the outcome interval
  # for h=1 and mechanically produce beta=-12 after cross-sectional demeaning.
  Xpeer[1:]=peer[:-1]
  # demean cross-section at each timestamp; no look-ahead.
  def demean(mat):
   out=mat.copy()
   for ii in range(n):
    row=out[ii]; good=np.isfinite(row)
    if good.sum()>=8: row[good]-=row[good].mean()
    else: row[:]=np.nan
   return out
  yd=demean(Y); own=demean(Xown); fs=demean(Xfund); pr=demean(Xpeer)
  # split indices refer to forecast timestamp t; training/validation are strictly earlier.
  def build(lo,hi):
   rows=[]; yy=[]; syms=[]; times=[]
   for ti in range(max(1,lo),min(hi,n-h)):
    for j in range(k):
     vals=[yd[ti,j],own[ti,j],fs[ti,j],pr[ti,j]]
     if all(np.isfinite(vals)):
      rows.append(vals[1:]); yy.append(vals[0]); syms.append(j); times.append(ti)
   return np.asarray(rows,float),np.asarray(yy,float),np.asarray(syms,int),np.asarray(times,int)
  xtr,ytr,_,_=build(*splits["train"])
  xva,yva,_,_=build(*splits["validation"])
  # Fixed train-only fits. Validation is reported separately; no OOS tuning.
  m1tr=np.column_stack([xtr[:,0],xtr[:,1]])
  m2tr=np.column_stack([xtr[:,0],xtr[:,1],xtr[:,2]])
  xte,yte,ste,tte=build(*splits["oos"])
  m1te=np.column_stack([xte[:,0],xte[:,1]])
  m2te=np.column_stack([xte[:,0],xte[:,1],xte[:,2]])
  p1,b1,_,_=ols_fit_predict(m1tr,ytr,m1te)
  p2,b2,_,_=ols_fit_predict(m2tr,ytr,m2te)
  # Build timestamp x symbol residual-improvement matrix for paired block bootstrap.
  dmat=np.full((n,k),np.nan); vmat=np.full((n,k),np.nan)
  for q,(ti,j) in enumerate(zip(tte,ste)):
   dmat[ti,j]=((yte[q]-p1[q])**2-(yte[q]-p2[q])**2)
   vmat[ti,j]=yte[q]**2
  ci=block_ci(dmat,vmat,45000+h)
  met=metrics(yte,p1,p2)
  met.update({"horizon_hours":h,"m1_coefficients_standardized":b1.tolist(),"m2_coefficients_standardized":b2.tolist(),
              "peer_beta_standardized":float(b2[-1]),"incremental_oos_r2_95pct_block_ci":ci,
              "train_asset_hours":len(ytr),"validation_asset_hours":len(yva),"oos_timestamps":len(set(tte))})
  output["splits"][str(h)]=met
  # Subperiod diagnostics use fixed train coefficients, no refit.
  sub=[]
  for q in range(3):
   lo,hi=int(edges[q]),int(edges[q+1]); xx,yy,ss,tt=build(lo,hi)
   if len(yy):
    a=np.column_stack([xx[:,0],xx[:,1]]); b=np.column_stack([xx[:,0],xx[:,1],xx[:,2]])
    pa=ols_fit_predict(m1tr,ytr,a)[0]; pb=ols_fit_predict(m2tr,ytr,b)[0]
    mm=metrics(yy,pa,pb); mm.update({"start_utc":datetime.fromtimestamp(common[lo]*HOUR/1000,timezone.utc).isoformat(),"end_utc":datetime.fromtimestamp(common[hi-1]*HOUR/1000,timezone.utc).isoformat()})
   else:mm={}
   sub.append(mm)
  output["oos_subperiods"][str(h)]=sub
  # Regime performance; predictions remain train-fitted.
  regout={}
  for rg,maskreg in [("bull",btc30>=.05),("bear",btc30<=-.05),("sideways",(btc30>-.05)&(btc30<.05))]:
   keep=np.array([maskreg[t] for t in tte])
   regout[rg]=metrics(yte[keep],p1[keep],p2[keep]) if keep.any() else {}
  output["oos_regimes"][str(h)]=regout
  # Train-only per-symbol peer slopes, controlling for own lag and funding.
  # These slopes are estimated without using OOS outcomes; OOS gain is reported separately.
  ps={}; positive_beta_symbols=0
  for j,s in enumerate(SYMBOLS):
   # Rebuild the training rows with symbol IDs to avoid leaking OOS information.
   tx,ty,tsym,ttm=build(*splits["train"])
   ixtr=np.where(tsym==j)[0]; beta_peer=None
   if len(ixtr)>=100:
    base=np.column_stack([tx[ixtr,0],tx[ixtr,1]])
    peer_col=tx[ixtr,2]
    base=np.column_stack([np.ones(len(base)),base])
    resid_peer=peer_col-base@np.linalg.lstsq(base,peer_col,rcond=None)[0]
    resid_y=ty[ixtr]-base@np.linalg.lstsq(base,ty[ixtr],rcond=None)[0]
    den=float(resid_peer@resid_peer)
    if den>1e-12: beta_peer=float((resid_peer@resid_y)/den)
   ix=np.where(ste==j)[0]
   if len(ix):
    mm=metrics(yte[ix],p1[ix],p2[ix]); mm["n_oos"]=len(ix)
    mm["train_only_peer_beta_raw"]=beta_peer
    mm["train_only_peer_beta_positive"]=bool(beta_peer is not None and beta_peer>0)
    if beta_peer is not None and beta_peer>0: positive_beta_symbols+=1
    ps[s]=mm
  output["per_symbol"][str(h)]={"positive_train_peer_beta_symbols":positive_beta_symbols,
                                  "peer_beta_positive_gate_required":9,
                                  "symbols":ps}
 Path(out_path).write_text(json.dumps(output,indent=2),encoding="utf-8")
 print(json.dumps({k:v for k,v in output.items() if k!="archive_qa"},indent=2),flush=True)
if __name__=="__main__":main()
