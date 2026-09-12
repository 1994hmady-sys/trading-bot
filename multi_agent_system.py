import os, json, time, math, threading, sys, random
from datetime import datetime, timezone, date
import requests, ccxt
import pandas as pd
import pandas_ta_classic as ta
from flask import Flask
from google import genai
from google.genai import types

# ==========================================
# AATA V7.9.2
# Paper Trading Validation Build
#
# Council:
# Hamida = CEO / Final Decision
# Claude = Architecture / Development
# ChatGPT = QA / Debugger
# Gemini = DevOps / Infrastructure
#
# V7.9.2 FIXES:
# 1. HARD Symbol Guard
# 2. Gemini daily request budget = 20
# 3. Controlled 429/503 handling
# 4. SDK automatic retry disabled
# 5. Real HTTP timeout = 60s
# 6. Gemini 3.6 Flash
# 7. Function response id=call.id
# 8. No orphaned threads
# ==========================================


# ==========================================
# CONFIG
# ==========================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "7106069536"

GEMINI_MODEL = "gemini-3.6-flash"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

GEMINI_HTTP_TIMEOUT_MS = 60000

# Free Tier validation budget
# Maximum actual Gemini HTTP requests allowed by AATA per UTC day.
GEMINI_DAILY_REQUEST_LIMIT = 20

# Controlled retry settings.
# IMPORTANT:
# 429 Daily Quota is NOT retried.
# 503 may be retried once if budget remains.
MAX_RETRIES = 1
BASE_BACKOFF_SEC = 2.0
MAX_JITTER_SEC = 1.0


if not GEMINI_API_KEY:
    print("FATAL: GEMINI_API_KEY is not set. AATA cannot function without it.")
    sys.exit(1)


# ==========================================
# GEMINI CLIENT
# ==========================================

# Disable SDK automatic retries.
# AATA owns the retry policy so we do not accidentally
# multiply requests and consume the free quota.
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
# APP / TRADING CONFIG
# ==========================================

app = Flask(__name__)

WATCHLIST = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT"
]

ALLOWED_SYMBOLS = frozenset(WATCHLIST)

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

VALID_DIRECTIONS = {"Long", "Short"}


# ==========================================
# GEMINI REQUEST BUDGET
# ==========================================

gemini_budget_lock = threading.RLock()

gemini_budget = {
    "date": datetime.now(timezone.utc).date().isoformat(),
    "used": 0,
    "limit": GEMINI_DAILY_REQUEST_LIMIT
}


def reset_gemini_budget_if_new_day():
    today = datetime.now(timezone.utc).date().isoformat()

    with gemini_budget_lock:
        if gemini_budget["date"] != today:
            gemini_budget["date"] = today
            gemini_budget["used"] = 0

            print(
                f"[Gemini Budget] New UTC day detected. "
                f"Budget reset to {GEMINI_DAILY_REQUEST_LIMIT}."
            )


def gemini_budget_remaining():
    reset_gemini_budget_if_new_day()

    with gemini_budget_lock:
        return max(
            0,
            gemini_budget["limit"] - gemini_budget["used"]
        )


def reserve_gemini_request():
    """
    Reserve exactly one Gemini HTTP request.

    Returns True if AATA is allowed to send.
    Returns False if the daily budget is exhausted.
    """

    reset_gemini_budget_if_new_day()

    with gemini_budget_lock:
        if gemini_budget["used"] >= gemini_budget["limit"]:
            return False

        gemini_budget["used"] += 1

        used = gemini_budget["used"]
        remaining = gemini_budget["limit"] - used

        print(
            f"[Gemini Budget] Request #{used}/"
            f"{gemini_budget['limit']} | "
            f"Remaining: {remaining}"
        )

        return True


def gemini_budget_status():
    reset_gemini_budget_if_new_day()

    with gemini_budget_lock:
        return {
            "date_utc": gemini_budget["date"],
            "used": gemini_budget["used"],
            "limit": gemini_budget["limit"],
            "remaining": max(
                0,
                gemini_budget["limit"] - gemini_budget["used"]
            )
        }


