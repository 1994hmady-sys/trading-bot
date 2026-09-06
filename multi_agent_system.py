import os
import requests
import ccxt
from flask import Flask
from live_simulator import LivePaperEngine

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "8849431477:AAGVNZett1gWBikPg6fWJ4p2CJhQJxWEaaw"
TELEGRAM_CHAT_ID = "7106069536"
WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

def send_telegram_msg(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

class PrecisionSniperBrain:
    def __init__(self):
        self.exchange = ccxt.mexc({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })

    def get_klines(self, symbol, timeframe="5m", limit=35): # تم التحويل إلى 5 دقائق لسرعة الصفقات
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv: return [], []
            closes = [float(candle[4]) for candle in ohlcv]
            volumes = [float(candle[5]) for candle in ohlcv]
            return closes, volumes
        except Exception as e:
            return [], []

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1: return 50.0
        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            gains.append(diff if diff > 0 else 0)
            losses.append(abs(diff) if diff < 0 else 0)
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def calculate_ema(self, prices, period):
        if len(prices) < period: return prices[-1]
        k = 2 / (period + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = (p * k) + (ema * (1 - k))
        return ema

    def scan_sniper_setups(self):
        opportunities = []
        market_intel = []
        for symbol in WATCHLIST:
            clean_symbol = symbol.replace("/", "")
            closes, volumes = self.get_klines(symbol)
            
            if len(closes) < 20:
                market_intel.append(f"⚠️ {clean_symbol}: فشل جلب البيانات")
                continue
            
            current_price = closes[-1]
            rsi = self.calculate_rsi(closes, period=14)
            # متوسطات متحركة أسرع بكثير (5 و 15) للمضاربة
            ema_fast = self.calculate_ema(closes, period=5)
            ema_slow = self.calculate_ema(closes, period=15)

            market_intel.append(f"🔹 {clean_symbol}: ${current_price:,.2f} (RSI: {rsi:.1f})")

            # شروط الدخول السريع (المضاربة)
            if rsi < 45:
                opportunities.append({
                    "asset": clean_symbol, "direction": "BUY",
                    "catalyst": f"⚡ شراء مضاربة (RSI={rsi:.1f})", "weight": 0.15
                })
            elif ema_fast > ema_slow and closes[-2] <= ema_slow:
                opportunities.append({
                    "asset": clean_symbol, "direction": "BUY",
                    "catalyst": f"📈 تقاطع سريع صاعد", "weight": 0.15
                })
        return opportunities, market_intel

try:
    engine = LivePaperEngine(initial_balance=100.0)
except Exception:
    engine = None

sniper = PrecisionSniperBrain()
ping_count = 0

@app.route('/')
def home():
    global ping_count, engine
    if not engine: return "Engine Error", 500

    try:
        if hasattr(engine, 'check_open_positions'):
            engine.check_open_positions(send_telegram_msg)
        elif hasattr(engine, 'update_positions'):
            engine.update_positions(send_telegram_msg)

        setups, intel = sniper.scan_sniper_setups()
        for setup in setups:
            if hasattr(engine, 'execute_simulated_trade'):
                engine.execute_simulated_trade(
                    asset=setup["asset"], weight=setup["weight"],
                    catalyst=setup["catalyst"], notifier=send_telegram_msg
                )

        ping_count += 1
        if ping_count % 6 == 0:
            text = "\n".join([f"{x}" for x in intel])
            if not text.strip(): text = "لا توجد بيانات متاحة حالياً"
            
            bal = engine.balance if hasattr(engine, 'balance') else 100.0
            pos_len = len(engine.open_positions) if hasattr(engine, 'open_positions') else 0
            
            send_telegram_msg(
                f"⏱️ تقرير المضارب (كل 30 دقيقة):\n"
                f"الرصيد: ${bal:.2f}\n"
                f"الصفقات المفتوحة: {pos_len}\n\n"
                f"📊 نبض الأسواق (على فريم 5 دقائق):\n{text}"
            )
        return "OK", 200
    except Exception as e:
        send_telegram_msg(f"⚠️ خطأ غير متوقع: {str(e)}")
        return "Error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
