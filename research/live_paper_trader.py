#!/usr/bin/env python3
"""Read-only Binance USD-M live paper trader. Never places exchange orders.

Signals are deliberately fixed before the observation window:
- 60s aggressive-trade quote imbalance
- top-5 book depth imbalance
- both must agree and exceed fixed thresholds
Two shadow execution books are tracked: taker (cross spread + impact + fee)
and maker (post at touch; conservative trade-through/queue proxy + fee).
This is an exploratory live-data simulation, not a validated strategy.
"""
from __future__ import annotations
import argparse, collections, json, signal, sys, time
from datetime import datetime, timezone
from pathlib import Path
import websocket

STOP = False

def stop_handler(*_):
    global STOP
    STOP = True

def utc():
    return datetime.now(timezone.utc).isoformat()

class SymbolState:
    def __init__(self, symbol, args):
        self.symbol, self.args = symbol, args
        self.trades = collections.deque()
        self.bids, self.asks = [], []
        self.bid, self.ask = None, None
        self.bid_qty, self.ask_qty = 0.0, 0.0
        self.last_price = None
        self.last_signal_ts = 0.0
        self.accounts = {
            "taker": {"position": None, "trades": [], "equity_bp": 0.0},
            "maker": {"position": None, "pending": None, "trades": [], "equity_bp": 0.0}
        }
        self.events = 0
        self.aggtrade_events = 0
        self.bookticker_events = 0
        self.depth_events = 0
        self.parse_errors = 0
        self.unknown_streams = collections.Counter()
        self.signals = 0

    def on_trade(self, d):
        ts = int(d["T"]) / 1000.0
        price, qty = float(d["p"]), float(d["q"])
        buyer_maker = bool(d["m"])
        quote = price * qty
        self.trades.append((ts, quote if not buyer_maker else 0.0,
                            quote if buyer_maker else 0.0, price, qty, buyer_maker))
        self.last_price = price
        cutoff = ts - self.args.lookback
        while self.trades and self.trades[0][0] < cutoff:
            self.trades.popleft()
        self._maker_queue_update(price, qty, buyer_maker)
        self._mark_exits(ts)

    def on_book(self, d):
        self.bid, self.ask = float(d["b"]), float(d["a"])
        self.bid_qty, self.ask_qty = float(d["B"]), float(d["A"])
        if self.bid > 0 and self.ask > self.bid:
            self.last_price = (self.bid + self.ask) / 2
        self._mark_exits(time.time())

    def on_depth(self, d):
        self.bids = [(float(p), float(q)) for p, q in d.get("b", [])]
        self.asks = [(float(p), float(q)) for p, q in d.get("a", [])]

    def features(self):
        buy = sum(x[1] for x in self.trades)
        sell = sum(x[2] for x in self.trades)
        den = buy + sell
        trade_imb = (buy - sell) / den if den else 0.0
        bq = sum(q for _, q in self.bids) if self.bids else self.bid_qty
        aq = sum(q for _, q in self.asks) if self.asks else self.ask_qty
        book_imb = (bq - aq) / (bq + aq) if bq + aq else 0.0
        return trade_imb, book_imb, buy, sell

    def maybe_signal(self, now):
        if self.bid is None or self.ask is None or now - self.last_signal_ts < self.args.cooldown:
            return
        ti, bi, buy, sell = self.features()
        direction = 1 if ti >= self.args.trade_threshold and bi >= self.args.book_threshold else (
                    -1 if ti <= -self.args.trade_threshold and bi <= -self.args.book_threshold else 0)
        if not direction: return
        self.last_signal_ts = now
        self.signals += 1
        self._open_taker(direction, now, ti, bi)
        self._place_maker(direction, now, ti, bi)

    def _open_taker(self, direction, now, ti, bi):
        a = self.accounts["taker"]
        if a["position"] is not None: return
        mid = (self.bid + self.ask) / 2
        spread_bp = (self.ask - self.bid) / mid * 10000
        px = self.ask if direction > 0 else self.bid
        px *= (1 + direction * self.args.impact_bp / 10000)
        a["position"] = {"side": direction, "entry": px, "time": now,
                         "signal_trade_imbalance": ti, "signal_book_imbalance": bi,
                         "entry_spread_bp": spread_bp}

    def _place_maker(self, direction, now, ti, bi):
        a = self.accounts["maker"]
        if a["position"] is not None or a["pending"] is not None: return
        px = self.bid if direction > 0 else self.ask
        queue = self.bid_qty if direction > 0 else self.ask_qty
        a["pending"] = {"side": direction, "price": px, "time": now,
                        "queue_ahead": max(queue, 0.0), "qty_seen": 0.0,
                        "signal_trade_imbalance": ti, "signal_book_imbalance": bi}

    def _maker_queue_update(self, trade_price, qty, buyer_maker):
        a = self.accounts["maker"]; p = a["pending"]
        if not p: return
        # A buy limit joins bid; only aggressive sells at/below it can consume queue.
        # A sell limit joins ask; only aggressive buys at/above it can consume queue.
        eligible = (p["side"] > 0 and buyer_maker and trade_price <= p["price"]) or (
                   p["side"] < 0 and not buyer_maker and trade_price >= p["price"])
        if not eligible: return
        p["qty_seen"] += qty
        p["queue_ahead"] = max(0.0, p["queue_ahead"] - qty)
        # Conservative fill proxy: require trade-through by one tick after queue is consumed.
        tick = max(p["price"] * 0.000001, 1e-8)
        through = trade_price <= p["price"] - tick if p["side"] > 0 else trade_price >= p["price"] + tick
        if p["queue_ahead"] <= 0 and through:
            a["position"] = {"side": p["side"], "entry": p["price"], "time": time.time(),
                             "signal_trade_imbalance": p["signal_trade_imbalance"],
                             "signal_book_imbalance": p["signal_book_imbalance"],
                             "entry_spread_bp": None, "maker_fill": True,
                             "queue_qty_seen": p["qty_seen"]}
            a["pending"] = None

    def _mark_exits(self, now):
        if self.bid is None or self.ask is None: return
        for mode, a in self.accounts.items():
            p = a["position"]
            if not p: continue
            age = now - p["time"]
            mid = (self.bid + self.ask) / 2
            # Fixed time exit; no parameter fitting during this observation run.
            if age < self.args.hold_seconds: continue
            exit_px = self.bid if p["side"] > 0 else self.ask
            if mode == "taker":
                exit_px *= (1 - p["side"] * self.args.impact_bp / 10000)
                fees = 2 * self.args.taker_fee_bp
            else:
                fees = self.args.maker_fee_bp + self.args.taker_fee_bp
            gross = p["side"] * (exit_px / p["entry"] - 1) * 10000
            net = gross - fees - (self.args.impact_bp if mode == "maker" else 0)
            rec = {"opened_at": datetime.fromtimestamp(p["time"], timezone.utc).isoformat(),
                   "closed_at": utc(), "side": "LONG" if p["side"] > 0 else "SHORT",
                   "entry": p["entry"], "exit": exit_px, "gross_bp": gross,
                   "fees_bp": fees, "impact_allowance_bp": self.args.impact_bp if mode == "maker" else 2*self.args.impact_bp,
                   "net_bp": net, "hold_seconds": age,
                   "signal_trade_imbalance": p["signal_trade_imbalance"],
                   "signal_book_imbalance": p["signal_book_imbalance"],
                   "maker_fill_proxy": bool(p.get("maker_fill", False)),
                   "queue_qty_seen": p.get("queue_qty_seen")}
            a["trades"].append(rec); a["equity_bp"] += net; a["position"] = None

    def snapshot(self):
        ti, bi, buy, sell = self.features()
        return {"symbol": self.symbol, "events": self.events,
                "aggtrade_events": self.aggtrade_events,
                "bookticker_events": self.bookticker_events,
                "depth_events": self.depth_events,
                "parse_errors": self.parse_errors,
                "unknown_streams": dict(self.unknown_streams),
                "trades_in_lookback": len(self.trades),
                "buy_quote_in_lookback": buy, "sell_quote_in_lookback": sell,
                "signals": self.signals,
                "trade_imbalance": ti, "book_imbalance": bi,
                "taker": summary(self.accounts["taker"]),
                "maker": summary(self.accounts["maker"])}

