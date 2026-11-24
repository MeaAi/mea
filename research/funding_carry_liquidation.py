#!/usr/bin/env python3
"""Conservative liquidation-aware cross-sectional funding carry simulation.
Free Binance Vision markPriceKlines + fundingRate; no credentials or orders.
This is a portfolio-level approximation, not Binance's private liquidation engine.
"""
import argparse,bisect,csv,hashlib,io,json,math,time,urllib.request,zipfile
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed

BASE="https://data.binance.vision/data/futures/um/monthly"
DAY=86400000
LEVERS=(1.25,1.5,2.0,2.5,3.0)

def months_between(a,b):
 y,m=map(int,a.split("-")); ey,em=map(int,b.split("-"))
 while (y,m)<=(ey,em):
  yield f"{y:04d}-{m:02d}"; m+=1
  if m==13:y,m=y+1,1

def download(url,path):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and path.stat().st_size:return
 tmp=Path(str(path)+".part")
 for i in range(4):
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
   with urllib.request.urlopen(req,timeout=90) as r,tmp.open("wb") as f:
    while True:
     b=r.read(1<<20)
     if not b:break
     f.write(b)
   tmp.replace(path);return
  except Exception:
   tmp.unlink(missing_ok=True);time.sleep(2**i)
 raise RuntimeError("download failed: "+url)

def verified_download(url,path):
 download(url,path)
 chk=Path(str(path)+".CHECKSUM")
 try:
  download(url+".CHECKSUM",chk)
  expected=chk.read_text().strip().split()[0].lower()
  h=hashlib.sha256(path.read_bytes()).hexdigest()
  if h!=expected:path.unlink(missing_ok=True);raise RuntimeError("SHA256 mismatch "+path.name)
 except RuntimeError as e:
  if "SHA256 mismatch" in str(e):raise
  print("CHECKSUM_UNAVAILABLE; ZIP integrity will be checked:",path.name,flush=True)

def readzip(path,kind):
 z=zipfile.ZipFile(path)
 if z.testzip() is not None:raise RuntimeError("corrupt ZIP "+str(path))
 n=next(x for x in z.namelist() if x.endswith(".csv"))
 f=io.TextIOWrapper(z.open(n),encoding="utf-8-sig",newline="")
 out={}
 for row in csv.reader(f):
  try:
   t=int(float(row[0]))
   if kind=="mark":
    vals=tuple(float(row[i]) for i in (1,2,3,4))
    if all(math.isfinite(x) and x>0 for x in vals):out[t]=vals
   else:
    rate=float(row[2])
    if math.isfinite(rate):out[t]=rate
  except (ValueError,IndexError):pass
 f.close();z.close();return out

def load_symbol(sym,months,root):
 fund={};marks={}
 for mo in months:
  fn=f"{sym}-fundingRate-{mo}.zip"
  fp=root/"cache"/sym/"funding"/fn
  verified_download(f"{BASE}/fundingRate/{sym}/{fn}",fp);fund.update(readzip(fp,"fund"))
  mn=f"{sym}-1h-{mo}.zip"
  mp=root/"cache"/sym/"mark"/mn
  verified_download(f"{BASE}/markPriceKlines/{sym}/1h/{mn}",mp);marks.update(readzip(mp,"mark"))
 return sym,fund,marks

