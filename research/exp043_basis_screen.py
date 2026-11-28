#!/usr/bin/env python3
"""EXP-043: point-in-time spot/perpetual basis predictive screen. Public data only."""
from __future__ import annotations
import csv, hashlib, io, json, math, time, urllib.request, zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

SYMBOLS = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","SOLUSDT","LINKUSDT","LTCUSDT","BCHUSDT","DOTUSDT","TRXUSDT","AVAXUSDT"]
START, END = "2023-01", "2026-10"
ROOT = Path("research-output/exp043-cache")
BASE = "https://data.binance.vision"

def months(a,b):
    y,m=map(int,a.split("-")); ey,em=map(int,b.split("-"))
    while (y,m)<=(ey,em):
        yield f"{y:04d}-{m:02d}"
        m+=1
        if m==13: y,m=y+1,1

def get(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size: return
    tmp=path.with_suffix(path.suffix+".part")
    err=None
    for n in range(4):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"MEAFLOW research"})
            with urllib.request.urlopen(req,timeout=90) as r,tmp.open("wb") as f:
                while True:
                    b=r.read(1024*1024)
                    if not b: break
                    f.write(b)
            tmp.replace(path); return
        except Exception as e:
            err=str(e); tmp.unlink(missing_ok=True); time.sleep(2**n)
    raise RuntimeError(f"{url}: {err}")

def archive(market,symbol,month):
    if market=="spot":
        rel=f"data/spot/monthly/klines/{symbol}/1h/{symbol}-1h-{month}.zip"
    else:
        rel=f"data/futures/um/monthly/klines/{symbol}/1h/{symbol}-1h-{month}.zip"
    url=f"{BASE}/{rel}"; p=ROOT/market/symbol/f"{symbol}-{month}.zip"
    get(url,p); cp=Path(str(p)+".CHECKSUM"); get(url+".CHECKSUM",cp)
    expected=cp.read_text().strip().split()[0].lower()
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    if h.hexdigest()!=expected: raise RuntimeError(f"SHA256 mismatch {p}")
    return p

def load_daily(market,symbol,ms):
    out={}
    for month in ms:
        p=archive(market,symbol,month)
        with zipfile.ZipFile(p) as z:
            name=next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(name) as raw:
                for row in csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig")):
                    if len(row)<5: continue
                    try:
                        t=int(float(row[0]))
                        if t>=10**17: t//=10**6
                        elif t>=10**14: t//=10**3
                        # only completed UTC daily close candle (23:00 open)
                        dt=datetime.fromtimestamp(t/1000,timezone.utc)
                        if dt.hour==23:
                            px=float(row[4])
                            if px>0 and math.isfinite(px): out[dt.strftime("%Y-%m-%d")]=px
                    except (ValueError,OverflowError): pass
    return out

def rank(values):
    keys=sorted(values,key=lambda k:(values[k],k))
    n=len(keys)
    return {k:(i-(n-1)/2)/max(1,n-1) for i,k in enumerate(keys)}

def corr(a,b):
    if len(a)<5: return None
    x=np.asarray(a,dtype=float); y=np.asarray(b,dtype=float)
    if np.std(x)==0 or np.std(y)==0: return None
    return float(np.corrcoef(x,y)[0,1])

def block_ci(vals,seed=43,B=2000):
    x=np.asarray(vals,dtype=float); x=x[np.isfinite(x)]
    if len(x)<30: return None
    rng=np.random.default_rng(seed); n=len(x); means=[]
    # 7-day circular moving-block bootstrap
    starts=rng.integers(0,n,size=(B,math.ceil(n/7)))
    samples=np.concatenate([x[(s[:,None]+np.arange(7))%n] for s in starts],axis=1)[:,:n]
    means=samples.mean(axis=1)
    return [float(np.quantile(means,.025)),float(np.quantile(means,.975))]

