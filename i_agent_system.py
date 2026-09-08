import os, json, time, threading, math
from datetime import datetime, timezone
import requests, ccxt
import pandas as pd
import pandas_ta as ta
from flask import Flask
from google import genai
from google.genai import types

# ==========================================
# AATA V7.1 - Autonomous Adaptive Agent
# PAPER TRADING ONLY - ReAct Architecture
# ==========================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "7106069536"
GEMINI_MODEL = "gemini-2.5-flash"

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

app = Flask(__name__)
WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
INITIAL_CAPITAL = 100.0

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4000]}, timeout=5)
    except: pass

class StructuredMemory:
    def __init__(self):
        self.path = "aata_memory.json"
        self.lock = threading.Lock()
        if not os.path.exists(self.path): self.write(self.default_state())

    def default_state(self):
        return {"portfolio": {"cash": INITIAL_CAPITAL, "positions": {}}, "strategies": {}, "trade_history": []}

    def read(self):
        with self.lock:
            try:
                with open(self.path, "r") as f: return json.load(f)
            except: return self.default_state()

    def write(self, state):
        with self.lock:
            with open(self.path, "w") as f: json.dump(state, f, indent=2)

class MarketEngine:
    def __init__(self): self.exchange = ccxt.mexc({'enableRateLimit': True})
    def snapshot(self, symbol):
        try:
            df = pd.DataFrame(self.exchange.fetch_ohlcv(symbol, "15m", limit=50), columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["RSI"] = ta.rsi(df["close"], length=14)
            df["EMA20"] = ta.ema(df["close"], length=20)
            df["ATR"] = ta.atr(df["high"], df["low"], df["close"], length=14)
            last = df.iloc[-1]
            return {"symbol": symbol, "price": float(last["close"]), "rsi": float(last["RSI"]), "ema20": float(last["EMA20"]), "atr": float(last["ATR"])}
        except: return None

class PaperBroker:
    def __init__(self, memory, market):
        self.memory = memory
        self.market = market

    def open_position(self, state, symbol, direction, risk_pct, strategy):
        if symbol in state["portfolio"]["positions"]: return {"ok": False, "error": "Position exists"}
        snap = self.market.snapshot(symbol)
        if not snap: return {"ok": False, "error": "No market data"}
        
        price = snap["price"]
        risk_pct = max(0.01, min(0.25, float(risk_pct)))
        margin = state["portfolio"]["cash"] * risk_pct
        if margin <= 0: return {"ok": False, "error": "Insufficient cash"}
        
        qty = margin / price
        sl_dist = snap["atr"] * 2
        tp_dist = snap["atr"] * 3
        
        sl = price - sl_dist if direction == "Long" else price + sl_dist
        tp = price + tp_dist if direction == "Long" else price - tp_dist
        
        state["portfolio"]["cash"] -= margin
        state["portfolio"]["positions"][symbol] = {"entry": price, "qty": qty, "margin": margin, "direction": direction, "sl": sl, "tp": tp, "strategy": strategy}
        return {"ok": True, "symbol": symbol, "direction": direction, "entry": price, "sl": sl, "tp": tp}

    def close_position(self, state, symbol, reason):
        if symbol not in state["portfolio"]["positions"]: return {"ok": False, "error": "No open position"}
        pos = state["portfolio"]["positions"][symbol]
        snap = self.market.snapshot(symbol)
        if not snap: return {"ok": False, "error": "No market data"}
        
        price = snap["price"]
        if pos["direction"] == "Long": pnl = (price - pos["entry"]) * pos["qty"]
        else: pnl = (pos["entry"] - price) * pos["qty"]
        
        state["portfolio"]["cash"] += (pos["margin"] + pnl)
        state["trade_history"].append({"symbol": symbol, "strategy": pos["strategy"], "pnl": pnl, "reason": reason})
        del state["portfolio"]["positions"][symbol]
        return {"ok": True, "pnl": pnl}

memory = StructuredMemory()
market = MarketEngine()
broker = PaperBroker(memory, market)

# --- AATA TOOLS (Function Declarations) ---
def get_portfolio_state() -> dict:
    """Fetch current cash and open positions."""
    return memory.read()["portfolio"]

def get_market_snapshot(symbol: str) -> dict:
    """Get latest price, RSI, EMA, and ATR for a symbol."""
    return {"ok": True, "data": market.snapshot(symbol)}

def get_trade_history(limit: int = 5) -> dict:
    """Review past closed trades to learn from mistakes."""
    history = memory.read().get("trade_history", [])[-limit:]
    return {"ok": True, "trades": history}

def open_position(symbol: str, direction: str, risk_pct: float, strategy: str) -> dict:
    """Open a new Paper trade (Long or Short). risk_pct between 0.01 and 0.25"""
    state = memory.read()
    res = broker.open_position(state, symbol, direction, risk_pct, strategy)
    if res.get("ok"): memory.write(state)
    return res

def close_position(symbol: str, reason: str) -> dict:
    """Close an existing open position."""
    state = memory.read()
    res = broker.close_position(state, symbol, reason)
    if res.get("ok"): memory.write(state)
    return res

def wait(reason: str) -> dict:
    """Decide not to trade and wait for better conditions."""
    return {"ok": True, "action": "WAIT", "reason": reason}

tools_map = {
    "get_portfolio_state": get_portfolio_state,
    "get_market_snapshot": get_market_snapshot,
    "get_trade_history": get_trade_history,
    "open_position": open_position,
    "close_position": close_position,
    "wait": wait
}

# --- AATA Core Loop ---
def run_agent_cycle():
    sys_inst = "أنت AATA، وكيل تداول ذكي. افحص المحفظة والسوق باستخدام الأدوات. تعلم من الصفقات السابقة. لا تتسرع. استخدم أدواتك لاتخاذ قرار (فتح، إغلاق، أو انتظار)."
    try:
        chat = client.chats.create(
            model=GEMINI_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=sys_inst,
                tools=list(tools_map.values()),
                temperature=0.2
            )
        )
        
        response = chat.send_message("ابدأ دورة السوق الحالية واستخدم أدواتك للقرار.")
        step = 0
        while response.function_calls and step < 4:
            step += 1
            for call in response.function_calls:
                fn_name = call.name
                fn_args = {k: v for k, v in call.args.items()} if call.args else {}
                fn = tools_map.get(fn_name)
                
                result = fn(**fn_args) if fn else {"error": "Tool not found"}
                
                if fn_name in ["open_position", "close_position"]:
                    send_telegram(f"⚡ [AATA Action]\nTool: {fn_name}\nArgs: {fn_args}\nResult: {result}")
                
                response = chat.send_message(types.Part.from_function_response(name=fn_name, response={"result": result}))
    except Exception as e:
        print(f"Agent Loop Error: {e}")

ping = 0
def main_loop():
    global ping
    while True:
        try:
            # Auto SL/TP Check
            state = memory.read()
            for sym, pos in list(state["portfolio"]["positions"].items()):
                snap = market.snapshot(sym)
                if snap:
                    cp = snap["price"]
                    if (pos["direction"] == "Long" and (cp <= pos["sl"] or cp >= pos["tp"])) or \
                       (pos["direction"] == "Short" and (cp >= pos["sl"] or cp <= pos["tp"])):
                        res = broker.close_position(state, sym, "Auto SL/TP")
                        memory.write(state)
                        send_telegram(f"🛑 [Auto Close]\nSymbol: {sym}\nPnL: ${res.get('pnl', 0):.2f}")
            
            run_agent_cycle()
            ping += 1
            if ping % 20 == 0:
                s = memory.read()
                send_telegram(f"📊 [AATA V7.1 System]\nAlive & Monitoring.\nCash: ${s['portfolio']['cash']:.2f}")
        except: pass
        time.sleep(180)

threading.Thread(target=main_loop, daemon=True).start()

@app.route('/')
def home(): return "AATA V7.1 Active!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
