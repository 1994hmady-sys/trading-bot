import os, json, time, math, threading, sys
from datetime import datetime, timezone
import requests, ccxt
import pandas as pd
import pandas_ta_classic as ta
from flask import Flask
from google import genai
from google.genai import types

# ==========================================
# AATA V7.9.1 - Real HTTP Timeout (no orphaned threads)
# Council Approved: Claude (Code) + ChatGPT (QA) + Gemini (DevOps) + Hamida (CEO)
# ==========================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "7106069536"
GEMINI_MODEL = "gemini-3.6-flash"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

GEMINI_HTTP_TIMEOUT_MS = 60000  # 60 ثانية - timeout حقيقي على مستوى الطلب نفسه

if not GEMINI_API_KEY:
    print("FATAL: GEMINI_API_KEY is not set. AATA cannot function without it. Exiting.")
    sys.exit(1)

# --- Fix #2: HTTP timeout حقيقي على مستوى الاتصال ---
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=GEMINI_HTTP_TIMEOUT_MS)
)

app = Flask(__name__)
WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
INITIAL_CAPITAL = 100.0

DRAWDOWN_WARN_PCT = 0.5
MAX_RISK_NORMAL = 0.25
MAX_RISK_AFTER_DRAWDOWN = 0.05
MIN_RISK_FLOOR = 0.001

EMOTIONAL_START = 100
EMOTIONAL_MIN = 0
EMOTIONAL_MAX = 200
WIN_SMALL, WIN_BIG = 3, 8
LOSS_SMALL, LOSS_BIG = -3, -8

def emotional_state_and_multiplier(score):
    if score >= 150:   return "Euphoria (نشوة)", 0.5
    elif score >= 115: return "Confidence (ثقة)", 0.85
    elif score >= 70:  return "Neutral (متوازن)", 1.0
    elif score >= 30:  return "Caution (حذر)", 0.6
    else:              return "Frustration (إحباط)", 0.4

VALID_DIRECTIONS = {"Long", "Short"}

class MemoryCorruptedError(Exception):
    pass

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4000]}, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")

def log_to_supabase(action_type, details):
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase not configured, skipping log.")
        return
    try:
        endpoint = f"{SUPABASE_URL}/rest/v1/trade_logs"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        payload = {"log_data": {"action": action_type, "details": details,
                                 "timestamp": datetime.now(timezone.utc).isoformat()}}
        r = requests.post(endpoint, headers=headers, json=payload, timeout=5)
        if r.status_code >= 300:
            print(f"Supabase log failed: {r.status_code} {r.text}")
    except Exception as e:
        print(f"Supabase error: {e}")

class StructuredMemory:
    def __init__(self):
        self.path = "aata_memory.json"
        self.lock = threading.RLock()
        if not os.path.exists(self.path):
            self.write(self.default_state())

    def default_state(self):  
        return {  
            "portfolio": {"cash": INITIAL_CAPITAL, "positions": {}},  
            "strategies": {},  
            "trade_history": [],  
            "risk_mode": "normal",  
            "peak_equity": INITIAL_CAPITAL,  
            "emotional_score": EMOTIONAL_START  
        }  

    def read(self):  
        with self.lock:  
            if not os.path.exists(self.path):  
                return self.default_state()  
            try:  
                with open(self.path, "r") as f:  
                    return json.load(f)  
            except Exception as e:  
                raise MemoryCorruptedError(f"ملف الذاكرة تالف: {e}")  

    def write(self, state):  
        with self.lock:  
            try:  
                with open(self.path, "w") as f: json.dump(state, f, indent=2)  
            except Exception as e:  
                print(f"Memory write error: {e}")

def safe_read_memory(context=""):
    try:
        return memory.read()
    except MemoryCorruptedError as e:
        send_telegram(f"🔴🔴 [خطأ حرج جداً] {e}\nالسياق: {context}\n"
                      f"تم إيقاف هذه الدورة لمنع فقدان بيانات المحفظة. يتطلب تدخل يدوي فوري!")
        return None

