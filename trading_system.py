#!/usr/bin/env python3
"""
FAI-QUANT-SUPERIOR: Sistema di Trading Overnight su FIB
Esecuzione: Ogni giorno feriale a 19:00 CET
Invia segnali di trading via Email
"""
import os
import sys
import logging
import smtplib
import json
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import pandas as pd
import numpy as np
from pytz import timezone

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EmailNotificationError(Exception):
    """Custom exception for email notification errors"""
    pass

class TradingSystem:
    def __init__(self):
        """Initialize trading system with email credentials"""
        self.smtp_host = os.environ.get('SMTP_HOST')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.smtp_user = os.environ.get('SMTP_USER')
        self.smtp_pass = os.environ.get('SMTP_PASS')
        self.email_to = os.environ.get('EMAIL_TO', 'pioggiamarrone@gmail.com')
        self.email_from_name = os.environ.get('EMAIL_FROM_NAME', 'FAI-QUANT-SUPERIOR')
        self.github_run_id = os.environ.get('GITHUB_RUN_ID', 'N/A')
        self.github_server_url = os.environ.get('GITHUB_SERVER_URL', 'https://github.com')
        self.github_repository = os.environ.get('GITHUB_REPOSITORY', 'SLartax/FAI-QUANT-SUPERIOR')
        self.tz_rome = timezone('Europe/Rome')
        self.tz_utc = timezone('UTC')
        
        # Validate required secrets
        self._validate_secrets()
    
    def _validate_secrets(self):
        """Validate that all required secrets are set"""
        required_secrets = {
            'SMTP_HOST': self.smtp_host,
            'SMTP_PORT': self.smtp_port,
            'SMTP_USER': self.smtp_user,
            'SMTP_PASS': self.smtp_pass,
        }
        missing = [k for k, v in required_secrets.items() if not v]
        if missing:
            error_msg = f"FATAL: Missing required secrets: {', '.join(missing)}. Check GitHub Secrets configuration."
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.info(f"Secrets validated. Email will be sent to: {self.email_to}")
    
    def _log_time_info(self):
        """Log current time in both UTC and Europe/Rome timezone"""
        now_utc = datetime.now(self.tz_utc)
        now_rome = datetime.now(self.tz_rome)
        dow_rome = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][now_rome.weekday()]
        logger.info(f"UTC Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"Rome Time: {now_rome.strftime('%Y-%m-%d %H:%M:%S %Z')} ({dow_rome})")
        return now_utc, now_rome
    
    def get_market_data(self):
        """Fetch FTSE MIB market data from Yahoo Finance"""
        try:
            logger.info("Fetching FTSE MIB market data...")
            url = 'https://query1.finance.yahoo.com/v10/finance/quoteSummary/%5EFTSEMIB'
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.info("Market data fetched successfully")
                return data
            else:
                logger.warning(f"Yahoo Finance returned status {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            logger.error("Timeout fetching market data (10s)")
            return None
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return None
    
    def calculate_signals(self, market_data):
        """Calculate trading signals based on market data"""
        now_rome = datetime.now(self.tz_rome)
        
        try:
            signals = {
                'timestamp_utc': datetime.now(self.tz_utc).isoformat(),
                'timestamp_rome': now_rome.isoformat(),
                'strategy': 'FAI-QUANT-SUPERIOR',
                'instrument': 'FTSE MIB (FIB1!)',
                'last_candle': None,
                'reference_price': None,
                'signal': 'FLAT',
                'reason': 'Market data unavailable or insufficient',
                'risk_level': 'medium'
            }
            
            # If no market data, return FLAT signal
            if not market_data:
                logger.warning("No market data available - returning FLAT signal")
                return signals
            
            # Attempt to extract price data
            try:
                price = market_data.get('quoteSummary', {}).get('result', [{}])[0].get('regularMarketPrice', {}).get('raw')
                if price:
                    signals['reference_price'] = price
                    signals['last_candle'] = now_rome.strftime('%Y-%m-%d %H:%M')
                    logger.info(f"Reference price extracted: {price}")
            except (IndexError, KeyError, TypeError):
                logger.warning("Could not extract price from market data")
            
            # Simple trading logic based on hour (example)
            hour = now_rome.hour
            if 19 <= hour < 21:
                signals['signal'] = 'BUY'
                signals['reason'] = 'Market hours 19:00-21:00 CET - BUY signal triggered'
                logger.info("BUY signal generated")
            else:
                signals['signal'] = 'FLAT'
                signals['reason'] = f'Current hour {hour}:00 Rome time - no active signal'
                logger.info("FLAT signal (outside active hours)")
            
            return signals
        except Exception as e:
            logger.error(f"Error calculating signals: {e}")
            signals['reason'] = f'Error during calculation: {str(e)}'
            return signals
    
    def send_email(self, signal):
        """Send email notification with signal
        
        Args:
            signal (dict): Trading signal dict
        
        Returns:
            bool: True if sent successfully, False otherwise
        
        Raises:
            EmailNotificationError: On SMTP errors
        """
        if not signal:
            logger.error("No signal provided to send_email()")
            return False
        
        try:
            # Build subject
            now_rome = datetime.fromisoformat(signal['timestamp_rome']).astimezone(self.tz_rome)
            subject = f"FAI-QUANT-SUPERIOR — {signal['signal']} — {now_rome.strftime('%Y-%m-%d %H:%M')} Europe/Rome"
            
            # Build HTML body
            html_body = self._build_email_body(signal)
            
            # Create email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.email_from_name} <{self.smtp_user}>"
            msg['To'] = self.email_to
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send via SMTP
            logger.info(f"Connecting to SMTP: {self.smtp_host}:{self.smtp_port}")
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                logger.info("TLS connection established")
                server.login(self.smtp_user, self.smtp_pass)
                logger.info(f"Authenticated as {self.smtp_user}")
                server.send_message(msg)
                logger.info(f"Email sent successfully to {self.email_to}")
            
            return True
        
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication failed: {e} - Check SMTP_USER and SMTP_PASS")
            raise EmailNotificationError(f"SMTP auth failed: {e}")
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            raise EmailNotificationError(f"SMTP error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise EmailNotificationError(f"Email send failed: {e}")
    
    def _build_email_body(self, signal):
        """Build HTML email body
        
        Args:
            signal (dict): Trading signal dict
        
        Returns:
            str: HTML email body
        """
        now_rome = datetime.fromisoformat(signal['timestamp_rome']).astimezone(self.tz_rome)
        run_url = f"{self.github_server_url}/{self.github_repository}/actions/runs/{self.github_run_id}" if self.github_run_id != 'N/A' else "N/A"
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .header {{ background-color: #2c3e50; color: white; padding: 15px; border-radius: 5px; }}
                .signal {{ font-size: 24px; font-weight: bold; color: 
        {'#27ae60' if signal['signal'] == 'BUY' else '#e74c3c' if signal['signal'] == 'SELL' else '#95a5a6'}; }}
                .info {{ margin: 15px 0; }}
                .label {{ font-weight: bold; }}
                .footer {{ font-size: 12px; color: #7f8c8d; margin-top: 20px; border-top: 1px solid #ecf0f1; padding-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>FAI-QUANT-SUPERIOR</h1>
                <p>Trading System - FTSE MIB Overnight</p>
            </div>
            
            <div class="info">
                <p><span class="label">Strumento:</span> {signal['instrument']}</p>
                <p><span class="label">Data/Ora (Europe/Rome):</span> {now_rome.strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="info">
                <p><span class="label">Segnale:</span> <span class="signal">{signal['signal']}</span></p>
            </div>
            
            <div class="info">
                <p><span class="label">Prezzo di riferimento:</span> {signal['reference_price'] if signal['reference_price'] else 'N/A'}</p>
                <p><span class="label">Ultima candela disponibile:</span> {signal['last_candle'] if signal['last_candle'] else 'N/A'}</p>
            </div>
            
            <div class="info">
                <p><span class="label">Regola del segnale:</span> {signal['reason']}</p>
            </div>
            
            <div class="footer">
                <p><span class="label">Run GitHub Actions:</span> <a href="{run_url}">{self.github_run_id}</a></p>
                <p><span class="label">Risk Level:</span> {signal['risk_level']}</p>
                <p>Generated by FAI-QUANT-SUPERIOR automated trading system</p>
            </div>
        </body>
        </html>
        """
        return html
    
    async def run(self):
        """Main execution loop"""
        logger.info("=" * 60)
        logger.info("FAI-QUANT-SUPERIOR - Trading System Started")
        logger.info("=" * 60)
        
        # Log time info
        self._log_time_info()
        
        # Fetch market data
        market_data = self.get_market_data()
        
        # Calculate signals
        signal = self.calculate_signals(market_data)
        
        # Send email
        try:
            # Decision: Send email only on BUY/SELL signals
            # Change this to `if signal:` to send email always (including FLAT)
            if signal['signal'] in ['BUY', 'SELL']:
                logger.info(f"Signal is {signal['signal']} - sending email notification")
                self.send_email(signal)
            else:
                logger.info(f"Signal is {signal['signal']} - email not sent (only BUY/SELL trigger emails)")
        
        except EmailNotificationError as e:
            logger.error(f"Failed to send email notification: {e}")
            raise
        
        logger.info("=" * 60)
        logger.info("Trading cycle completed")
        logger.info("=" * 60)


async def main():
    """Entry point"""
    try:
        system = TradingSystem()
        await system.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
