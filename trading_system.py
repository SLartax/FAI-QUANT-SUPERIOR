# -*- coding: utf-8 -*-
"""
FAI QUANT SUPERIOR – OVERNIGHT SIGNAL (FLAT, ROBUST, EMAIL)
----------------------------------------------------------
- Nessun look-ahead
- Segnale sempre per il prossimo overnight utile
- Robusto a weekend / festivi / Yahoo incompleto
- Validazione completa secret SMTP
"""

import pandas as pd
import numpy as np
import yfinance as yf
import datetime as dt
import smtplib
import os
import sys
import warnings
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

warnings.filterwarnings("ignore")

START_DATE = "2010-01-01"
ALLOWED_DAYS = [0, 1, 2, 3]  # Lun–Gio


# ============================================================
# EMAIL CLIENT
# ============================================================
class EmailClient:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = os.getenv("SMTP_PORT", "587")
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")
        self.email_to = os.getenv("EMAIL_TO")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "FAI-QUANT-SUPERIOR")

        self._validate_secrets()

    def _validate_secrets(self):
        """Validate that all required secrets are set"""
        required_secrets = {
            "SMTP_HOST": self.smtp_host,
            "SMTP_PORT": self.smtp_port,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASS": self.smtp_pass,
            "EMAIL_TO": self.email_to,
        }

        missing = [k for k, v in required_secrets.items() if not v]

        if missing:
            print("❌ ERRORE: secret SMTP mancanti:")
            for k in missing:
                print(f"   - {k}")
            sys.exit(1)

    def send(self, subject: str, body: str):
        msg = MIMEMultipart()
        msg["From"] = self.from_name
        msg["To"] = self.email_to
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(self.smtp_host, int(self.smtp_port)) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.send_message(msg)


# ============================================================
# DATA LOADING
# ============================================================
def fix_yahoo_df(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join(map(str, c)) for c in df.columns]
    return df


def extract_close(df):
    for c in df.columns:
        if "close" in c.lower():
            return df[c]
    raise RuntimeError("Colonna Close non trovata")


def load_ftsemib():
    df = yf.download(
        "FTSEMIB.MI",
        start=START_DATE,
        interval="1d",
        auto_adjust=False,
        progress=False
    )

    if df is None or df.empty:
        raise RuntimeError("Nessun dato FTSEMIB disponibile")

    df = fix_yahoo_df(df).sort_index()

    out = pd.DataFrame(index=df.index)
    out["Open"] = df[[c for c in df.columns if "open" in c.lower()][0]]
    out["High"] = df[[c for c in df.columns if "high" in c.lower()][0]]
    out["Low"] = df[[c for c in df.columns if "low" in c.lower()][0]]
    out["Close"] = extract_close(df)
    out["Volume"] = df[[c for c in df.columns if "vol" in c.lower()][0]]

    return out


def load_aux(symbol):
    df = yf.download(
        symbol,
        start=START_DATE,
        interval="1d",
        auto_adjust=False,
        progress=False
    )

    if df is None or df.empty:
        return None

    df = fix_yahoo_df(df).sort_index()
    return pd.DataFrame({"Close": extract_close(df)})


# ============================================================
# DATASET (SOLO DATI CAUSALI)
# ============================================================
def build_dataset():
    df = load_ftsemib()

    spy = load_aux("SPY")
    vix = load_aux("^VIX")

    if spy is not None:
        df["spy_ret"] = spy["Close"].pct_change()

    if vix is not None:
        df["vix_ret"] = vix["Close"].pct_change()

    df["Close_prev"] = df["Close"].shift(1)
    df["gap_open"] = df["Open"] / df["Close_prev"] - 1

    df["vol_ma"] = df["Volume"].rolling(20).mean()
    df["vol_std"] = df["Volume"].rolling(20).std()
    df["vol_z"] = (df["Volume"] - df["vol_ma"]) / df["vol_std"]

    df["dow"] = df.index.dayofweek

    return df


# ============================================================
# STRATEGIA (TOP3)
# ============================================================
def match_top3(r):
    cond = False

    if not pd.isna(r.get("spy_ret")):
        cond |= (0 <= r["gap_open"] < 0.01) and (0 <= r["spy_ret"] < 0.01)

    if not pd.isna(r.get("vix_ret")):
        cond |= (-0.10 <= r["vix_ret"] < -0.05)

    cond |= (-1.5 <= r["vol_z"] < -0.5)

    return cond


def filters(r):
    if not pd.isna(r.get("spy_ret")) and r["spy_ret"] < -0.005:
        return False
    if r["dow"] not in ALLOWED_DAYS:
        return False
    return True


# ============================================================
# SEGNALE LIVE ROBUSTO
# ============================================================
def get_next_overnight_signal(df):
    today = dt.date.today()
    df_live = df.dropna(
        subset=["gap_open", "spy_ret", "vix_ret", "vol_z", "dow"]
    ).copy()

    if df_live.empty:
        raise RuntimeError("ERRORE: Nessun dato valido dopo dropna")

    last_row = df_live.iloc[-1]
    last_date = last_row.name.date()

    if last_date >= today:
        raise RuntimeError(f"ERRORE: data piu recente ({last_date}) non è chiusa")

    signal = match_top3(last_row) and filters(last_row)
    return last_date, signal



# ============================================================
# MAIN
# ============================================================
def main():
    mailer = EmailClient()

    df = build_dataset()
    ref_date, signal = get_next_overnight_signal(df)

    status = "LONG" if signal else "FLAT"

    subject = f"FAI QUANT SUPERIOR – Overnight {status}"

    body = f"""
FAI QUANT SUPERIOR – SEGNALE OVERNIGHT

Ultima seduta chiusa: {ref_date}
Segnale valido per il prossimo overnight utile

Segnale: {status}

Il segnale è calcolato esclusivamente
su dati disponibili alla chiusura
dell’ultima seduta di mercato.
"""

    print(body)
    mailer.send(subject, body)


if __name__ == "__main__":
    main()
