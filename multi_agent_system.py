cat << 'EOF' > multi_agent_system.py
import os, json, time, math, threading, sys, random
from datetime import datetime, timezone

import requests
import ccxt
import pandas as pd
import pandas_ta_classic as ta
from flask import Flask
from google import genai
from google.genai import types


# ==========================================
# AATA V7.9.2
# Controlled Gemini Transient Error Retry
#
# FIXES:
# 1. No ThreadPoolExecutor
# 2. Real Gemini HTTP timeout = 60 seconds
# 3. SDK internal retry disabled
# 4. AATA handles ONLY 429 / 503
# 5. Maximum 2 extra retries
# 6. Exponential backoff: 2s -> 4s
# 7. Small jitter
# 8. Gemini 3 function call IDs preserved
#
# NO changes to:
# - PaperBroker
# - Risk logic
# - SL/TP
# - Memory
# - MEXC logic
# ==========================================


# ==========================================
# CONFIGURATION
# ==========================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "7106069536"

GEMINI_MODEL = "gemini-3.6-flash"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Real HTTP timeout
GEMINI_HTTP_TIMEOUT_MS = 60000


# ==========================================
# FAIL FAST
# ==========================================

if not GEMINI_API_KEY:
    print(
        "FATAL: GEMINI_API_KEY is not set. "
        "AATA cannot function without it. Exiting."
    )
    sys.exit(1)


# ==========================================
# GEMINI CLIENT
#
# IMPORTANT:
# SDK automatic retry is disabled.
# AATA controls retry itself for 429/503 only.
# ==========================================

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(
        timeout=GEMINI_HTTP_TIMEOUT_MS,
        retry_options=types.HttpRetryOptions(
            attempts=1,
            http_status_codes=[]
        )
    )
)


# ==========================================
# FLASK
# ==========================================

app = Flask(__name__)


# ==========================================
# TRADING CONFIG
# ==========================================

WATCHLIST = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT"
]

INITIAL_CAPITAL = 100.0

DRAWDOWN_WARN_PCT = 0.5

MAX_RISK_NORMAL = 0.25
MAX_RISK_AFTER_DRAWDOWN = 0.05

MIN_RISK_FLOOR = 0.001


# ==========================================
# EMOTIONAL SYSTEM
# ==========================================

EMOTIONAL_START = 100
EMOTIONAL_MIN = 0
EMOTIONAL_MAX = 200

WIN_SMALL = 3
WIN_BIG = 8

LOSS_SMALL = -3
LOSS_BIG = -8


# ==========================================
# GEMINI RETRY SETTINGS
# ==========================================

MAX_RETRIES = 2

BASE_BACKOFF_SEC = 2.0

MAX_JITTER_SEC = 1.0


# ==========================================
# BASIC HELPERS
# ==========================================

VALID_DIRECTIONS = {
    "Long",
    "Short"
}


class MemoryCorruptedError(Exception):
    pass


# ==========================================
# EMOTIONAL STATE
# ==========================================

def emotional_state_and_multiplier(score):

    if score >= 150:
        return "Euphoria (نشوة)", 0.5

    elif score >= 115:
        return "Confidence (ثقة)", 0.85

    elif score >= 70:
        return "Neutral (متوازن)", 1.0

    elif score >= 30:
        return "Caution (حذر)", 0.6

    else:
        return "Frustration (إحباط)", 0.4


# ==========================================
# TELEGRAM
# ==========================================

def send_telegram(msg):

    if not TELEGRAM_BOT_TOKEN:
        return

    try:

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg[:4000]
            },
            timeout=5
        )

    except Exception as e:

        print(f"Telegram error: {e}")


# ==========================================
# SUPABASE LOGGING
# ==========================================

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

        payload = {
            "log_data": {
                "action": action_type,
                "details": details,
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat()
            }
        }

        r = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=5
        )

        if r.status_code >= 300:

            print(
                f"Supabase log failed: "
                f"{r.status_code} {r.text}"
            )

    except Exception as e:

        print(f"Supabase error: {e}")


