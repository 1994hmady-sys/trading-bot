import time
import requests
import feedparser
from datetime import datetime
from live_simulator import LivePaperEngine

TELEGRAM_BOT_TOKEN = "7950965005:AAEUhM4c_UqF_XQkF50xQG9Z-0P0kS_qf84"
TELEGRAM_CHAT_ID = "6176503816"

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
            # محرك الملاذات الآمنة والأزمات الجيوسياسية / البنوك
            if any(w in text for w in ["war", "conflict", "crisis", "bank collapse", "inflation surge", "escalation", "tensions"]):
                signals.append({"asset": "PAXGUSDT", "direction": "BUY", "catalyst": "ملاذ آمن / توترات واضطرابات كبرى", "weight": 0.20})
                signals.append({"asset": "BTCUSDT", "direction": "BUY", "catalyst": "تحوط ضد النظام المالي والسيولة", "weight": 0.15})
            
            # محرك النمو وتخفيض الفائدة وضخ السيولة
            elif any(w in text for w in ["rate cut", "fed eases", "liquidity", "stimulus", "bullish", "rally", "growth"]):
                signals.append({"asset": "ETHUSDT", "direction": "BUY", "catalyst": "توسع السيولة العالمية وأصول المخاطرة", "weight": 0.15})
                signals.append({"asset": "SOLUSDT", "direction": "BUY", "catalyst": "زخم المضاربة السريعة والتوسع التقني", "weight": 0.15})
                signals.append({"asset": "BTCUSDT", "direction": "BUY", "catalyst": "انخفاض الفائدة وضعف مؤشر الدولار", "weight": 0.20})
                
            # صدمات الطاقة والأسواق
            elif any(w in text for w in ["oil spike", "energy shortage", "sanctions", "trade war"]):
                signals.append({"asset": "PAXGUSDT", "direction": "BUY", "catalyst": "صدمة تضخم سلع وطاقة", "weight": 0.15})
        return signals

def main():
    engine = LivePaperEngine(initial_balance=100.0)
    researcher = GlobalMacroResearcher()
    brain = MasterMacroBrain()

    send_telegram_msg("⚡ تم تفعيل العقل الاقتصادي الشامل 24/7\nتم ربط الأسواق، المؤشرات، البنوك، الطاقة، والمعادن بالسيرفر السحابي.")

    while True:
        try:
            engine.check_open_positions(send_telegram_msg)
            events = researcher.scan_world_events()
            if events:
                opportunities = brain.analyze_opportunities(events)
                for opp in opportunities:
                    engine.execute_simulated_trade(
                        asset=opp["asset"],
                        weight=opp["weight"],
                        catalyst=opp["catalyst"],
                        notifier=send_telegram_msg
                    )
            time.sleep(60)
        except Exception as e:
            print(f"Engine Loop Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