# ==========================================
# ERROR CLASS
# ==========================================

class GeminiBudgetExhausted(Exception):
    pass


# ==========================================
# GEMINI ERROR HELPERS
# ==========================================

def get_error_code(exc):
    """
    Prefer structured APIError.code when available.
    Fall back to conservative text detection.
    """

    code = getattr(exc, "code", None)

    if isinstance(code, int):
        return code

    if isinstance(code, str):
        try:
            return int(code)
        except Exception:
            pass

    text = str(exc)

    if "429" in text:
        return 429

    if "503" in text:
        return 503

    return None


def is_daily_quota_error(exc):
    text = str(exc).lower()

    quota_markers = [
        "generate_requests_per_day",
        "generaterequestsperday",
        "free_tier_requests",
        "daily quota",
        "quota exceeded for metric",
        "perdayperproject",
        "per_day"
    ]

    return any(marker in text for marker in quota_markers)


def is_transient_gemini_error(exc):
    code = get_error_code(exc)

    if code == 503:
        return True

    if code == 429 and not is_daily_quota_error(exc):
        return True

    return False


# ==========================================
# CONTROLLED GEMINI REQUEST
# ==========================================

def send_gemini_message(chat, message):
    """
    All Gemini requests MUST pass through this function.

    Guarantees:
    - Daily request budget
    - No unlimited retry
    - 429 Daily Quota is not retried
    - 503 may be retried once
    """

    attempts = 0

    while True:

        if not reserve_gemini_request():
            raise GeminiBudgetExhausted(
                f"Gemini daily request budget exhausted: "
                f"{GEMINI_DAILY_REQUEST_LIMIT}/"
                f"{GEMINI_DAILY_REQUEST_LIMIT}"
            )

        try:
            response = chat.send_message(message)

            status = gemini_budget_status()

            print(
                f"[Gemini] Request successful | "
                f"Used: {status['used']}/{status['limit']} | "
                f"Remaining: {status['remaining']}"
            )

            return response

        except Exception as e:

            code = get_error_code(e)

            # Daily quota = STOP.
            # Do not waste another request.
            if code == 429 and is_daily_quota_error(e):
                print(
                    "[Gemini] Daily quota reached. "
                    "No retry will be attempted."
                )
                raise

            # 400/401/403/404/etc = immediate failure.
            if not is_transient_gemini_error(e):
                raise

            # Limited transient retry.
            if attempts >= MAX_RETRIES:
                raise

            attempts += 1

            delay = (
                BASE_BACKOFF_SEC * (2 ** (attempts - 1))
                + random.uniform(0, MAX_JITTER_SEC)
            )

            print(
                f"[Gemini Retry] HTTP {code}. "
                f"Retry {attempts}/{MAX_RETRIES} "
                f"after {delay:.2f}s"
            )

            time.sleep(delay)


# ==========================================
# SYMBOL GUARD
# ==========================================

def validate_symbol(symbol):
    """
    HARD SECURITY BOUNDARY.

    Gemini may request any symbol,
    but AATA only permits WATCHLIST symbols.
    """

    if not isinstance(symbol, str):
        return False, {
            "ok": False,
            "error": "Invalid symbol type."
        }

    symbol = symbol.strip().upper()

    if symbol not in ALLOWED_SYMBOLS:
        return False, {
            "ok": False,
            "error": (
                f"Symbol '{symbol}' is NOT allowed. "
                f"Allowed symbols: {WATCHLIST}"
            )
        }

    return True, symbol


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
# MEMORY
# ==========================================

class MemoryCorruptedError(Exception):
    pass


class StructuredMemory:

    def __init__(self):
        self.path = "aata_memory.json"
        self.lock = threading.RLock()

        if not os.path.exists(self.path):
            self.write(self.default_state())


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

                with open(self.path, "r") as f:
                    return json.load(f)

            except Exception as e:

                raise MemoryCorruptedError(
                    f"ملف الذاكرة تالف: {e}"
                )


    def write(self, state):

        with self.lock:

            try:

                with open(self.path, "w") as f:
                    json.dump(
                        state,
                        f,
                        indent=2
                    )

            except Exception as e:

                print(
                    f"Memory write error: {e}"
                )