# ==========================================
# STRUCTURED MEMORY
# ==========================================

class StructuredMemory:

    def __init__(self):

        self.path = "aata_memory.json"

        self.lock = threading.RLock()

        if not os.path.exists(self.path):

            self.write(
                self.default_state()
            )


    def default_state(self):

        return {
            "portfolio": {
                "cash": INITIAL_CAPITAL,
                "positions": {}
            },

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

                with open(
                    self.path,
                    "r"
                ) as f:

                    return json.load(f)

            except Exception as e:

                raise MemoryCorruptedError(
                    f"ملف الذاكرة تالف: {e}"
                )


    def write(self, state):

        with self.lock:

            try:

                with open(
                    self.path,
                    "w"
                ) as f:

                    json.dump(
                        state,
                        f,
                        indent=2
                    )

            except Exception as e:

                print(
                    f"Memory write error: {e}"
                )


# ==========================================
# SAFE MEMORY READ
# ==========================================

def safe_read_memory(context=""):

    try:

        return memory.read()

    except MemoryCorruptedError as e:

        send_telegram(
            f"🔴🔴 [خطأ حرج جداً]\n"
            f"{e}\n"
            f"السياق: {context}\n"
            f"تم إيقاف هذه الدورة لمنع فقدان بيانات المحفظة. "
            f"يتطلب تدخل يدوي فوري!"
        )

        return None


# ==========================================
# MARKET ENGINE
# ==========================================

class MarketEngine:

    def __init__(self):

        self.exchange = ccxt.mexc({
            "enableRateLimit": True
        })


    def snapshot(self, symbol):

        try:

            df = pd.DataFrame(
                self.exchange.fetch_ohlcv(
                    symbol,
                    "15m",
                    limit=50
                ),
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume"
                ]
            )

            df["RSI"] = ta.rsi(
                df["close"],
                length=14
            )

            df["EMA20"] = ta.ema(
                df["close"],
                length=20
            )

            df["ATR"] = ta.atr(
                df["high"],
                df["low"],
                df["close"],
                length=14
            )

            last = df.iloc[-1]

            if (
                pd.isna(last["RSI"])
                or
                pd.isna(last["ATR"])
                or
                pd.isna(last["EMA20"])
            ):

                print(
                    f"Snapshot warning: "
                    f"NaN indicator for {symbol}, skipping."
                )

                return None


            return {
                "symbol": symbol,
                "price": float(last["close"]),
                "rsi": float(last["RSI"]),
                "ema20": float(last["EMA20"]),
                "atr": float(last["ATR"])
            }


        except Exception as e:

            print(
                f"Market snapshot error for "
                f"{symbol}: {e}"
            )

            return None


# ==========================================
# PNL
# ==========================================

def unrealized_pnl(pos, current_price):

    if pos["direction"] == "Long":

        return (
            current_price - pos["entry"]
        ) * pos["qty"]

    return (
        pos["entry"] - current_price
    ) * pos["qty"]


# ==========================================
# EQUITY
# ==========================================

def calculate_equity(state, market):

    equity = state["portfolio"]["cash"]

    data_complete = True

    for sym, pos in state[
        "portfolio"
    ]["positions"].items():

        equity += pos["margin"]

        snap = market.snapshot(sym)

        if snap:

            equity += unrealized_pnl(
                pos,
                snap["price"]
            )

        else:

            data_complete = False


    return equity, data_complete


# ==========================================
# EMOTIONAL SCORE
# ==========================================

def update_emotional_score(
    state,
    pnl,
    margin_used
):

    score = state.get(
        "emotional_score",
        EMOTIONAL_START
    )

    pnl_pct = (
        pnl / margin_used
        if margin_used > 0
        else 0
    )

    if pnl > 0:

        delta = (
            WIN_BIG
            if pnl_pct >= 0.05
            else WIN_SMALL
        )

    else:

        delta = (
            LOSS_BIG
            if pnl_pct <= -0.05
            else LOSS_SMALL
        )

    score = max(
        EMOTIONAL_MIN,
        min(
            EMOTIONAL_MAX,
            score + delta
        )
    )

    state["emotional_score"] = score

    return score