class MarketEngine:
    def __init__(self): self.exchange = ccxt.mexc({'enableRateLimit': True})
    def snapshot(self, symbol):
        try:
            df = pd.DataFrame(self.exchange.fetch_ohlcv(symbol, "15m", limit=50),
                               columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["RSI"] = ta.rsi(df["close"], length=14)
            df["EMA20"] = ta.ema(df["close"], length=20)
            df["ATR"] = ta.atr(df["high"], df["low"], df["close"], length=14)
            last = df.iloc[-1]
            if pd.isna(last["RSI"]) or pd.isna(last["ATR"]) or pd.isna(last["EMA20"]):
                print(f"Snapshot warning: NaN indicator for {symbol}, skipping.")
                return None
            return {"symbol": symbol, "price": float(last["close"]), "rsi": float(last["RSI"]),
                     "ema20": float(last["EMA20"]), "atr": float(last["ATR"])}
        except Exception as e:
            print(f"Market snapshot error for {symbol}: {e}")
            return None

def unrealized_pnl(pos, current_price):
    if pos["direction"] == "Long":
        return (current_price - pos["entry"]) * pos["qty"]
    return (pos["entry"] - current_price) * pos["qty"]

def calculate_equity(state, market):
    equity = state["portfolio"]["cash"]
    data_complete = True
    for sym, pos in state["portfolio"]["positions"].items():
        equity += pos["margin"]
        snap = market.snapshot(sym)
        if snap:
            equity += unrealized_pnl(pos, snap["price"])
        else:
            data_complete = False
    return equity, data_complete

def update_emotional_score(state, pnl, margin_used):
    score = state.get("emotional_score", EMOTIONAL_START)
    pnl_pct = (pnl / margin_used) if margin_used > 0 else 0
    if pnl > 0:
        delta = WIN_BIG if pnl_pct >= 0.05 else WIN_SMALL
    else:
        delta = LOSS_BIG if pnl_pct <= -0.05 else LOSS_SMALL
    score = max(EMOTIONAL_MIN, min(EMOTIONAL_MAX, score + delta))
    state["emotional_score"] = score
    return score

def check_drawdown_protection(state, market):
    equity, data_complete = calculate_equity(state, market)
    if not data_complete:
        print("Drawdown check skipped this cycle: incomplete market data.")
        return equity, None
    if equity > state.get("peak_equity", INITIAL_CAPITAL):
        state["peak_equity"] = equity
    peak = state["peak_equity"]
    drawdown_pct = (peak - equity) / peak if peak > 0 else 0

    if drawdown_pct >= DRAWDOWN_WARN_PCT and state.get("risk_mode") != "reduced":  
        state["risk_mode"] = "reduced"  
        send_telegram(f"⚠️ [Drawdown Protection]\nEquity هبط {drawdown_pct*100:.1f}% من الذروة (${peak:.2f}).\n"  
                      f"Equity الحالي: ${equity:.2f}\nسقف المخاطرة انخفض إلى {MAX_RISK_AFTER_DRAWDOWN*100:.0f}%.")  
        log_to_supabase("DRAWDOWN_PROTECTION_TRIGGERED", {"equity": equity, "peak_equity": peak})  
    elif drawdown_pct < DRAWDOWN_WARN_PCT and state.get("risk_mode") == "reduced":  
        state["risk_mode"] = "normal"  
        send_telegram(f"✅ [Drawdown Protection متعطل]\nEquity تعافى إلى ${equity:.2f}.")  
        log_to_supabase("DRAWDOWN_PROTECTION_RECOVERED", {"equity": equity, "peak_equity": peak})  

    return equity, drawdown_pct

def get_effective_max_risk(state):
    base_max = MAX_RISK_AFTER_DRAWDOWN if state.get("risk_mode") == "reduced" else MAX_RISK_NORMAL
    score = state.get("emotional_score", EMOTIONAL_START)
    state_name, multiplier = emotional_state_and_multiplier(score)
    return base_max * multiplier, state_name, score

class PaperBroker:
    def __init__(self, memory, market):
        self.memory = memory
        self.market = market

    def open_position(self, state, symbol, direction, risk_pct, strategy):  
        if direction not in VALID_DIRECTIONS:  
            return {"ok": False, "error": f"Invalid direction '{direction}'. Must be 'Long' or 'Short'."}  
        if symbol in state["portfolio"]["positions"]:  
            return {"ok": False, "error": "Position exists"}  

        requested_risk = float(risk_pct)  
        if not math.isfinite(requested_risk) or requested_risk < 0:  
            return {"ok": False, "error": "Invalid risk_pct"}  
        if requested_risk == 0:  
            return {"ok": False, "error": "risk_pct is 0 - no position will be opened. Use wait() if you intend not to trade."}  

        check_drawdown_protection(state, self.market)  

        snap = self.market.snapshot(symbol)  
        if not snap: return {"ok": False, "error": "No market data"}  

        effective_max, emo_state, emo_score = get_effective_max_risk(state)  
        applied_risk = max(MIN_RISK_FLOOR, min(effective_max, requested_risk))  

        price = snap["price"]  
        margin = state["portfolio"]["cash"] * applied_risk  
        if margin <= 0: return {"ok": False, "error": "Insufficient cash"}  

        qty = margin / price  
        sl_dist = snap["atr"] * 2  
        tp_dist = snap["atr"] * 3  
        sl = price - sl_dist if direction == "Long" else price + sl_dist  
        tp = price + tp_dist if direction == "Long" else price - tp_dist  

        state["portfolio"]["cash"] -= margin  
        pos_data = {"entry": price, "qty": qty, "margin": margin, "direction": direction,  
                    "sl": sl, "tp": tp, "strategy": strategy}  
        state["portfolio"]["positions"][symbol] = pos_data  

        log_to_supabase("OPEN_POSITION", {"symbol": symbol, "position": pos_data,  
                                          "requested_risk": requested_risk, "applied_risk": applied_risk})  

        note = ""  
        if applied_risk < requested_risk:  
            note = f" (قُلّص إلى {applied_risk*100:.1f}% بسبب حالة: {emo_state})"  
        return {"ok": True, "symbol": symbol, "direction": direction, "entry": price, "sl": sl, "tp": tp,  
                "risk_pct_used": applied_risk, "note": note}  

    def close_position(self, state, symbol, reason):  
        if symbol not in state["portfolio"]["positions"]:  
            return {"ok": False, "error": "No open position"}  
        pos = state["portfolio"]["positions"][symbol]  
        snap = self.market.snapshot(symbol)  
        if not snap: return {"ok": False, "error": "No market data"}  

        price = snap["price"]  
        pnl = unrealized_pnl(pos, price)  
        state["portfolio"]["cash"] += (pos["margin"] + pnl)  
        trade_record = {"symbol": symbol, "strategy": pos["strategy"], "pnl": pnl, "reason": reason}  
        state["trade_history"].append(trade_record)  
        del state["portfolio"]["positions"][symbol]  

        new_score = update_emotional_score(state, pnl, pos["margin"])  
        equity, drawdown_pct = check_drawdown_protection(state, self.market)  

        trade_record["equity_after"] = equity  
        trade_record["emotional_score_after"] = new_score  
        trade_record["equity_data_complete"] = (drawdown_pct is not None)  
        log_to_supabase("CLOSE_POSITION", trade_record)  
        return {"ok": True, "pnl": pnl, "equity_after": equity, "emotional_score_after": new_score}

memory = StructuredMemory()
market = MarketEngine()
broker = PaperBroker(memory, market)

def get_portfolio_state() -> dict:
    state = safe_read_memory("get_portfolio_state")
    if state is None:
        return {"ok": False, "error": "Memory corrupted"}
    equity, data_complete = calculate_equity(state, market)
    effective_max, emo_state, emo_score = get_effective_max_risk(state)
    portfolio = dict(state["portfolio"])
    portfolio["equity"] = equity
    portfolio["equity_data_complete"] = data_complete
    portfolio["risk_mode"] = state.get("risk_mode", "normal")
    portfolio["emotional_score"] = emo_score
    portfolio["emotional_state"] = emo_state
    portfolio["max_risk_allowed_now"] = effective_max
    portfolio["note"] = f"حالتك الحالية: {emo_state}. الحد الأقصى المسموح الآن: {effective_max*100:.1f}%."
    return portfolio

def get_market_snapshot(symbol: str) -> dict: return {"ok": True, "data": market.snapshot(symbol)}

def get_trade_history(limit: int) -> dict:
    state = safe_read_memory("get_trade_history")
    if state is None: return {"ok": False, "error": "Memory corrupted"}
    return {"ok": True, "trades": state.get("trade_history", [])[-limit:]}

def open_position(symbol: str, direction: str, risk_pct: float, strategy: str) -> dict:
    state = safe_read_memory("open_position")
    if state is None: return {"ok": False, "error": "Memory corrupted"}
    res = broker.open_position(state, symbol, direction, risk_pct, strategy)
    memory.write(state)
    return res

def close_position(symbol: str, reason: str) -> dict:
    state = safe_read_memory("close_position")
    if state is None: return {"ok": False, "error": "Memory corrupted"}
    res = broker.close_position(state, symbol, reason)
    memory.write(state)
    return res

def wait(reason: str) -> dict:
    log_to_supabase("WAIT", {"reason": reason})
    return {"ok": True, "action": "WAIT", "reason": reason}

tools_map = {
    "get_portfolio_state": get_portfolio_state,
    "get_market_snapshot": get_market_snapshot,
    "get_trade_history": get_trade_history,
    "open_position": open_position,
    "close_position": close_position,
    "wait": wait
}

gemini_failure_count = 0

def run_agent_cycle():
    """لا executor، لا thread منفصل - الـ HTTP timeout الحقيقي (client.http_options) هو ما يضمن
    أن الطلب نفسه لن يتعلق أكثر من GEMINI_HTTP_TIMEOUT_MS، فيرفع استثناءً طبيعياً يلتقطه try/except هنا."""
    global gemini_failure_count
    sys_inst = ("أنت AATA، وكيل تداول ذكي. افحص المحفظة والسوق باستخدام الأدوات. تعلم من الصفقات السابقة. "
                "لا تتسرع. استخدم أدواتك لاتخاذ قرار (فتح، إغلاق، أو انتظار). "
                "النظام يفرض حدوداً صارمة على المخاطرة بناءً على حالتك العاطفية الرقمية وأداء المحفظة - "
                "هذه الحدود غير قابلة للتفاوض ولا يمكنك تجاوزها.")
    try:
        chat = client.chats.create(model=GEMINI_MODEL,
                                   config=types.GenerateContentConfig(system_instruction=sys_inst,
                                                                      tools=list(tools_map.values()),
                                                                      temperature=0.2))
        response = chat.send_message("ابدأ دورة السوق الحالية واستخدم أدواتك للقرار.")
        step = 0
        while response.function_calls and step < 4:
            step += 1
            function_response_parts = []
            for call in response.function_calls:
                fn_name = call.name
                fn_args = {k: v for k, v in call.args.items()} if call.args else {}
                fn = tools_map.get(fn_name)
                result = fn(**fn_args) if fn else {"error": "Tool not found"}
                if fn_name in ["open_position", "close_position"]:
                    send_telegram(f"⚡ [AATA Action]\nTool: {fn_name}\nArgs: {fn_args}\nResult: {result}")
                # --- Fix #4: id=call.id مطلوب رسمياً في Gemini 3 لمطابقة النتيجة بالطلب الصحيح ---
                function_response_parts.append(
                    types.Part.from_function_response(name=fn_name, response={"result": result}, id=call.id)
                )
            response = chat.send_message(function_response_parts)
        gemini_failure_count = 0
    except Exception as e:
        gemini_failure_count += 1
        print(f"Agent Loop Error: {e}")
        if gemini_failure_count == 3:
            send_telegram(f"🔴 [تحذير] فشل الوكيل 3 مرات متتالية.\nآخر خطأ: {e}")

ping = 0
def main_loop():
    global ping
    while True:
        try:
            state = safe_read_memory("main_loop SL/TP check")
            if state is None:
                time.sleep(180)
                continue

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
                s = safe_read_memory("periodic report")  
                if s:  
                    equity, data_complete = calculate_equity(s, market)  
                    effective_max, emo_state, emo_score = get_effective_max_risk(s)  
                    mode = "🟢 عادي" if s.get("risk_mode") != "reduced" else "🟡 مخفّض"  
                    send_telegram(f"📊 [AATA V7.9.1]\nCash: ${s['portfolio']['cash']:.2f}\nEquity: ${equity:.2f}\n"  
                                 f"Peak: ${s.get('peak_equity', INITIAL_CAPITAL):.2f}\nRisk Mode: {mode}\n"  
                                 f"Emotional: {emo_state} (Score: {emo_score})")  
        except Exception as e:  
            print(f"Main loop error: {e}")  
        time.sleep(180)

threading.Thread(target=main_loop, daemon=True).start()

@app.route('/')
def home(): return "AATA V7.9.1 - Real HTTP Timeout, No Orphaned Threads!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
