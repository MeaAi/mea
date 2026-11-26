#!/usr/bin/env python3
"""Causal BTC 30d regime transition diagnostics: raw vs 6 completed-hour persistence."""
import json, bisect
from pathlib import Path
from datetime import datetime, timezone
import funding_carry_liquidation_fixed as sim

WINDOWS={
 "2023_calendar":("2023-01-01T00:00:00+00:00","2024-01-01T00:00:00+00:00"),
 "2024_calendar":("2024-01-01T00:00:00+00:00","2025-01-01T00:00:00+00:00"),
 "2025_jan_to_sep":("2025-01-01T00:00:00+00:00","2025-09-06T18:24:00+00:00"),
 "2025_sep_to_2026_oct":("2025-09-06T18:24:00+00:00","2026-10-31T16:00:00+00:00"),
}
H=3600000; DAY=24*H
def ms(s):return int(datetime.fromisoformat(s).timestamp()*1000)
def iso(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()

def main():
 months=list(sim.months_between("2022-12","2026-10"))
 _,fund,marks=sim.load_symbol("BTCUSDT",months,Path("research-output"))
 times=sorted(marks)
 close={t:marks[t][3] for t in times}
 def raw_at(ts):
  j=bisect.bisect_right(times,ts)-1
  k=bisect.bisect_right(times,ts-30*DAY)-1
  if j<0 or k<0:return "unknown"
  ret=close[times[j]]/close[times[k]]-1
  return "bull" if ret>.05 else ("bear" if ret<-.05 else "sideways")
 raw=[raw_at(t) for t in times]
 raw_index={t:i for i,t in enumerate(times)}
 def confirmed_at(i):
  cur=raw[i]
  if cur=="unknown":return cur
  for h in range(1,7):
   j=i-h
   if j<0 or raw[j]!=cur:
    return raw[max(0,i-6)]
  return cur
 confirmed=[confirmed_at(i) for i in range(len(times))]
 report={}
 for name,(start,end) in WINDOWS.items():
  lo=bisect.bisect_left(times,ms(start)); hi=bisect.bisect_right(times,ms(end))-1
  if hi<=lo:continue
  def runs(labels):
   out=[];s=lo
   for i in range(lo+1,hi+1):
    if labels[i]!=labels[i-1]:
     out.append({"from":labels[s],"start":iso(times[s]),"end":iso(times[i-1]),"hours":i-s})
     s=i
   out.append({"from":labels[s],"start":iso(times[s]),"end":iso(times[hi]),"hours":hi-s+1})
   return out
  rr=runs(raw); cr=runs(confirmed)
  raw_flips=sum(1 for i in range(lo+1,hi+1) if raw[i]!=raw[i-1])
  conf_flips=sum(1 for i in range(lo+1,hi+1) if confirmed[i]!=confirmed[i-1])
  mismatch=sum(1 for i in range(lo,hi+1) if raw[i]!=confirmed[i])
  state_hours={x:sum(1 for i in range(lo,hi+1) if raw[i]==x) for x in ("bull","bear","sideways","unknown")}
  conf_hours={x:sum(1 for i in range(lo,hi+1) if confirmed[i]==x) for x in ("bull","bear","sideways","unknown")}
  short_runs=[x for x in rr[:-1] if x["hours"]<7]
  lagged=[]
  for run in rr[1:]:
   idx=bisect.bisect_left(times,ms(run["start"]))
   if idx<=hi and confirmed[idx]!=run["from"]:
    j=idx
    while j<=hi and confirmed[j]!=run["from"]:j+=1
    if j<=hi:
     lagged.append({"to":run["from"],"raw_flip":iso(times[idx]),"confirmed_flip":iso(times[j]),"lag_hours":j-idx,"raw_run_hours":run["hours"]})
  report[name]={
   "period_utc":[iso(times[lo]),iso(times[hi])],"hourly_observations":hi-lo+1,
   "raw_flip_count":raw_flips,"confirmed_flip_count":conf_flips,
   "raw_state_hours":state_hours,"confirmed_state_hours":conf_hours,
   "raw_vs_confirmed_mismatch_hours":mismatch,
   "raw_vs_confirmed_mismatch_pct":round(100*mismatch/(hi-lo+1),3),
   "raw_regime_runs_shorter_than_7h":[x for x in short_runs],
   "confirmed_transition_lags":lagged,
   "median_transition_lag_hours":sorted(x["lag_hours"] for x in lagged)[len(lagged)//2] if lagged else 0,
   "mean_transition_lag_hours":round(sum(x["lag_hours"] for x in lagged)/len(lagged),3) if lagged else 0,
  }
  print("RESULT",name,json.dumps(report[name],separators=(",",":")),flush=True)
 output={
  "experiment":"BTC 30d +/-5% regime transition diagnostics",
  "branch":"research/meaflow72-regime-transition-diagnostics-v1",
  "source":"Free official Binance Vision BTCUSDT 1h markPriceKlines",
  "definition":"Raw regime uses trailing 30d mark-price return: bull > +5%, bear < -5%, sideways otherwise. 6h label reproduces the simulator's causal regime_at() logic: the candidate must match six preceding completed hourly observations.",
  "windows":report,
  "cautions":["This isolates signal classification, not strategy profitability.","Historical windows were already inspected; exploratory diagnostic, not pristine OOS.","6h persistence does not guarantee lower turnover because the strategy also rebalances on a 7d schedule."]
 }
 Path("research-results").mkdir(exist_ok=True)
 Path("research-results/meaflow72_regime_transition_diagnostics.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
 print("REPORT research-results/meaflow72_regime_transition_diagnostics.json",flush=True)
if __name__=="__main__":main()