memory = StructuredMemory()


def safe_read_memory(context=""):

    try:

        return memory.read()

    except MemoryCorruptedError as e:

        send_telegram(
            f"🔴🔴 [خطأ حرج جداً]\n"
            f"{e}\n"
            f"السياق: {context}\n"
            f"تم إيقاف هذه الدورة لمنع فقدان بيانات المحفظة."
        )

        return None


# ==========================================
# TELEGRAM
# ==========================================

def send_telegram(msg):

    if not TELEGRAM_BOT_TOKEN:
        return

    try:

        requests.post(
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage",

            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg[:4000]
            },

            timeout=5
        )

    except Exception as e:

        print(
            f"Telegram error: {e}"
        )


# ==========================================
# SUPABASE LOGGING
# ==========================================

def log_to_supabase(action_type, details):

    if not SUPABASE_URL or not SUPABASE_KEY:

        print(
            "Supabase not configured, skipping log."
        )

        return

    try:

        endpoint = (
            f"{SUPABASE_URL}/rest/v1/trade_logs"
        )

        headers = {
            "apikey": SUPABASE_KEY,

            "Authorization":
                f"Bearer {SUPABASE_KEY}",

            "Content-Type":
                "application/json",

            "Prefer":
                "return=minimal"
        }

        payload = {
            "log_data": {
                "action": action_type,

                "details": details,

                "timestamp":
                    datetime.now(
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

        print(
            f"Supabase error: {e}"
        )


# ==========================================
# MARKET ENGINE
# ==========================================

class MarketEngine:

    def __init__(self):

        self.exchange = ccxt.mexc({
            "enableRateLimit": True
        })


    def snapshot(self, symbol):

        valid, result = validate_symbol(symbol)

        if not valid:

            print(
                f"[Symbol Guard] BLOCKED market request: "
                f"{symbol}"
            )

            return None

        symbol = result

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
                    f"NaN indicator for {symbol}"
                )

                return None

            return {
                "symbol": symbol,

                "price":
                    float(last["close"]),

                "rsi":
                    float(last["RSI"]),

                "ema20":
                    float(last["EMA20"]),

                "atr":
                    float(last["ATR"])
            }

        except Exception as e:

            print(
                f"Market snapshot error for "
                f"{symbol}: {e}"
            )

            return None


market = MarketEngine()


# ==========================================
# PORTFOLIO / RISK
# ==========================================

def unrealized_pnl(pos, current_price):

    if pos["direction"] == "Long":

        return (
            current_price - pos["entry"]
        ) * pos["qty"]

    return (
        pos["entry"] - current_price
    ) * pos["qty"]


def calculate_equity(state, market):

    equity = state["portfolio"]["cash"]

    data_complete = True

    for sym, pos in state["portfolio"]["positions"].items():

        snap = market.snapshot(sym)

        equity += pos["margin"]

        if snap:

            equity += unrealized_pnl(
                pos,
                snap["price"]
            )

        else:

            data_complete = False

    return equity, data_complete


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
            f"{drawdown_pct*100:.1f}% "
            f"من الذروة "
            f"(${peak:.2f}).\n"
            f"Equity الحالي: "
            f"${equity:.2f}\n"
            f"سقف المخاطرة انخفض إلى "
            f"{MAX_RISK_AFTER_DRAWDOWN*100:.0f}%."
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

        # HARD SYMBOL GUARD
        valid, result = validate_symbol(symbol)

        if not valid:

            return result

        symbol = result

        if direction not in VALID_DIRECTIONS:

            return {
                "ok": False,
                "error":
                    f"Invalid direction "
                    f"'{direction}'. Must be "
                    f"'Long' or 'Short'."
            }

        if symbol in state[
            "portfolio"
        ]["positions"]:

            return {
                "ok": False,
                "error": "Position exists"
            }

        requested_risk = float(risk_pct)

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
                "error":
                    "risk_pct is 0 - "
            
