import os
import time
import threading
import requests
import feedparser
from flask import Flask
from live_simulator import LivePaperEngine

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "7950965005:AAEUhM4c_UqF_XQkF50xQG9Z-0P0kS_qf84"
TELEGRAM_CHAT_ID = "6176503816"

WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]

NEWS_FEEDS = [
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "https://cointelegraph.com/rss",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.investing.com/rss/news_25.rss"
]

def send_telegram_msg(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

class TechnicalMarketScanner:
    """محرك فني يفحص الأسعار والزخم للدخول في صفقات يومية وسريعة"""
    def get_market_data(self, symbol):
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=20"
        try:
            res = requests.get(url, timeout=5).json()
            closes = [float(candle[4]) for candle in res]
            return closes
        except Exception:
            return []

    def scan_for_setups(self):
        signals = []
        for symbol in WATCHLIST:
            prices = self.get_market_data(symbol)
            if len(prices) < 15:
                continue
            
            current_price = prices[-1]
            prev_price = prices[-5]
            change_pct = ((current_price - prev_price) / prev_price) * 100

            # استراتيجية الزخم اللحظي واختراق المدى السعري
            if change_pct > 0.4:
                signals.append({
                    "asset": symbol,
                    "direction": "BUY",
                    "catalyst": f"زخم فني صاعد سريع (+{change_pct:.2f}%) على فريم 15 دقيقة",
                    "weight": 0.15
                })
            elif change_pct < -1.2:
                # ارتداد من تشبع بيعي
                signals.append({
                    "asset": symbol,
                    "direction": "BUY",
                    "catalyst": f"اقتناص ارتداد سعري بعد هبوط مؤقت ({change_pct:.2f}%)",
                    "weight": 0.12
                })
        return signals

class GlobalMacroResearcher:
    def __init__(self):
        self.seen_news = set()

    def scan_world_events(self):
        events = []
        for feed_url in NEWS_FEEDS:
            try:
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries[:5]:
                    title = entry.title.lower()
                    if entry.link not in self.seen_news:
                        self.seen_news.add(entry.link)
                        events.append(title)
            except Exception:
                continue
        return events

class MasterMacroBrain:
    def analyze_opportunities(self, events):
        signals = []
        for text in events:
            if any(w in text for w in ["war", "crisis", "bank", "inflation", "tensions", "oil", "gold"]):
                signals.append({"asset": "PAXGUSDT", "direction": "BUY", "catalyst": "تحوط كلي / توترات واضطرابات", "weight": 0.15})
                signals.append({"asset": "BTCUSDT", "direction": "BUY", "catalyst": "طلب سيولة وتحوط", "weight": 0.15})
            elif any(w in text for w in ["rate cut", "fed", "stimulus", "rally", "crypto", "surge", "gain"]):
                signals.append({"asset": "ETHUSDT", "direction": "BUY", "catalyst": "شهية مخاطرة وتوسع سيولة", "weight": 0.15})
                signals.append({"asset": "SOLUSDT", "direction": "BUY", "catalyst": "تسارع مضاربي على العملات البديلة", "weight": 0.15})
        return signals

def bot_worker_loop():
    engine = LivePaperEngine(initial_balance=100.0)
    researcher = GlobalMacroResearcher()
    brain = MasterMacroBrain()
    scanner = TechnicalMarketScanner()

    send_telegram_msg("🚀 تم تفعيل المحرك الهجومي النشط!\nالنظام الآن يضارب فنياً وإخبارياً على مدار اليوم والساعة.")

    loop_count = 0
    while True:
        try:
            # فحص الصفقات المفتوحة وأهداف الربح
            engine.check_open_positions(send_telegram_msg)

            # 1. فحص فني لحظي للأسعار (يعمل دائماً حتى بدون أخبار)
            tech_signals = scanner.scan_for_setups()
            for sig in tech_signals:
                engine.execute_simulated_trade(
                    asset=sig["asset"],
                    weight=sig["weight"],
                    catalyst=sig["catalyst"],
                    notifier=send_telegram_msg
                )

            # 2. فحص إخباري عالمي
            events = researcher.scan_world_events()
            if events:
                news_signals = brain.analyze_opportunities(events)
                for sig in news_signals:
                    engine.execute_simulated_trade(
                        asset=sig["asset"],
                        weight=sig["weight"],
                        catalyst=sig["catalyst"],
                        notifier=send_telegram_msg
                    )

            # إرسال تقرير حالة كل 4 ساعات (كل 240 دورة دقيقة)
            loop_count += 1
            if loop_count % 240 == 0:
                send_telegram_msg(f"📊 تقرير دوري:\nالبوت نشط ويعمل في مراقبة الأسواق.\nالرصيد المتاح: ${engine.balance:.2f}\nعدد الصفقات المفتوحة: {len(engine.open_positions)}")

            time.sleep(60)
        except Exception as e:
            print(f"Engine Loop Error: {e}")
            time.sleep(60)

@app.route('/')
def home():
    return "Active Scalper Bot Running 24/7", 200

worker_thread = threading.Thread(target=bot_worker_loop, daemon=True)
worker_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