def main():
    ms=list(months(START,END)); data={}; errors={}
    def one(s):
        return s,load_daily("spot",s,ms),load_daily("um",s,ms)
    with ThreadPoolExecutor(max_workers=6) as pool:
        fs=[pool.submit(one,s) for s in SYMBOLS]
        for f in as_completed(fs):
            try:
                s,spot,perp=f.result(); data[s]={"spot":spot,"perp":perp}
                print("LOADED",s,len(spot),len(perp),flush=True)
            except Exception as e:
                errors[str(f)] = str(e); print("LOAD_ERROR",str(e),flush=True)
    usable=sorted(s for s in data if len(data[s]["spot"])>300 and len(data[s]["perp"])>300)
    if len(usable)<8: raise RuntimeError(f"Need >=8 paired symbols; got {len(usable)}. {errors}")
    dates=sorted(set.intersection(*(set(data[s]["spot"]) & set(data[s]["perp"]) for s in usable)))
    # Daily cross-sectional basis at the completed UTC 23:00 candle; only predict subsequent returns.
    rows=[]; ic1=[]; ic5=[]; byyear=defaultdict(list); byreg=defaultdict(list)
    for i,d in enumerate(dates):
        if i+5>=len(dates): break
        basis={s:(data[s]["perp"][d]/data[s]["spot"][d]-1.0)*10000 for s in usable}
        r1={s:data[s]["perp"][dates[i+1]]/data[s]["perp"][d]-1 for s in usable if dates[i+1] in data[s]["perp"]}
        r5={s:data[s]["perp"][dates[i+5]]/data[s]["perp"][d]-1 for s in usable if dates[i+5] in data[s]["perp"]}
        common1=sorted(set(basis)&set(r1)); common5=sorted(set(basis)&set(r5))
        c1=corr([basis[s] for s in common1],[r1[s] for s in common1])
        c5=corr([basis[s] for s in common5],[r5[s] for s in common5])
        if c1 is not None: ic1.append((d,c1)); byyear[d[:4]].append(c1)
        if c5 is not None: ic5.append((d,c5))
        # Market regime uses only BTC spot trailing 30 calendar-day return, threshold +/-5%.
        btc=data["BTCUSDT"]["spot"]
        prior=dates[i-30] if i>=30 else None
        reg="warmup"
        if prior and prior in btc and d in btc:
            rr=btc[d]/btc[prior]-1
            reg="bull" if rr>0.05 else "bear" if rr<-.05 else "sideways"
            if c1 is not None: byreg[reg].append(c1)
        if len(common1)>=8:
            rb=rank({s:basis[s] for s in common1})
            k=max(1,int(len(common1)*.20))
            order=sorted(common1,key=lambda s:(basis[s],s))
            long=order[-k:]; short=order[:k]
            # 50% capital long and 50% short, gross exposure 100%; one-day rebalance.
            gross=.5*np.mean([r1[s] for s in long])-.5*np.mean([r1[s] for s in short])
            rows.append({"date":d,"basis_mean_bp":float(np.mean(list(basis.values()))),
                         "basis_ic_1d":c1,"basis_ic_5d":c5,"gross_hilo_1d_pct":gross*100,
                         "long_symbols":long,"short_symbols":short,"regime":reg})
    # daily rebalanced top/bottom quintile; 5bp one-way on 100% gross turnover baseline.
    gross=np.array([x["gross_hilo_1d_pct"] for x in rows],dtype=float)
    # Conservative 10bp/day round-trip proxy: 5bp per leg on 50% long + 50% short.
    cost_bp=10.0
    net=gross-cost_bp/100
    report={
      "experiment":"EXP-043 spot-perpetual basis cross-sectional predictive screen",
      "status":"signal_screen_only_not_portfolio_backtest",
      "source":"Binance Vision official spot and USD-M futures monthly 1h klines; SHA256 verified",
      "period":{"requested_start":START,"requested_end":END,"paired_first_date":dates[0],"paired_last_date":dates[-1]},
      "universe_requested":SYMBOLS,"universe_used":usable,"load_errors":errors,
      "observations":{"paired_daily_dates":len(dates),"daily_cross_sections":len(rows),"mean_cross_section_size":len(usable)},
      "definition":"basis_bp = (USD-M perpetual close / spot close - 1) * 10000, using matched completed UTC 23:00 hourly candle",
      "predictive_test":"Daily cross-sectional Pearson correlation of basis level and subsequent perpetual return, 1d and 5d; average daily IC and 7-day moving-block bootstrap CI",
      "basis_ic":{"1d_mean":float(np.mean([v for _,v in ic1])),"1d_median":float(np.median([v for _,v in ic1])),
                  "1d_block_bootstrap_95pct_ci":block_ci([v for _,v in ic1]),
                  "5d_mean":float(np.mean([v for _,v in ic5])),"5d_median":float(np.median([v for _,v in ic5])),
                  "5d_block_bootstrap_95pct_ci":block_ci([v for _,v in ic5]),
                  "yearly_1d_mean_ic":{k:float(np.mean(v)) for k,v in byyear.items()},
                  "regime_1d_mean_ic":{k:float(np.mean(v)) for k,v in byreg.items()}},
      "high_minus_low_quintile_daily_proxy":{"capital_weighting":"50% long high-basis quintile / 50% short low-basis quintile; 100% gross",
        "gross_mean_daily_pct":float(np.mean(gross)),"gross_median_daily_pct":float(np.median(gross)),
        "net_mean_daily_pct_after_10bp_round_trip":float(np.mean(net)),
        "net_positive_day_fraction":float(np.mean(net>0)),"days":len(net),
        "cost_assumption":"10bp/day round-trip on 100% gross exposure (5bp per side); conservative proxy, excludes funding and market impact",
        "note":"This is a signal diagnostic, not the MEAFLOW72 account simulation; no compounded equity or portfolio DD is claimed."},
      "daily_diagnostics":rows,
      "limitations":["Fixed 13-symbol universe survivorship bias; not delisted historical universe.",
        "Basis is sampled once daily at completed UTC 23:00 hourly candle; not intraday executable basis.",
        "No funding cashflow, actual fees by symbol, slippage, spread, borrow, liquidation, or account-level drawdown model.",
        "Basis can proxy demand/risk premia; correlation is not causal and can be regime-dependent.",
        "5-day forward returns overlap, so confidence interval uses 7-day moving blocks; ICs are not independent."],
      "decision_rule":"Advance to portfolio test only if 1d basis IC has positive block-bootstrap lower bound, positive mean high-minus-low net daily proxy after 10bp cost, and positive IC in at least 3 calendar years. Otherwise stop without parameter tuning."
    }
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp043_basis_screen.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("SCREEN",json.dumps({k:report["basis_ic"][k] for k in ("1d_mean","1d_block_bootstrap_95pct_ci","5d_mean","5d_block_bootstrap_95pct_ci","yearly_1d_mean_ic","regime_1d_mean_ic")}),flush=True)
    print("HILO",json.dumps(report["high_minus_low_quintile_daily_proxy"]),flush=True)
if __name__=="__main__": main()
