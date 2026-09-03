import os
import time
import threading
import requests
from flask import Flask
from live_simulator import LivePaperEngine

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "7950965005:AAEUhM4c_UqF_XQkF50xQG9Z-0P0kS_qf84"
TELEGRAM_CHAT_ID = "6176503816"

WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]

def send_telegram_msg(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[Telegram Error] {e}")

class PrecisionSniperBrain:
    """محرك تحليلي متقدم يدمج RSI والمتوسطات المتحركة ونبض السيولة"""
    
    def get_klines(self, symbol, interval="15m", limit=35):
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        try:
            res = requests.get(url, timeout=6).json()
            closes = [float(k[4]) for k in res]
            highs = [float(k[2]) for k in res]
            lows = [float(k[3]) for k in res]
            volumes = [float(k[5]) for k in res]
            return closes, highs, lows, volumes
        except Exception:
            return [], [], [], []

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i - 1]
            gains.append(diff if diff > 0 else 0)
            losses.append(abs(diff) if diff < 0 else 0)
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def calculate_ema(self, prices, period):
        if len(prices) < period:
            return prices[-1]
        k = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = (price * k) + (ema * (1 - k))
        return ema

    def scan_sniper_setups(self):
        opportunities = []
        market_intel = []

        for symbol in WATCHLIST:
            closes, highs, lows, volumes = self.get_klines(symbol)
            if len(closes) < 25:
                continue

            current_price = closes[-1]
            rsi = self.calculate_rsi(closes, period=14)
            ema_fast = self.calculate_ema(closes, period=9)
            ema_slow = self.calculate_ema(closes, period=21)
            vol_avg = sum(volumes[-10:]) / 10
            vol_spike = volumes[-1] > (vol_avg * 1.3)

            status_note = f"{symbol}: ${current_price:,.2f} | RSI: {rsi:.1f}"
            market_intel.append(status_note)

            # --- استراتيجية القناص 1: ارتداد من تشبع بيعي حاد مع دخول سيولة ---
            if rsi < 32 and current_price > closes[-2]:
                opportunities.append({
                    "asset": symbol,
                    "direction": "BUY",
                    "catalyst": f"🎯 قنص تشبع بيعي عميق (RSI={rsi:.1f}) مع ارتداد وانعكاس إيجابي",
                    "weight": 0.12
                })

            # --- استراتيجية القناص 2: اختراق ذهبي مع انفجار حجم التداول ---
            elif ema_fast > ema_slow and closes[-2] <= ema_slow and vol_spike and rsi > 52:
                opportunities.append({
                    "asset": symbol,
                    "direction": "BUY",
                    "catalyst": f"⚡ اختراق تريند مؤسسي صاعد مدعوم بحجم تداول ضخم (RSI={rsi:.1f})",
                    "weight": 0.15
                })

        return opportunities, market_intel

def bot_worker_loop():
    time.sleep(5)
    send_telegram_msg("🧠 تم تفعيل عقلية القناص الذكي (Precision Sniper AI)!\nالوضع: فلترة عميقة للفرص عالية الاحتمالية والربح السريع فقط.")

    try:
        engine = LivePaperEngine(initial_balance=100.0)
    except Exception as e:
        print(f"[Init Error] {e}")
        return

    sniper = PrecisionSniperBrain()
    loop_count = 0

    while True:
        try:
            # 1. متابعة الصفقات وجني الأرباح فور الوصول للهدف
            engine.check_open_positions(send_telegram_msg)

            # 2. فحص قناص فائق الدقة
            setups, intel = sniper.scan_sniper_setups()

            for setup in setups:
                engine.execute_simulated_trade(
                    asset=setup["asset"],
                    weight=setup["weight"],
                    catalyst=setup["catalyst"],
                    notifier=send_telegram_msg
                )

            # 3. تقرير دوري ذكي كل 30 دقيقة لطمأنتك ومتابعة التحليل
            loop_count += 1
            if loop_count % 30 == 0:
                summary_text = "\n".join([f"• {line}" for line in intel])
                send_telegram_msg(
                    f"🎯 تقرير القناص الدوري (رصد السوق):\n"
                    f"السيولة المتاحة: ${engine.balance:.2f}\n"
                    f"الصفقات المفتوحة: {len(engine.open_positions)}\n\n"
                    f"📈 مؤشرات الأصول الحالية:\n{summary_text}\n\n"
                    f"الحالة: في وضع التربص لاقتناص الفرص عالية الدقة."
                )

            time.sleep(60)
        except Exception as e:
            print(f"[Loop Exception] {e}")
            time.sleep(60)

@app.route('/')
def home():
    return "Institutional Sniper AI Active 24/7", 200

worker_thread = threading.Thread(target=bot_worker_loop, daemon=True)
worker_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
