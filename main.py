import time
import requests
import feedparser
from live_simulator import LivePaperEngine, send_telegram_alert

class EconomicBrain:
    def __init__(self):
        # مصادر الأخبار الاقتصادية والجيوسياسية المباشرة
        self.feeds = [
            "https://feeds.content.dowjones.com/public/rss/mw_topstories",
            "https://cointelegraph.com/rss"
        ]

    def get_market_news(self):
        headlines = []
        for url in self.feeds:
            try:
                f = feedparser.parse(url)
                for entry in f.entries[:6]:
                    headlines.append(entry.title)
            except Exception:
                pass
        return headlines

    def analyze_and_hunt_opportunities(self, engine: LivePaperEngine):
        headlines = self.get_market_news()
        all_text = " ".join(headlines).lower()

        # 1. تحليل الذهب والمعادن (الأزمات، التضخم، الحروب)
        if any(k in all_text for k in ["war", "conflict", "inflation", "crisis", "tension", "middle east"]):
            if "PAXGUSDT" not in engine.positions:
                price = engine.get_live_price("PAXGUSDT")
                send_telegram_alert(
                    "🧠 *تحليل اقتصادي جديد*\n"
                    "🔍 *السبب:* رصد توترات جيوسياسية/تضخم في الأخبار العالمية.\n"
                    "💡 *القرار:* الدخول في الذهب (PAXG) كملاذ آمن."
                )
                engine.open_trade("PAXGUSDT", 15.0, price * 0.985, price * 1.025)

        # 2. تحليل الكريبتو والسيولة (خفض الفائدة، سيولة البنوك المركزية)
        if any(k in all_text for k in ["rate cut", "fed", "liquidity", "etf approval", "institutional"]):
            if "BTCUSDT" not in engine.positions:
                price = engine.get_live_price("BTCUSDT")
                send_telegram_alert(
                    "🧠 *تحليل اقتصادي جديد*\n"
                    "🔍 *السبب:* تحسن مؤشرات السيولة وخفض الفائدة عالمياً.\n"
                    "💡 *القرار:* الدخول في البيتكوين (BTC) للاستفادة من الزخم."
                )
                engine.open_trade("BTCUSDT", 15.0, price * 0.98, price * 1.03)

def main():
    engine = LivePaperEngine(initial_balance=100.0)
    brain = EconomicBrain()

    send_telegram_alert("🚀 *بدء تشغيل المستثمر الاقتصادي الذكي*\nيراقب الآن الأخبار والسياسة والأسواق لاتخاذ القرارات.")
    print("Agent is monitoring global events & market prices...")

    while True:
        # فحص الأخبار والبحث عن فرص اقتصادية
        brain.analyze_and_hunt_opportunities(engine)
        
        # متابعة الصفقات المفتوحة مع حركة السوق الحقيقية
        engine.sync_market_and_check_exits()
        
        # تكرار دورة المراقبة كل 60 ثانية
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
