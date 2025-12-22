#!/usr/bin/env python3
"""
FAI-QUANT-SUPERIOR: Sistema di Trading Overnight su FIB
Esecuzione: Ogni giorno feriale a 19:00 CET
Invia segnali di trading al Telegram
"""

import os
import logging
import asyncio
import json
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np
from pytz import timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingSystem:
    def __init__(self):
        self.telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        if not self.telegram_bot_token or not self.telegram_chat_id:
            raise ValueError("Missing Telegram credentials")
    
    def get_market_data(self):
        try:
            url = 'https://query1.finance.yahoo.com/v10/finance/quoteSummary/%5EFTSEMIB'
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                logger.info("Market data fetched")
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return None
    
    def calculate_signals(self, market_data):
        if not market_data:
            return None
        try:
            signals = {
                'timestamp': datetime.now(timezone('Europe/Rome')).isoformat(),
                'strategy': 'FAI-QUANT-SUPERIOR',
                'instruments': [],
                'risk_level': 'medium',
                'recommendation': 'neutral'
            }
            hour = datetime.now(timezone('Europe/Rome')).hour
            if 19 <= hour <= 21:
                signals['recommendation'] = 'buy'
                signals['instruments'].append({
                    'symbol': 'FIB1!',
                    'action': 'BUY',
                    'entry': 'Market',
                    'stop_loss': '-100',
                    'take_profit': '+150'
                })
            return signals
        except Exception as e:
            logger.error(f"Error calculating signals: {e}")
            return None
    
    async def send_telegram_signal(self, signal):
        if not signal:
            return False
        try:
            message = self._format_telegram_message(signal)
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {'chat_id': self.telegram_chat_id, 'text': message, 'parse_mode': 'HTML'}
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Signal sent to Telegram")
                return True
            return False
        except Exception as e:
            logger.error(f"Error sending Telegram: {e}")
            return False
    
    def _format_telegram_message(self, signal):
        message = f"""<b>FAI-QUANT-SUPERIOR</b>
<b>Ora:</b> {signal['timestamp']}
<b>Raccomandazione:</b> {signal['recommendation'].upper()}
"""
        if signal['instruments']:
            for instr in signal['instruments']:
                message += f"\n{instr['symbol']}: {instr['action']}"
        return message
    
    async def run(self):
        logger.info("=" * 50)
        logger.info("FAI-QUANT-SUPERIOR - Started")
        logger.info("=" * 50)
        market_data = self.get_market_data()
        signal = self.calculate_signals(market_data)
        if signal:
            await self.send_telegram_signal(signal)
        logger.info("Cycle complete")

async def main():
    try:
        system = TradingSystem()
        await system.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