# ==========================================
# DRAWDOWN PROTECTION
# ==========================================

def check_drawdown_protection(
    state,
    market
):

    equity, data_complete = calculate_equity(
        state,
        market
    )

    if not data_complete:

        print(
            "Drawdown check skipped this cycle: "
            "incomplete market data."
        )

        return equity, None


    if equity > state.get(
        "peak_equity",
        INITIAL_CAPITAL
    ):

        state["peak_equity"] = equity


    peak = state["peak_equity"]

    drawdown_pct = (
        (peak - equity) / peak
        if peak > 0
        else 0
    )


    if (
        drawdown_pct >= DRAWDOWN_WARN_PCT
        and
        state.get("risk_mode") != "reduced"
    ):

        state["risk_mode"] = "reduced"

        send_telegram(
            f"⚠️ [Drawdown Protection]\n"
            f"Equity هبط "
            f"{drawdown_pct * 100:.1f}% "
            f"من الذروة "
            f"(${peak:.2f}).\n"
            f"Equity الحالي: "
            f"${equity:.2f}\n"
            f"سقف المخاطرة انخفض إلى "
            f"{MAX_RISK_AFTER_DRAWDOWN * 100:.0f}%."
        )

        log_to_supabase(
            "DRAWDOWN_PROTECTION_TRIGGERED",
            {
                "equity": equity,
                "peak_equity": peak
            }
        )


    elif (
        drawdown_pct < DRAWDOWN_WARN_PCT
        and
        state.get("risk_mode") == "reduced"
    ):

        state["risk_mode"] = "normal"

        send_telegram(
            f"✅ [Drawdown Protection متعطل]\n"
            f"Equity تعافى إلى "
            f"${equity:.2f}."
        )

        log_to_supabase(
            "DRAWDOWN_PROTECTION_RECOVERED",
            {
                "equity": equity,
                "peak_equity": peak
            }
        )


    return equity, drawdown_pct


# ==========================================
# EFFECTIVE RISK
# ==========================================

def get_effective_max_risk(state):

    base_max = (
        MAX_RISK_AFTER_DRAWDOWN
        if state.get("risk_mode") == "reduced"
        else MAX_RISK_NORMAL
    )

    score = state.get(
        "emotional_score",
        EMOTIONAL_START
    )

    state_name, multiplier = (
        emotional_state_and_multiplier(score)
    )

    return (
        base_max * multiplier,
        state_name,
        score
    )


# ==========================================
# PAPER BROKER
# ==========================================