def summary(a):
    xs = a["trades"]; nets = [x["net_bp"] for x in xs]
    return {"closed_trades":len(xs), "net_total_bp":sum(nets),
            "net_mean_bp":sum(nets)/len(nets) if nets else None,
            "win_rate":sum(x>0 for x in nets)/len(nets) if nets else None,
            "open_position":bool(a["position"]), "pending_limit":bool(a.get("pending")),
            "trade_log":xs}

def main():
    global STOP
    ap=argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--minutes", type=int, default=20)
    ap.add_argument("--lookback", type=int, default=60)
    ap.add_argument("--hold-seconds", type=int, default=60)
    ap.add_argument("--trade-threshold", type=float, default=0.35)
    ap.add_argument("--book-threshold", type=float, default=0.15)
    ap.add_argument("--cooldown", type=float, default=30)
    ap.add_argument("--taker-fee-bp", type=float, default=5.0)
    ap.add_argument("--maker-fee-bp", type=float, default=2.0)
    ap.add_argument("--impact-bp", type=float, default=1.0)
    ap.add_argument("--out", default="paper-results/live_paper_report.json")
    args=ap.parse_args()
    symbols=[s.strip().lower() for s in args.symbols.split(",") if s.strip()]
    states={s:SymbolState(s.upper(),args) for s in symbols}
    streams=[]
    for s in symbols: streams += [f"{s}@aggTrade",f"{s}@bookTicker",f"{s}@depth5@100ms"]
    url="wss://fstream.binance.com/stream?streams="+"/".join(streams)
    started=time.time(); deadline=started+args.minutes*60
    def on_message(ws, raw):
        try:
            msg=json.loads(raw); stream=msg.get("stream",""); d=msg.get("data",{})
            stream_l=stream.lower()
            sym=stream_l.split("@")[0]; st=states.get(sym)
            if not st: return
            if "@aggtrade" in stream_l:
                st.aggtrade_events += 1
                st.on_trade(d)
            elif "@bookticker" in stream_l:
                st.bookticker_events += 1
                st.on_book(d)
            elif "@depth5" in stream_l:
                st.depth_events += 1
                st.on_depth(d)
            else:
                st.unknown_streams[stream] += 1
                print(json.dumps({"event":"unknown_stream","stream":stream}),flush=True)
            st.events += 1
            st.maybe_signal(time.time())
            if time.time() >= deadline: ws.close()
        except Exception as e:
            for st in states.values(): st.parse_errors += 1
            print(json.dumps({"event":"parse_error","stream":msg.get("stream") if "msg" in locals() else None,
                              "error":str(e)}),flush=True)
    def on_error(ws, err): print(json.dumps({"event":"websocket_error","error":str(err)}),flush=True)
    def on_close(ws, code, msg): print(json.dumps({"event":"websocket_closed","code":code,"message":msg}),flush=True)
    def on_open(ws): print(json.dumps({"event":"websocket_connected","symbols":symbols,"started_at":utc()}),flush=True)
    signal.signal(signal.SIGTERM,stop_handler); signal.signal(signal.SIGINT,stop_handler)
    app=websocket.WebSocketApp(url,on_open=on_open,on_message=on_message,on_error=on_error,on_close=on_close)
    # Reconnects are bounded by total session deadline; preserve state within process.
    while not STOP and time.time()<deadline:
        app.run_forever(ping_interval=20,ping_timeout=10)
        if time.time()<deadline and not STOP: time.sleep(2)
    finished=time.time()
    report={"mode":"READ_ONLY_LIVE_PAPER_TRADING","exchange":"Binance USD-M Futures public WebSocket",
            "started_at":datetime.fromtimestamp(started,timezone.utc).isoformat(),
            "finished_at":datetime.fromtimestamp(finished,timezone.utc).isoformat(),
            "duration_seconds":finished-started,"symbols":{},
            "fixed_parameters":{"lookback_seconds":args.lookback,"hold_seconds":args.hold_seconds,
                "trade_imbalance_threshold":args.trade_threshold,"book_imbalance_threshold":args.book_threshold,
                "cooldown_seconds":args.cooldown,"taker_fee_bp_per_side":args.taker_fee_bp,
                "maker_fee_bp_per_side":args.maker_fee_bp,"impact_allowance_bp":args.impact_bp},
            "limitations":["No private account access or order placement.",
                "Maker fill is a conservative queue/trade-through proxy, not exact exchange queue reconstruction.",
                "Fee inputs are explicit scenarios; actual account fee tier may differ.",
                "Short observation windows do not establish profitability or out-of-sample robustness."]}
    for sym,st in states.items(): report["symbols"][sym]=st.snapshot()
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"event":"report_written","path":str(out),"symbols":{
        k:{"signals":v["signals"],"taker_trades":v["taker"]["closed_trades"],
           "taker_net_bp":v["taker"]["net_total_bp"],"maker_trades":v["maker"]["closed_trades"],
           "maker_net_bp":v["maker"]["net_total_bp"]} for k,v in report["symbols"].items()}},indent=2),flush=True)
    if not any(s.events for s in states.values()): sys.exit("No market data received; session invalid.")

if __name__=="__main__": main()
