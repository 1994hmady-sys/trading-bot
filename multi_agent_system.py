import time
import json
import os
import requests
import feedparser
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

TELEGRAM_BOT_TOKEN = "8849431477:AAEhJvZ9CK8lng3EEH3ujNgx5fhm6CD4_WQ"
TELEGRAM_CHAT_ID = "7106069536"

def send_alert(msg: str):
    if not TELEGRAM_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception:
        pass

# 1. Memory Agent
class MemoryAgent:
    def __init__(self, filename="trade_memory.json"):
        self.filename = filename
        if not os.path.exists(self.filename):
            with open(self.filename, 'w') as f:
                json.dump({"history": [], "lessons": []}, f)

    def record_closed_trade(self, trade_data: dict):
        with open(self.filename, 'r') as f:
            mem = json.load(f)
        mem["history"].append(trade_data)
        if trade_data.get("pnl", 0) < 0:
            mem["lessons"].append(f"خسارة في {trade_data['symbol']} بسبب حركة سريعة عكس الاتجاه.")
        with open(self.filename, 'w') as f:
            json.dump(mem, f, indent=2)

    def get_recent_performance(self):
        with open(self.filename, 'r') as f:
            return json.load(f)

# 2. Researcher Agent
class ResearcherAgent:
    def __init__(self):
        self.sources = [
            "https://feeds.content.dowjones.com/public/rss/mw_topstories",
            "https://cointelegraph.com/rss"
        ]

    def fetch_intel(self) -> str:
        headlines = []
        for url in self.sources:
            try:
                f = feedparser.parse(url)
                for entry in f.entries[:5]:
                    headlines.append(entry.title)
            except Exception:
                pass
        return " ".join(headlines)

    def get_price(self, symbol: str) -> float:
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            return float(requests.get(url, timeout=5).json()['price'])
        except Exception:
            defaults = {"BTCUSDT": 78000.0, "PAXGUSDT": 2500.0, "USDCUSDT": 1.0}
            return defaults.get(symbol, 100.0)

# 3. Brain & Opportunity Hunter
class BrainAgent:
    def analyze_macro(self, raw_news: str) -> Optional[dict]:
        text = raw_news.lower()
        # صائد فرص الذهب والسلع (أزمات، تضخم، حروب)
        if any(w in text for w in ["war", "conflict", "inflation", "crisis", "tension", "oil"]):
            return {
                "symbol": "PAXGUSDT",
                "asset_class": "Commodities/Gold",
                "thesis": "رصد توترات جيوسياسية أو مخاطر تضخم في الأسواق العالمية.",
                "sl_ratio": 0.015,
                "tp_ratio": 0.030
            }
        # صائد فرص الكريبتو والسيولة
        if any(w in text for w in ["rate cut", "liquidity", "etf", "fed", "stimulus"]):
            return {
                "symbol": "BTCUSDT",
                "asset_class": "Crypto",
                "thesis": "رصد مؤشرات إيجابية لتوسع السيولة النقدية العالمية.",
                "sl_ratio": 0.020,
                "tp_ratio": 0.045
            }
        return None

# 4. Quant Agent
class QuantAgent:
    def validate_setup(self, entry_price: float, opp: dict) -> dict:
        sl = entry_price * (1 - opp["sl_ratio"])
        tp = entry_price * (1 + opp["tp_ratio"])
        risk = entry_price - sl
        reward = tp - entry_price
        rr_ratio = reward / risk if risk > 0 else 0
        return {
            "entry": entry_price,
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "valid": rr_ratio >= 1.8,
            "rr_ratio": round(rr_ratio, 2)
        }

# 5. Risk Manager Agent
class RiskManagerAgent:
    def __init__(self, max_risk_per_trade=0.15, max_drawdown=0.10):
        self.max_risk_per_trade = max_risk_per_trade
        self.max_drawdown = max_drawdown

    def approve_trade(self, capital: float, total_portfolio: float, active_positions: dict, symbol: str) -> bool:
        if symbol in active_positions:
            return False
        if capital > (total_portfolio * self.max_risk_per_trade):
            return False
        return True