class PaperBroker:

    def __init__(
        self,
        memory,
        market
    ):

        self.memory = memory
        self.market = market


    def open_position(
        self,
        state,
        symbol,
        direction,
        risk_pct,
        strategy
    ):

        if direction not in VALID_DIRECTIONS:

            return {
                "ok": False,
                "error": (
                    f"Invalid direction "
                    f"'{direction}'. "
                    f"Must be 'Long' or 'Short'."
                )
            }


        if symbol in state[
            "portfolio"
        ]["positions"]:

            return {
                "ok": False,
                "error": "Position exists"
            }


        try:

            requested_risk = float(
                risk_pct
            )

        except Exception:

            return {
                "ok": False,
                "error": "Invalid risk_pct"
            }


        if (
            not math.isfinite(
                requested_risk
            )
            or
            requested_risk < 0
        ):

            return {
                "ok": False,
                "error": "Invalid risk_pct"
            }


        if requested_risk == 0:

            return {
                "ok": False,
                "error": (
                    "risk_pct is 0 - "
                    "no position will be opened. "
                    "Use wait() if you intend not to trade."
                )
            }


        check_drawdown_protection(
            state,
            self.market
        )


        snap = self.market.snapshot(
            symbol
        )

        if not snap:

            return {
                "ok": False,
                "error": "No market data"
            }


        effective_max, emo_state, emo_score = (
            get_effective_max_risk(state)
        )


        applied_risk = max(
            MIN_RISK_FLOOR,
            min(
                effective_max,
                requested_risk
            )
        )


        price = snap["price"]

        margin = (
            state["portfolio"]["cash"]
            * applied_risk
        )


        if margin <= 0:

            return {
                "ok": False,
                "error": "Insufficient cash"
            }


        qty = margin / price

        sl_dist = snap["atr"] * 2

        tp_dist = snap["atr"] * 3


        sl = (
            price - sl_dist
            if direction == "Long"
            else price + sl_dist
        )


        tp = (
            price + tp_dist
            if direction == "Long"
            else price - tp_dist
        )


        state["portfolio"]["cash"] -= margin


        pos_data = {
            "entry": price,
            "qty": qty,
            "margin": margin,
            "direction": direction,
            "sl": sl,
            "tp": tp,
            "strategy": strategy
        }


        state[
            "portfolio"
        ]["positions"][symbol] = pos_data


        log_to_supabase(
            "OPEN_POSITION",
            {
                "symbol": symbol,
                "position": pos_data,
                "requested_risk": requested_risk,
                "applied_risk": applied_risk
            }
        )


        note = ""

        if applied_risk < requested_risk:

            note = (
                f" (قُلّص إلى "
                f"{applied_risk * 100:.1f}% "
                f"بسبب حالة: {emo_state})"
            )


        return {
            "ok": True,
            "symbol": symbol,
            "direction": direction,
            "entry": price,
            "sl": sl,
            "tp": tp,
            "risk_pct_used": applied_risk,
            "note": note
        }


    def close_position(
        self,
        state,
        symbol,
        reason
    ):

        if symbol not in state[
            "portfolio"
        ]["positions"]:

            return {
                "ok": False,
                "error": "No open position"
            }


        pos = state[
            "portfolio"
        ]["positions"][symbol]


        snap = self.market.snapshot(
            symbol
        )


        if not snap:

            return {
                "ok": False,
                "error": "No market data"
            }


        price = snap["price"]

        pnl = unrealized_pnl(
            pos,
            price
        )


        state["portfolio"]["cash"] += (
            pos["margin"] + pnl
        )


        trade_record = {
            "symbol": symbol,
            "strategy": pos["strategy"],
            "pnl": pnl,
            "reason": reason
        }


        state[
            "trade_history"
        ].append(trade_record)


        del state[
            "portfolio"
        ]["positions"][symbol]


        new_score = update_emotional_score(
            state,
            pnl,
            pos["margin"]
        )


        equity, drawdown_pct = (
            check_drawdown_protection(
                state,
                self.market
            )
        )


        trade_record[
            "equity_after"
        ] = equity

        trade_record[
            "emotional_score_after"
        ] = new_score

        trade_record[
            "equity_data_complete"
        ] = (
            drawdown_pct is not None
        )


        log_to_supabase(
            "CLOSE_POSITION",
            trade_record
        )


        return {
            "ok": True,
            "pnl": pnl,
            "equity_after": equity,
            "emotional_score_after": new_score
        }


# ==========================================
# GLOBAL OBJECTS
# ==========================================

memory = StructuredMemory()

market = MarketEngine()

broker = PaperBroker(
    memory,
    market
)


# ==========================================
# GEMINI TOOLS
# ==========================================

def get_portfolio_state() -> dict:

    state = safe_read_memory(
        "get_portfolio_state"
    )

    if state is None:

        return {
            "ok": False,
            "error": "Memory corrupted"
        }


    equity, data_complete = (
        calculate_equity(
            state,
            market
        )
    )


    effective_max, emo_state, emo_score = (
        get_effective_max_risk(
            state
        )
    )


    portfolio = dict(
        state["portfolio"]
    )


    portfolio["equity"] = equity

    portfolio[
        "equity_data_complete"
    ] = data_complete

    portfolio[
        "risk_mode"
    ] = state.get(
        "risk_mode",
        "normal"
    )

    portfolio[
        "emotional_score"
    ] = emo_score

    portfolio[
        "emotional_state"
    


