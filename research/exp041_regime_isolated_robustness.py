#!/usr/bin/env python3
"""EXP-041: regime-isolated VWAP comparison with matched robustness checks."""
import json, math
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import funding_carry_liquidation_causal as base
import exp039_binance_vwap as exp039

SYMBOLS=exp039.SYMBOLS
POLICY=exp039.POLICY
DAY=exp039.DAY
HOUR=exp039.HOUR

def iso(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()

def compact(r):
    keys=("start_equity_usdt","end_equity_usdt","net_return_pct","max_drawdown_pct",
          "liquidated","rebalance_count","hourly_adverse_checks","trading_fees_usdt",
          "slippage_usdt","price_pnl_usdt","funding_pnl_usdt")
    return {k:r[k] for k in keys}

def cmp(b,c):
    return {"return_delta_pp":round(c["net_return_pct"]-b["net_return_pct"],4),
            "drawdown_improvement_pp":round(c["max_drawdown_pct"]-b["max_drawdown_pct"],4),
            "return_pass":c["net_return_pct"]>b["net_return_pct"],
            "drawdown_pass":c["max_drawdown_pct"]>b["max_drawdown_pct"],
            "no_liquidation":not c["liquidated"],
            "joint_pass":c["net_return_pct"]>b["net_return_pct"] and
                         c["max_drawdown_pct"]>b["max_drawdown_pct"] and not c["liquidated"]}

def aggregate(rows):
    # Each contiguous regime block starts with an independent 100 USDT account.
    # Compound block returns for a regime-level growth factor; report worst block DD.
    factor=1.0
    for row in rows:
        factor *= row["end_equity_usdt"]/100.0
    ret=(factor-1)*100
    worst=min((row["max_drawdown_pct"] for row in rows),default=0.0)
    return {"segments":len(rows),"total_days":round(sum(x["days"] for x in rows),2),
            "compounded_return_pct":round(ret,4),"equivalent_end_equity_from_100":round(100*factor,6),
            "worst_segment_max_drawdown_pct":round(worst,4),
            "liquidations":sum(bool(x["liquidated"]) for x in rows)}

def main():
    months=list(base.months_between("2023-01","2026-10"))
    root=Path("research-output");root.mkdir(exist_ok=True)
    data={};errors={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        fs={pool.submit(base.load_symbol,s,months,root):s for s in SYMBOLS}
        for f in as_completed(fs):
            s=fs[f]
            try:
                _,fund,marks=f.result();data[s]={"fund":fund,"marks":marks}
                print("LOADED",s,len(fund),len(marks),flush=True)
            except Exception as e:
                errors[s]=str(e);print("SKIP",s,str(e),flush=True)
    if len(data)<8 or "BTCUSDT" not in data: raise RuntimeError("Insufficient symbols "+json.dumps(errors))
    data={s:data[s] for s in sorted(data)}
    vraw=exp039.load_btc_vwap(months,root);vwap=exp039.make_vwap_series(vraw)
    sim=exp039.make_sim(vwap)

    # Match EXP-040 OOS boundary and require 155d VWAP warm-up before OOS.
    events=sorted(t for s in data for t in data[s]["fund"]
                  if sum(t in data[z]["fund"] and t in data[z]["marks"] for z in data)>=math.ceil(.8*len(data)))
    first=max(events[0],vwap["times"][0]+155*DAY);last=events[-1]
    oos_start=first+int((last-first)*.70);oos_end=last

    btc=data["BTCUSDT"]["marks"];bt=sorted(btc)
    def regime_at(ts):
        import bisect
        j=bisect.bisect_right(bt,ts)-1;k=bisect.bisect_right(bt,ts-30*DAY)-1
        if j<0 or k<0:return "unknown"
        ret=btc[bt[j]][3]/btc[bt[k]][3]-1
        return "bull" if ret>.05 else ("bear" if ret<-.05 else "sideways")

    # Use the simulator's exact regime timestamp convention: last completed 1h bar.
    hourly=[t for t in bt if oos_start<=t<=oos_end]
    labels=[regime_at(t-HOUR) for t in hourly]
    MIN_SEGMENT_DAYS=45
    segments=[]; start=None; prev=None; prev_t=None
    for t,lab in zip(hourly,labels):
        if lab=="unknown": 
            if start is not None and prev_t-start>=MIN_SEGMENT_DAYS*DAY: segments.append((prev,start,prev_t,prev_t-start))
            start=None;prev=None;prev_t=None;continue
        if start is None:
            start=t;prev=lab;prev_t=t
        elif lab==prev and t-prev_t==HOUR:
            prev_t=t
        else:
            if prev_t-start>=MIN_SEGMENT_DAYS*DAY:segments.append((prev,start,prev_t,prev_t-start))
            start=t;prev=lab;prev_t=t
    if start is not None and prev_t-start>=MIN_SEGMENT_DAYS*DAY:segments.append((prev,start,prev_t,prev_t-start))
    # Include contiguous regime-pure blocks  >=45 days; shorter episodes are counted, not silently treated as full samples.
    if not segments:raise RuntimeError(f"No regime-pure segments >= {MIN_SEGMENT_DAYS} days")
    short_segments=[]
    # Count shorter contiguous episodes for transparency.
    st=None; pl=None; pt=None
    for t,lab in zip(hourly,labels):
        if lab=="unknown":
            if st is not None and pt-st<MIN_SEGMENT_DAYS*DAY: short_segments.append({"regime":pl,"start":iso(st),"end":iso(pt),"days":round((pt-st)/DAY,2)})
            st=pl=pt=None; continue
        if st is None: st=t; pl=lab; pt=t
        elif lab==pl and t-pt==HOUR: pt=t
        else:
            if pt-st<MIN_SEGMENT_DAYS*DAY: short_segments.append({"regime":pl,"start":iso(st),"end":iso(pt),"days":round((pt-st)/DAY,2)})
            st=t; pl=lab; pt=t
    if st is not None and pt-st<MIN_SEGMENT_DAYS*DAY: short_segments.append({"regime":pl,"start":iso(st),"end":iso(pt),"days":round((pt-st)/DAY,2)})
    print("SEGMENTS",json.dumps([{"regime":r,"start":iso(a),"end":iso(b),"days":round(d/DAY,2)} for r,a,b,d in segments]),flush=True)

    def execute(period,fee,slip,days,mode):
        r=sim(data,period,1.0,fee,slip_bp=slip,lookback_days=7,rebalance_days=7,
              tail_fraction=.20,regime_policy=POLICY,regime_threshold_pct=5.0,
              sideways_action="hold",vwap_series=vwap,vwap_days=days,vwap_mode=mode)
        return compact(r)

    by_regime={}
    for regime in ("bull","bear","sideways"):
        segs=[x for x in segments if x[0]==regime]
        if not segs:
            by_regime[regime]={"eligible_segments":0,"note":"No >=45d contiguous segment; insufficient sample."}
            continue
        base_rows=[];cand_rows=[];details=[]
        for idx,(_,a,b,dur) in enumerate(segs,1):
            period=(a,b)
            rb=execute(period,5,2,155,"baseline")
            rc=execute(period,5,2,155,"short_only_below")
            base_rows.append({**rb,"days":dur/DAY})
            cand_rows.append({**rc,"days":dur/DAY})
            details.append({"segment":idx,"period_utc":{"start":iso(a),"end":iso(b)},
                            "days":round(dur/DAY,2),"baseline":rb,"candidate_155d":rc,
                            "comparison":cmp(rb,rc)})
        by_regime[regime]={"eligible_segments":len(segs),
            "baseline_aggregate":aggregate(base_rows),"candidate_155d_aggregate":aggregate(cand_rows),
            "aggregate_comparison":{
                "return_delta_pp_compounded":round(aggregate(cand_rows)["compounded_return_pct"]-aggregate(base_rows)["compounded_return_pct"],4),
                "worst_dd_improvement_pp":round(aggregate(cand_rows)["worst_segment_max_drawdown_pct"]-aggregate(base_rows)["worst_segment_max_drawdown_pct"],4),
                "all_segments_joint_pass":all(x["comparison"]["joint_pass"] for x in details),
                "segments_joint_passed":sum(x["comparison"]["joint_pass"] for x in details)},
            "segments":details}
        print("REGIME",regime,json.dumps(by_regime[regime]["aggregate_comparison"]),flush=True)

    # Cost stress across every eligible pure-regime segment, independently reset at each segment.
    costs={}
    for fee,slip in ((5,2),(10,4),(15,6)):
        costs[f"{fee}bp_fee_{slip}bp_slip"]={}
        for regime in ("bull","bear","sideways"):
            segs=[x for x in segments if x[0]==regime]
            if not segs:continue
            br=[];cr=[]
            for _,a,b,d in segs:
                br.append({**execute((a,b),fee,slip,155,"baseline"),"days":d/DAY})
                cr.append({**execute((a,b),fee,slip,155,"short_only_below"),"days":d/DAY})
            ba=aggregate(br);ca=aggregate(cr)
            costs[f"{fee}bp_fee_{slip}bp_slip"][regime]={
                "baseline":ba,"candidate":ca,
                "joint_pass":ca["compounded_return_pct"]>ba["compounded_return_pct"] and
                             ca["worst_segment_max_drawdown_pct"]>ba["worst_segment_max_drawdown_pct"] and ca["liquidations"]==0}
        print("COST",fee,slip,json.dumps(costs[f"{fee}bp_fee_{slip}bp_slip"]),flush=True)

    # Parameter neighbourhood on the same regime-pure segments.
    windows={}
    for days in (135,155,175):
        windows[f"{days}d"]={}
        for regime in ("bull","bear","sideways"):
            segs=[x for x in segments if x[0]==regime]
            if not segs:continue
            rows=[]
            for _,a,b,d in segs:
                rows.append({**execute((a,b),5,2,days,"short_only_below"),"days":d/DAY})
            windows[f"{days}d"][regime]=aggregate(rows)
    report={"experiment":"EXP-041 regime-isolated VWAP validation and robustness",
      "branch":"research/exp041-regime-isolated-robustness",
      "reference_base_sha":"a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1",
      "source_candidate_branch":"research/exp039-binance-vwap",
      "oos_utc":{"start":iso(oos_start),"end":iso(oos_end)},
      "regime_definition":"BTC trailing 30d return >+5% bull, <-5% bear, otherwise sideways; uses completed hourly mark bars only.",
      "segment_method":f"All contiguous pure-regime OOS blocks >={MIN_SEGMENT_DAYS} days; each block is independently restarted with 100 USDT and 7d funding warmup. Compound independent block returns by regime; report worst segment drawdown. No positions or PnL are carried between segments.",
      "capital_usdt":100,"leverage":1,"baseline_costs":"5bp one-way fee + 2bp one-way slippage",
      "candidate_rule":"155d rolling BTC close*quote-volume VWAP; when last completed BTC close is below VWAP, permit shorts only.",
      "loaded_symbols":list(data),"data_errors":errors,
      "segments":[{"regime":r,"start":iso(a),"end":iso(b),"days":round(d/DAY,2)} for r,a,b,d in segments],
      "regime_results":by_regime,"cost_stress":costs,"window_sensitivity":windows,
      "decision_rule":"Reject unless candidate increases compounded return and improves worst segment hourly adverse drawdown, with zero liquidations; require segment-level consistency plus cost and window robustness.",
      "limitations":["Regime blocks are historical contiguous samples, not independent market cycles.",
       "Only blocks  >=45d are included; shorter regime episodes are separately counted and listed.",
       "Each segment restarts at 100 USDT; compounded return is a regime-conditional growth factor, not a tradable continuous portfolio equity curve.",
       "VWAP is a volume-weighted traded-price proxy, not holder cost basis.",
       "Static 13-symbol universe survivorship bias; portfolio hourly adverse/liquidation remains an approximation."]}
    Path("research-results").mkdir(exist_ok=True)
    Path("research-results/exp041_regime_isolated_robustness.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REPORT_READY research-results/exp041_regime_isolated_robustness.json",flush=True)

if __name__=="__main__":main()
