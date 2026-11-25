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
    elif kind=="mark": p=f"futures/um/monthly/markPriceKlines/{sym}/1m/{sym}-1m-{month}.zip"
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
        spot={}; perp={}; mark={}; funding=[]
        for month in (START,END):
            for kind,target in (("spot",spot),("perp",perp),("mark",mark)):
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
        data[sym]={"spot":spot,"perp":perp,"mark":mark,"funding":sorted(funding),"common":common}
    return data
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--fee-bp",type=float,default=FEE_BP)
    parser.add_argument("--out",default="research-results/basis_pilot_backtest.json")
    args=parser.parse_args()
    fee_bp=args.fee_bp
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
        skips={"short_window":0,"minute_gap":0,"missing_perp_minute":0,"missing_mark_funding_time":0}; missing_mark_samples=[]; candidates=0; funding_events_seen=0
        for sig_t,levels,changes in snapshots:
            candidates+=1
            scores=levels if factor=="basis_level" else changes
            ranked=sorted(SYMS,key=lambda s:sign*scores[s])
            long_sym=ranked[-1]; short_sym=ranked[0]
            start_i=idx.get(sig_t,-1)+1
            if start_i<1 or start_i+1439>=len(times):skips["short_window"]+=1;continue
            entry_t=times[start_i]; exit_t=times[start_i+1439]
            # Reject any missing minute in the holding window or mismatched spot/perp data.
            window=times[start_i:start_i+1440]
            if len(window)!=1440 or any(window[k]-window[k-1]!=60000 for k in range(1,len(window))):skips["minute_gap"]+=1;continue
            notion=eq*0.5
            legs=[]; day_funding=0.0; day_price=0.0; day_cost=0.0
            valid=True
            for sym,side in ((long_sym,1),(short_sym,-1)):
                bars=d[sym]["perp"]
                if any(t not in bars for t in window):valid=False;skips["missing_perp_minute"]+=1;break
                entry=bars[entry_t]["open"]; exitp=bars[exit_t]["close"]
                ret=side*(exitp/entry-1)
                day_price+=notion*ret
                # Entry and exit costs separately on their own notionals.
                day_cost+=notion*2*(fee_bp+SLIP_BP)/10000
                for ft,rate in d[sym]["funding"]:
                    if entry_t<=ft<=exit_t:
                        funding_events_seen+=1
                        # Positive funding: longs pay, shorts receive.
                        if ft not in d[sym]["mark"]:
                            valid=False;skips["missing_mark_funding_time"]+=1
                            if len(missing_mark_samples)<12:missing_mark_samples.append({"symbol":sym,"funding_time_ms":ft,"entry_time_ms":entry_t,"exit_time_ms":exit_t})
                            break
                        mark_at_funding=d[sym]["mark"][ft]["open"]
                        quantity=notion/entry
                        day_funding += -side*quantity*mark_at_funding*rate
                legs.append((sym,side,notion,entry))
            if not valid:continue
            # Entry/exit costs are booked at their actual cashflow points, not all at entry.
            entry_cost=notion*(fee_bp+SLIP_BP)/10000*2
            exit_cost=entry_cost
            day_cost=entry_cost+exit_cost
            net=day_price+day_funding-day_cost
            # Hourly adverse mark approximated using every minute's high/low; conservative
            # adverse side for each leg, portfolio equity path from current start equity.
            funding_accrued=0.0
            funding_events={}
            for sym,side,n,entry in legs:
                qty=n/entry
                for ft,rate in d[sym]["funding"]:
                    if entry_t<=ft<=exit_t:
                        funding_events.setdefault(ft,0.0)
                        funding_events[ft] += -side*qty*d[sym]["mark"][ft]["open"]*rate
            for k,t in enumerate(window):
                funding_accrued += funding_events.get(t,0.0)
                mark=0.0
                for sym,side,n,entry in legs:
                    b=d[sym]["perp"][t]
                    adverse=(b["low"]/entry-1) if side==1 else (b["high"]/entry-1)
                    mark+=n*side*adverse
                mark_eq=eq+mark+funding_accrued-entry_cost-(exit_cost if t==exit_t else 0.0)
                peak=max(peak,mark_eq)
                if peak>0:maxdd=min(maxdd,mark_eq/peak-1)
            eq+=net; peak=max(peak,eq); maxdd=min(maxdd,eq/peak-1)
            trades+=1;pnl_total+=day_price;funding_total+=day_funding;cost_total+=day_cost
        variants.append({"factor":factor,"sign":sign,"trades":trades,"start_equity":100.0,
          "end_equity":round(eq,6),"net_return_pct":round((eq/100-1)*100,4),
          "max_adverse_minute_dd_pct":round(maxdd*100,4),"price_pnl_usdt":round(pnl_total,6),
          "funding_usdt":round(funding_total,6),"cost_usdt":round(cost_total,6),
          "fee_bp_per_side":fee_bp,"slippage_bp_per_side":SLIP_BP,"leverage":1,
          "portfolio":"50% long highest score + 50% short lowest score; daily 1440m holding",
          "candidate_signals":candidates,"skip_counts":skips,"funding_events_in_holding_windows":funding_events_seen,"missing_mark_samples":missing_mark_samples})
    report={"period":[START,END],"symbols":list(SYMS),"method":f"UTC daily cross-sectional top-vs-bottom basis; 5-day change uses 7200 contiguous minute index observations; next-minute open entry; 1440 contiguous 1m bars; {fee_bp:g}bp fee + {SLIP_BP:g}bp slippage each side; funding uses event-time mark-price open; entry/exit costs booked at their timestamps; adverse minute high/low DD.",
      "data_qa":"archives checksum-verified; exact spot/perp common timestamps only; no gap interpolation",
      "limitations":["Two-month pilot only; not OOS proof.","Only three-symbol cross-section; 50/50 long-short gross 1x.","No queue/fill model because this is a taker execution baseline.","Funding uses event-time mark-price candles; verify archive alignment before full-period expansion."],
      "results":variants}
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