# 6. Portfolio Manager & Trader Agent
class PortfolioTraderEngine:
    def __init__(self, cash=100.0):
        self.cash = cash
        self.positions = {}
        self.memory = MemoryAgent()
        self.auditor = AuditorAgent()

    def total_value(self, researcher: ResearcherAgent) -> float:
        val = self.cash
        for s, pos in self.positions.items():
            val += pos["units"] * researcher.get_price(s)
        return val

    def execute_order(self, symbol: str, amount: float, setup: dict, thesis: str):
        entry = setup["entry"]
        units = amount / entry
        self.cash -= amount
        self.positions[symbol] = {
            "symbol": symbol,
            "units": units,
            "capital": amount,
            "entry_price": entry,
            "sl": setup["sl"],
            "tp": setup["tp"],
            "thesis": thesis
        }
        send_alert(
            f"🟢 *تنفيذ صفقة جديدة بواسطة الوكلاء*\n\n"
            f"🔹 *الأصل:* `{symbol}`\n"
            f"🧠 *التحليل:* {thesis}\n"
            f"💵 *المبلغ:* ${amount:.2f}\n"
            f"🎯 *الدخول:* ${entry:.2f} | *R:R:* {setup['rr_ratio']}\n"
            f"🛑 *الوقف:* ${setup['sl']:.2f} | 🚀 *الهدف:* ${setup['tp']:.2f}\n"
            f"💰 *الكاش المتبقي:* ${self.cash:.2f}"
        )

    def monitor(self, researcher: ResearcherAgent):
        for s in list(self.positions.keys()):
            pos = self.positions[s]
            curr = researcher.get_price(s)
            
            if curr >= pos["tp"]:
                self.close_position(s, curr, "Take Profit (تحقيق الهدف)", researcher)
            elif curr <= pos["sl"]:
                self.close_position(s, curr, "Stop Loss (ضرب الوقف)", researcher)

    def close_position(self, symbol: str, exit_price: float, reason: str, researcher: ResearcherAgent):
        pos = self.positions.pop(symbol)
        gross = pos["units"] * exit_price
        pnl = gross - pos["capital"]
        self.cash += gross

        trade_record = {
            "symbol": symbol,
            "entry": pos["entry_price"],
            "exit": exit_price,
            "pnl": round(pnl, 2),
            "reason": reason,
            "thesis": pos["thesis"]
        }
        self.memory.record_closed_trade(trade_record)
        self.auditor.audit_trade(trade_record, self.total_value(researcher))

# 7. Auditor Agent
class AuditorAgent:
    def audit_trade(self, trade: dict, current_total_portfolio: float):
        status = "🎯 صفقة رابحة" if trade["pnl"] > 0 else "🛑 صفقة خاسرة"
        msg = (
            f"📋 *تقرير المراجع المستقل (Auditor)*\n\n"
            f"🔹 *النتيجة:* {status} في `{trade['symbol']}`\n"
            f"📊 *صافي الربح/الخسارة:* ${trade['pnl']:+.2f}\n"
            f"🚪 *سعر الخروج:* ${trade['exit']:.2f}\n"
            f"💼 *إجمالي قيمة المحفظة:* ${current_total_portfolio:.2f}\n"
            f"💡 *التقييم:* تم توثيق العملية في الذاكرة لتطوير القرارات القادمة."
        )
        send_alert(msg)

# Main System Coordinator
def run_autonomous_ecosystem():
    researcher = ResearcherAgent()
    brain = BrainAgent()
    quant = QuantAgent()
    risk = RiskManagerAgent()
    engine = PortfolioTraderEngine(cash=100.0)

    send_alert("🧠 *تم إطلاق النظام البيئي المتكامل للوكلاء الذكاء الاصطناعي ($100 Paper)*\nيعمل الآن: Brain, Researcher, Quant, Risk, Portfolio, Trader, Auditor & Memory.")

    while True:
        try:
            intel = researcher.fetch_intel()
            opp = brain.analyze_macro(intel)

            if opp and risk.approve_trade(15.0, engine.total_value(researcher), engine.positions, opp["symbol"]):
                entry_p = researcher.get_price(opp["symbol"])
                setup = quant.validate_setup(entry_p, opp)

                if setup["valid"]:
                    engine.execute_order(opp["symbol"], 15.0, setup, opp["thesis"])

            engine.monitor(researcher)
        except Exception as e:
            pass

        time.sleep(60)

if __name__ == "__main__":
    run_autonomous_ecosystem()
