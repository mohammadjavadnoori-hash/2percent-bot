import telebot
import requests
import os
from threading import Thread
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

BLACKLIST = ["USDT","USDC","BUSD","DAI","TUSD","FDUSD","USDD","FRAX","GUSD"]

# --- دریافت داده از Binance API (برای اندیکاتورهای 1h)
def get_klines(symbol, interval="1h", limit=100):
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        data = requests.get(url, params=params, timeout=10).json()
        return [[float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])] for c in data]  # o,h,l,c,v
    except:
        return []

# --- محاسبه EMA
def ema(values, period):
    import numpy as np
    v = np.array(values)
    return float(np.mean(v[-period:])) if len(v) >= period else values[-1]

# --- محاسبه MACD
def macd(close_prices):
    import numpy as np
    exp1 = np.convolve(close_prices, np.ones(12)/12, mode='valid')
    exp2 = np.convolve(close_prices, np.ones(26)/26, mode='valid')
    macd_line = exp1[-len(exp2):] - exp2
    signal = np.convolve(macd_line, np.ones(9)/9, mode='valid')
    return macd_line[-1], signal[-1] if len(signal)>0 else 0

# --- SuperTrend ساده
def supertrend(high, low, close, period=10, multiplier=3):
    atr = sum([h - l for h,l in zip(high[-period:], low[-period:])]) / period
    upper = (sum(high[-period:]) + sum(low[-period:])) / (2*period) + multiplier * atr
    lower = (sum(high[-period:]) + sum(low[-period:])) / (2*period) - multiplier * atr
    return "green" if close[-1] > lower else "red"

# --- دریافت 100 کوین برتر از CoinGecko
def get_top_coins():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/markets", 
                        params={"vs_currency":"usd","order":"volume_desc","per_page":100,"page":1}, timeout=15)
        return r.json()
    except: return []

# --- اسکن اصلی
def scan_coins():
    coins = get_top_coins()
    signals = []
    for coin in coins[:50]:  # فقط 50 تا اول برای سرعت
        symbol = coin['symbol'].upper() + "USDT"
        if any(b in symbol for b in BLACKLIST): continue
        if coin['total_volume'] < 120_000_000: continue
        
        # RSI روزانه (از CoinGecko)
        try:
            hist = requests.get(f"https://api.coingecko.com/api/v3/coins/{coin['id']}/market_chart", 
                               params={"vs_currency":"usd","days":30}, timeout=10).json()
            prices = [p[1] for p in hist['prices'][-30:]]
            delta = [prices[i]-prices[i-1] for i in range(1,len(prices))]
            gain = sum(max(d,0) for d in delta[-14:]) / 14
            loss = sum(abs(min(d,0)) for d in delta[-14:]) / 14
            rsi = round(100 - (100/(1 + (gain/loss if loss else 99))), 2)
        except: rsi = 50
        
        if not (47.5 <= rsi <= 52.5): continue
        
        # داده 1h از Binance
        klines = get_klines(symbol.replace("/",""))
        if len(klines) < 55: continue
        closes = [k[3] for k in klines]
        highs = [k[1] for k in klines]
        lows = [k[2] for k in klines]
        volumes = [k[4] for k in klines]
        
        # EMA Ribbon
        ema8 = ema(closes, 8)
        ema21 = ema(closes, 21)
        ema55 = ema(closes, 55)
        price = closes[-1]
        
        # Volume Spike
        avg_vol = sum(volumes[-20:]) / 20
        vol_spike = volumes[-1] > avg_vol * 1.5
        
        # MACD
        macd_line, signal_line = macd(closes)
        macd_bull = macd_line > signal_line
        
        # SuperTrend
        st_color = supertrend(highs, lows, closes)
        
        # همه شرط‌ها
        if (price > ema8 > ema21 > ema55 and 
            vol_spike and 
            macd_bull and 
            st_color == "green"):
            
            entry = price
