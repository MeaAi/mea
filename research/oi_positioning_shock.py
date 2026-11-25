#!/usr/bin/env python3
"""Point-in-time OI/positioning shock research. Historical Binance UM metrics + 1m klines.
No private API, no order placement. Signals are frozen from train quantiles only.
"""
import argparse,csv,gzip,glob,hashlib,io,json,math,urllib.request,zipfile
from pathlib import Path
from datetime import date,timedelta,datetime,timezone
from bisect import bisect_right
from collections import defaultdict

BASE="https://data.binance.vision/data/futures/um/daily/metrics"
def days_between(start,end):
    d=date.fromisoformat(start); z=date.fromisoformat(end)
    while d<=z:
        yield d.isoformat(); d+=timedelta(days=1)
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 research-only"})
    with urllib.request.urlopen(req,timeout=120) as r:return r.read()
def metrics_for(symbol,start,end):
    out={}
    for day in days_between(start,end):
        name=f"{symbol}-metrics-{day}.zip"; url=f"{BASE}/{symbol}/{name}"
        try: blob=get(url); chk=get(url+".CHECKSUM")
        except Exception as e: raise RuntimeError(f"metrics archive missing {name}: {e}")
        expected=chk.decode().strip().split()[0].lower()
        actual=hashlib.sha256(blob).hexdigest()
        if actual!=expected: raise RuntimeError(f"SHA256 mismatch {name}")
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            fn=next(n for n in z.namelist() if n.endswith(".csv"))
            with z.open(fn) as raw:
                for r in csv.DictReader(io.TextIOWrapper(raw,encoding="utf-8",newline="")):
                    # 2024 archives use end-of-period timestamps; preserve original labels.
                    t=int(datetime.strptime(r["create_time"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()*1000)
                    vals={}
                    for k in ("sum_open_interest_value","count_toptrader_long_short_ratio","sum_toptrader_long_short_ratio","count_long_short_ratio","sum_taker_long_short_vol_ratio"):
                        try: vals[k]=float(r[k])
                        except (ValueError,TypeError): vals[k]=float("nan")
                    if math.isfinite(vals["sum_open_interest_value"]) and vals["sum_open_interest_value"]>0:out[t]=vals
    return sorted(out.items())
def load_bars(pattern):
    out=defaultdict(dict)
    for p in glob.glob(pattern):
        sym=Path(p).name.split("-")[0]
        with gzip.open(p,"rt",encoding="utf-8",newline="") as f:
            for r in csv.DictReader(f):
                try:
                    t=int(r["open_time_ms"])
                    out[sym][t]={k:float(r[k]) for k in ("open","high","low","close")}
                except (ValueError,KeyError):pass
    return out
def qtile(a,q):
    x=sorted(v for v in a if math.isfinite(v))
    return x[min(len(x)-1,max(0,math.ceil(q*len(x))-1))] if x else float("nan")
def calc_dd(trades,initial):
    eq=peak=initial; dd=0.0
    for tr in trades:
        entry,exitp,side,fee_entry,fee_exit,slip_entry,slip_exit,lows,highs=tr
        eq*=1-(fee_entry+slip_entry)/10000
        peak=max(peak,eq)
        for lo,hi in zip(lows,highs):
            adverse=(lo/entry-1)*10000 if side==1 else (entry/hi-1)*10000
            mark=eq*(1+adverse/10000)
            dd=max(dd,(peak-mark)/peak if peak else 0)
        raw=(exitp/entry-1)*10000*side
        eq*=1+raw/10000
        eq*=1-(fee_exit+slip_exit)/10000
        peak=max(peak,eq); dd=max(dd,(peak-eq)/peak if peak else 0)
    return eq,dd*100
def simulate(rows,signals,lo,hi,h,fee,slip,initial):
    chosen=[]; nxt=lo
    for i,side in signals:
        if i<lo or i+h>=hi or i+1>=len(rows):continue
        if i>=nxt and all(rows[j] is not None for j in range(i+1,i+h+1)):
            chosen.append((i,side));nxt=i+h+1
    trades=[]
    for i,side in chosen:
        entry=rows[i+1]["open"]; exitp=rows[i+h]["close"]
        if entry<=0:continue
        segment=rows[i+1:i+h+1]
        trades.append((entry,exitp,side,fee,fee,slip,slip,[x["low"] for x in segment],[x["high"] for x in segment]))
    end,dd=calc_dd(trades,initial)
    eq=initial; gp=fees=slips=0; wins=0; netbps=[]
    for tr in trades:
        en,ex,side,fe,fx,se,sx,*_=tr
        raw=(ex/en-1)*10000*side
        gross=eq*raw/10000; f=eq*(fe+fx)/10000; sl=eq*(se+sx)/10000
        pnl=gross-f-sl; gp+=gross;fees+=f;slips+=sl;wins+=pnl>0
        netbps.append(raw-fe-fx-se-sx);eq+=pnl
    n=len(trades)
    return {"trades":n,"end_equity_usdt":round(end,6),"net_return_pct":round((end/initial-1)*100,4),
      "gross_pnl_usdt":round(gp,6),"fees_usdt":round(fees,6),"slippage_usdt":round(slips,6),
      "net_mean_bp":round(sum(netbps)/n,4) if n else None,"win_rate_pct":round(100*wins/n,2) if n else None,
      "max_adverse_mark_dd_pct":round(dd,4),"profit_factor":None}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True);ap.add_argument("--start-day",required=True);ap.add_argument("--end-day",required=True)
    ap.add_argument("--out",default="oi_positioning_oos.json");ap.add_argument("--capital",type=float,default=100)
    a=ap.parse_args();bars=load_bars(a.input);result={"source":"Binance Vision USD-M metrics daily archives + 1m futures klines",
      "timestamp_policy":"2024 historical metrics create_time labels treated as end-of-period; as-of join only, signal uses metrics timestamp <= decision minute; entry next minute open.",
      "splits":"Chronological 50% train / 20% validation / 30% untouched OOS by matched minute rows. Thresholds fit on train only.",
      "costs":"Entry and exit fee each 2/5/8 bp; entry and exit slippage each 2 bp. 1x, 100% equity per trade, non-overlapping.",
      "limitations":["Metrics are 5-minute aggregates/snapshots; no tick-level position changes.","No funding cashflow or liquidation simulation in this diagnostic.","Historical metrics definitions and timestamp semantics require effective-date caution; this sample is 2024.","Adverse drawdown uses 1m high/low path during each held trade, not exchange liquidation engine."],"symbols":{}}
    for sym,bmap in bars.items():
        m=metrics_for(sym,a.start_day,a.end_day); mt=[x[0] for x in m]; mv=[x[1] for x in m]
        ts=sorted(bmap); rows=[]
        for i,t in enumerate(ts):
            j=bisect_right(mt,t)-1
            if j<12 or i<60:rows.append(None);continue
            v=mv[j];v0=mv[j-3];v12=mv[j-12]
            p=bmap[t]["close"];p15=bmap[ts[i-15]]["close"] if i>=15 else p
            oi15=v["sum_open_interest_value"]/v0["sum_open_interest_value"]-1
            ret15=p/p15-1 if p15 else 0
            rows.append({"t":t,**bmap[t],"oi15":oi15,"ret15":ret15,
              "top_pos":v["sum_toptrader_long_short_ratio"],"top_acc":v["count_toptrader_long_short_ratio"],
              "global_acc":v["count_long_short_ratio"],"taker_ratio":v["sum_taker_long_short_vol_ratio"]})
        valid=[i for i,x in enumerate(rows) if x is not None and math.isfinite(x["oi15"]) and math.isfinite(x["ret15"])]
        if len(valid)<1000:continue
        n=len(rows); cut=int(n*.5); val=int(n*.7)
        tr=[rows[i] for i in valid if i<cut]
        th={"oi_hi":qtile([x["oi15"] for x in tr],.8),"oi_lo":qtile([x["oi15"] for x in tr],.2),
            "ret_hi":qtile([x["ret15"] for x in tr],.8),"ret_lo":qtile([x["ret15"] for x in tr],.2),
            "top_pos_hi":qtile([x["top_pos"] for x in tr],.8),"top_pos_lo":qtile([x["top_pos"] for x in tr],.2),
            "global_hi":qtile([x["global_acc"] for x in tr],.8),"global_lo":qtile([x["global_acc"] for x in tr],.2)}
        families={"oi_expansion_momentum":[],"oi_contraction_reversal":[],"crowding_reversal":[]}
        for i in valid:
            x=rows[i]; oi=x["oi15"];r=x["ret15"]
            if oi>=th["oi_hi"] and r>0:families["oi_expansion_momentum"].append((i,1))
            elif oi>=th["oi_hi"] and r<0:families["oi_expansion_momentum"].append((i,-1))
            if oi<=th["oi_lo"] and r>=th["ret_hi"]:families["oi_contraction_reversal"].append((i,-1))
            elif oi<=th["oi_lo"] and r<=th["ret_lo"]:families["oi_contraction_reversal"].append((i,1))
            if x["top_pos"]>=th["top_pos_hi"] and x["global_acc"]>=th["global_hi"]:families["crowding_reversal"].append((i,-1))
            elif x["top_pos"]<=th["top_pos_lo"] and x["global_acc"]<=th["global_lo"]:families["crowding_reversal"].append((i,1))
        sr={"matched_minutes":n,"metrics_rows":len(m),"train_thresholds":th,"families":{}}
        for name,sigs in families.items():
            sr["families"][name]={"signal_count":len(sigs),"horizons":{}}
            for h in (15,60,240):
                sr["families"][name]["horizons"][str(h)]={}
                for split,lo,hi in (("train",0,cut),("validation",cut,val),("oos",val,n)):
                    sr["families"][name]["horizons"][str(h)][split]={}
                    for fee in (2,5,8):
                        sr["families"][name]["horizons"][str(h)][split][f"fee{fee}_slip2_each_way"]=simulate(rows,sigs,lo,hi,h,fee,2,a.capital)
        result["symbols"][sym]=sr
    Path(a.out).write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
