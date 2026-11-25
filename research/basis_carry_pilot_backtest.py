#!/usr/bin/env python3
"""Cross-sectional spot/perpetual basis pilot. 1x gross exposure, event funding, adverse-minute DD."""
import argparse,csv,hashlib,io,json,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

BASE="https://data.binance.vision/data"
SYMS=("BTCUSDT","ETHUSDT","SOLUSDT")
FEE_BP=5.0
SLIP_BP=2.0
START="2024-05"
END="2024-06"

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"research-only"})
    with urllib.request.urlopen(req,timeout=120) as r:return r.read()
def archive(kind,sym,month):
    if kind=="spot": p=f"spot/monthly/klines/{sym}/1m/{sym}-1m-{month}.zip"
    elif kind=="perp": p=f"futures/um/monthly/klines/{sym}/1m/{sym}-1m-{month}.zip"
    elif kind=="funding": p=f"futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{month}.zip"
    else: raise ValueError(kind)
    url=f"{BASE}/{p}"; blob=fetch(url); check=fetch(url+".CHECKSUM").decode().strip().split()[0].lower()
    if hashlib.sha256(blob).hexdigest()!=check: raise RuntimeError("checksum mismatch "+p)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name=next(n for n in z.namelist() if n.endswith(".csv"))
        rows=list(csv.reader(io.TextIOWrapper(z.open(name),encoding="utf-8-sig",newline="")))
    return rows
def ts(v):
    s=v.strip()
    try: n=int(float(s))
    except ValueError:return int(datetime.strptime(s,"%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()*1000)
    if n>10**17:return n//10**6
    if n>10**14:return n//10**3
    return n
def load():
    data={}
    for sym in SYMS:
        spot={}; perp={}; funding=[]
        for month in (START,END):
            for kind,target in (("spot",spot),("perp",perp)):
                for r in archive(kind,sym,month):
                    if not r:continue
                    try:t=ts(r[0])
                    except ValueError:continue
                    target[t]={"open":float(r[1]),"high":float(r[2]),"low":float(r[3]),"close":float(r[4])}
            for r in archive("funding",sym,month):
                if not r:continue
                try:funding.append((ts(r[0]),float(r[2])))
                except (ValueError,IndexError):continue
        common=sorted(set(spot)&set(perp))
        data[sym]={"spot":spot,"perp":perp,"funding":sorted(funding),"common":common}
    return data
def main():
    d=load()
    # Only exact common minutes; no interpolation. Daily signal formed at UTC day-end,
    # then traded from the next minute for 1440 minutes.
    rows=[]
    for sym,x in d.items():
        for t in x["common"]:
            s=x["spot"][t]["close"]; p=x["perp"][t]["close"]
            if s>0: rows.append((t,sym,p/s-1.0))
    bytime={}
    for t,s,b in rows:bytime.setdefault(t,{})[s]=b
    times=sorted(bytime)
    idx={t:i for i,t in enumerate(times)}
    # Snapshot basis level and 5-day basis change at 23:59 UTC; signal uses only data available then.
    snapshots=[]
    for t in times:
        dt=datetime.fromtimestamp(t/1000,timezone.utc)
        if dt.hour==23 and dt.minute==59:
            j=idx[t]; prior=times[j-7200] if j>=7200 and t-times[j-7200]==7200*60000 else None
            if prior is None:continue
            if len(bytime[t])==3 and len(bytime[prior])==3:
                snapshots.append((t,{s:bytime[t][s] for s in SYMS},{s:bytime[t][s]-bytime[prior][s] for s in SYMS}))
    # Each variant: level and 5d change, both signs. Top-ranked long, bottom-ranked short.
    variants=[]
    for factor in ("basis_level","basis_5d_change"):
      for sign in (1,-1):
        eq=100.0; peak=100.0; maxdd=0.0; trades=0; pnl_total=0.0; cost_total=0.0; funding_total=0.0
        for sig_t,levels,changes in snapshots:
            scores=levels if factor=="basis_level" else changes
            ranked=sorted(SYMS,key=lambda s:sign*scores[s])
            long_sym=ranked[-1]; short_sym=ranked[0]
            start_i=idx.get(sig_t,-1)+1
            if start_i<1 or start_i+1439>=len(times):continue
            entry_t=times[start_i]; exit_t=times[start_i+1439]
            # Reject any missing minute in the holding window or mismatched spot/perp data.
            window=times[start_i:start_i+1440]
            if len(window)!=1440 or any(window[k]-window[k-1]!=60000 for k in range(1,len(window))):continue
            notion=eq*0.5
            legs=[]; day_funding=0.0; day_price=0.0; day_cost=0.0
            valid=True
            for sym,side in ((long_sym,1),(short_sym,-1)):
                bars=d[sym]["perp"]
                if entry_t not in bars or exit_t not in bars:valid=False;break
                entry=bars[entry_t]["open"]; exitp=bars[exit_t]["close"]
                ret=side*(exitp/entry-1)
                day_price+=notion*ret
                # Entry and exit costs separately on their own notionals.
                day_cost+=notion*2*(FEE_BP+SLIP_BP)/10000
                for ft,rate in d[sym]["funding"]:
                    if entry_t<=ft<=exit_t:
                        # Positive funding: longs pay, shorts receive.
                        day_funding += -side*notion*rate
                legs.append((sym,side,notion,entry))
            if not valid:continue
            net=day_price+day_funding-day_cost
            # Hourly adverse mark approximated using every minute's high/low; conservative
            # adverse side for each leg, portfolio equity path from current start equity.
            for k,t in enumerate(window):
                mark=0.0
                for sym,side,n,entry in legs:
                    b=d[sym]["perp"][t]
                    adverse=(b["low"]/entry-1) if side==1 else (b["high"]/entry-1)
                    mark+=n*side*adverse
                mark_eq=eq+mark-day_cost
                peak=max(peak,mark_eq)
                if peak>0:maxdd=min(maxdd,mark_eq/peak-1)
            eq+=net; peak=max(peak,eq); maxdd=min(maxdd,eq/peak-1)
            trades+=1;pnl_total+=day_price;funding_total+=day_funding;cost_total+=day_cost
        variants.append({"factor":factor,"sign":sign,"trades":trades,"start_equity":100.0,
          "end_equity":round(eq,6),"net_return_pct":round((eq/100-1)*100,4),
          "max_adverse_minute_dd_pct":round(maxdd*100,4),"price_pnl_usdt":round(pnl_total,6),
          "funding_usdt":round(funding_total,6),"cost_usdt":round(cost_total,6),
          "fee_bp_per_side":FEE_BP,"slippage_bp_per_side":SLIP_BP,"leverage":1,
          "portfolio":"50% long highest score + 50% short lowest score; daily 1440m holding"})
    report={"period":[START,END],"symbols":list(SYMS),"method":"UTC daily cross-sectional top-vs-bottom basis; 5-day change uses 7200 contiguous minute index observations; next-minute open entry; 1440 contiguous 1m bars; 5bp fee + 2bp slippage each side; funding only at actual timestamps; adverse minute high/low DD.",
      "data_qa":"archives checksum-verified; exact spot/perp common timestamps only; no gap interpolation",
      "limitations":["Two-month pilot only; not OOS proof.","Only three-symbol cross-section; 50/50 long-short gross 1x.","No queue/fill model because this is a taker execution baseline.","Funding timestamp/rate interpretation must be checked against exchange semantics before full-period expansion."],
      "results":variants}
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/basis_pilot_backtest.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