def run(data,period,lev,fee_bp,slip_bp=2,mmr=.005,liq_fee=.01):
 symbols=list(data); first,last=period
 mark_times={s:sorted(data[s]["marks"]) for s in symbols}
 all_events=sorted(set(t for s in symbols for t in data[s]["fund"] if first<=t<=last))
 events=[t for t in all_events if sum(t in data[s]["fund"] and t in data[s]["marks"] for s in symbols)>=math.ceil(.8*len(symbols))]
 if len(events)<100:raise RuntimeError("insufficient aligned funding events")
 equity=100.; peak=100.; maxdd=0.; qty={s:0. for s in symbols}; prev={}; last_rebal=None
 fee_total=slip_total=price_pnl=funding_pnl=0.; liquidated=False; liq_time=None; liq_equity=None
 rebalances=0; hourly_checks=0
 lookback=7*DAY; interval=7*DAY
 for ix,t in enumerate(events):
  # Walk the union of hourly mark candles once; update portfolio equity close-to-close.
  current=prev.copy()
  if ix and current:
   start=events[ix-1]
   for ht in range(start,t,3600000):
    worst=equity;notion=0.
    for z in symbols:
     q=qty[z]
     bar=data[z]["marks"].get(ht)
     if not q or z not in current or bar is None:continue
     o,h,l,cl=bar;adverse=l if q>0 else h
     worst+=q*(adverse-current[z]);notion+=abs(q*adverse)
    hourly_checks+=1
    if worst<=notion*(mmr+liq_fee):
     equity=max(0.,worst-notion*liq_fee);liquidated=True
     liq_time=datetime.fromtimestamp(ht/1000,timezone.utc).isoformat();liq_equity=equity
     break
    step=0.
    for z in symbols:
     q=qty[z];bar=data[z]["marks"].get(ht)
     if q and z in current and bar is not None:
      cl=bar[3];step+=q*(cl-current[z]);current[z]=cl
    equity+=step;price_pnl+=step
   if liquidated:break
  px={}
  for s in symbols:
   if s in current:px[s]=current[s]
   else:
    j=bisect.bisect_left(mark_times[s],t)-1
    if j>=0:px[s]=data[s]["marks"][mark_times[s][j]][3]
  rates={s:data[s]["fund"][t] for s in symbols if t in data[s]["fund"]}
  # Funding cashflow for positions held across this settlement.
  fpnl=sum(-qty[s]*px[s]*rates[s] for s in symbols if qty[s] and s in px and s in rates)
  equity+=fpnl;funding_pnl+=fpnl
  if equity<=0:liquidated=True;liq_time=datetime.fromtimestamp(t/1000,timezone.utc).isoformat();liq_equity=0.;equity=0.;break
  if last_rebal is None and t>=first+lookback or last_rebal is not None and t-last_rebal>=interval:
   scores={}
   for s in symbols:
    vals=[r for et,r in data[s]["fund"].items() if t-lookback<et<=t]
    if len(vals)>=12 and s in px:scores[s]=sum(vals)
   ordered=sorted(scores,key=scores.get);k=max(1,int(len(ordered)*.2))
   if len(ordered)>=2*k:
    longs=ordered[:k];shorts=ordered[-k:];target={s:0. for s in symbols}
    leg=max(0.,equity)*lev*.5
    for s in longs:target[s]=leg/k/px[s]
    for s in shorts:target[s]=-leg/k/px[s]
    turnover=sum(abs((target[s]-qty[s])*px[s]) for s in symbols if s in px)
    fee=turnover*fee_bp/10000;slip=turnover*slip_bp/10000
    equity-=fee+slip;fee_total+=fee;slip_total+=slip;qty=target;last_rebal=t;rebalances+=1
  # Save latest event mark as anchor for next interval.
  prev=px.copy()
  peak=max(peak,equity);maxdd=min(maxdd,(equity/peak-1)*100 if peak else -100)
  if equity<=0:liquidated=True;equity=0.;break
 gross=sum(abs(qty[s]*prev.get(s,0)) for s in symbols)
 return {"leverage":lev,"fee_bp_one_way":fee_bp,"slippage_bp_one_way":slip_bp,
  "maintenance_margin_rate_assumption":mmr,"liquidation_fee_assumption":liq_fee,
  "start_equity_usdt":100.,"end_equity_usdt":round(equity,6),
  "net_return_pct":round((equity/100-1)*100,4),"max_drawdown_pct":round(maxdd,4),
  "liquidated":liquidated,"liquidation_time_utc":liq_time,"equity_at_liquidation_usdt":liq_equity,
  "price_pnl_usdt":round(price_pnl,6),"funding_pnl_usdt":round(funding_pnl,6),
  "trading_fees_usdt":round(fee_total,6),"slippage_usdt":round(slip_total,6),
  "rebalance_count":rebalances,"hourly_adverse_checks":hourly_checks,
  "model_note":"Cross-portfolio conservative hourly OHLC stress approximation; not exact Binance liquidation engine. Uses simultaneous adverse extremes and static 0.5% MMR assumption."}

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--start",default="2023-01");ap.add_argument("--end",default="2026-10")
 ap.add_argument("--symbols",default="BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT")
 ap.add_argument("--out",default="research-results/funding_carry_liquidation.json")
 a=ap.parse_args();months=list(months_between(a.start,a.end));symbols=a.symbols.split(",")
 root=Path("research-output");data={};errors={}
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs={ex.submit(load_symbol,s,months,root):s for s in symbols}
  for f in as_completed(fs):
   s=fs[f]
   try:
    _,fund,marks=f.result();data[s]={"fund":fund,"marks":marks}
    print(s,"funding",len(fund),"mark_bars",len(marks),flush=True)
   except Exception as e:errors[s]=str(e);print("SKIP",s,e,flush=True)
 if len(data)<8:raise RuntimeError("Fewer than 8 usable symbols: "+str(errors))
 times=sorted(t for s in data for t in data[s]["fund"] if sum(t in data[z]["fund"] for z in data)>=math.ceil(.8*len(data)))
 first,last=times[0],times[-1];span=last-first
 cuts={"train":(first+7*DAY,first+int(span*.5)),"validation":(first+int(span*.5),first+int(span*.7)),"oos":(first+int(span*.7),last)}
 results={}
 for name,period in cuts.items():
  results[name]={}
  for lev in LEVERS:
   results[name][f"{lev:g}x"]={}
   for fee in (2,5,8):
    v=run(data,period,lev,fee,slip_bp=2)
    results[name][f"{lev:g}x"][f"fee_{fee}bp"]=v
    print("RESULT",name,lev,fee,json.dumps(v,separators=(",",":")),flush=True)
 report={"strategy":"7d trailing funding rank, weekly rebalance, lowest 20% long/highest 20% short",
  "source":"Free official Binance Vision monthly fundingRate + 1h markPriceKlines",
  "period_utc":{"first":datetime.fromtimestamp(first/1000,timezone.utc).isoformat(),"last":datetime.fromtimestamp(last/1000,timezone.utc).isoformat()},
  "universe":list(data),"data_errors":errors,"capital_usdt":100,
  "splits":"chronological 50/20/30; fixed strategy; no OOS tuning",
  "assumptions":{"slippage":"2 bp one-way on rebalance turnover, in addition to 2/5/8 bp fee sensitivity",
   "maintenance_margin":"static conservative 0.5% of stressed gross notional; historical symbol-specific Binance brackets unavailable in this public dataset",
   "liquidation_fee":"1% of stressed gross notional proxy",
   "intrabar":"1h mark-price OHLC; simultaneous adverse low for longs and high for shorts, conservative but not tick-accurate",
   "margin_mode":"cross-portfolio approximation; funding cashflow at settlement; positions resized weekly",
   "limitations":["not exact Binance liquidation engine","static MMR instead of historical symbol-specific tier brackets","hourly OHLC cannot reconstruct tick order or exact liquidation price","spread and market impact beyond fixed slippage are not modeled","static universe survivorship bias"]},
  "results":results}
 Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(report,indent=2),encoding="utf-8")
 print("REPORT",a.out,flush=True)
if __name__=="__main__":main()
