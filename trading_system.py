# -*- coding: utf-8 -*-
"""
FAI QUANT SUPERIOR – OVERNIGHT SIGNAL (LIVE @ 17:30 Europe/Rome)
---------------------------------------------------------------
Obiettivo:
- usare i dati del GIORNO STESSO
- non dipendere dalla chiusura USA: SPY/VIX calcolati con snapshot <= 17:30 Europe/Rome
- email con timestamp esatto dei prezzi usati
"""

import pandas as pd
import numpy as np
import yfinance as yf
import datetime as dt
import smtplib
import os
import sys
import warnings
from zoneinfo import ZoneInfo
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

warnings.filterwarnings("ignore")

START_DATE = "2010-01-01"
ALLOWED_DAYS = [0, 1, 2, 3]  # Lun–Gio (se vuoi anche venerdì -> aggiungi 4)

TZ_ROME = ZoneInfo("Europe/Rome")
SNAPSHOT_TIME_ROME = dt.time(17, 30)

# Finestra di esecuzione per GitHub Actions
RUN_WINDOW_START = dt.time(17, 33)       # finestra d'avvio in minuti
RUN_WINDOW_END = dt.time(17, 55)         # finestra d'esecuzione in minuti


# ============================================================
# EMAIL CLIENT
# ============================================================
class EmailClient:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = os.getenv("SMTP_PORT", "587")
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")

        # Destinatario: se EMAIL_TO non è impostata, usa il default richiesto
        email_to_raw = (os.getenv("EMAIL_TO") or "").strip()
        self.email_to = email_to_raw if email_to_raw else "studiolegaleartax@gmail.com"

        self.from_name = os.getenv("EMAIL_FROM_NAME", "FAI-QUANT-SUPERIOR")
        self._validate_secrets()

    def _validate_secrets(self):
        # EMAIL_TO non è obbligatoria: c'è un default
        required = {
            "SMTP_HOST": self.smtp_host,
            "SMTP_PORT": self.smtp_port,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASS": self.smtp_pass,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            print("❌ ERRORE: secret SMTP mancanti:")
            for k in missing:
                print(f"   - {k}")
            sys.exit(1)

    def send(self, subject: str, body: str):
        msg = MIMEMultipart()
        msg["From"] = f"{self.from_name} <{self.smtp_user}>"
        msg["To"] = self.email_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        host = self.smtp_host
        port = int(self.smtp_port)

        print(f"[email] Invio a {self.email_to} via {host}:{port} (user={self.smtp_user})")

        # Supporto 587 (STARTTLS) e 465 (SSL)
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as server:
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

        print("[email] Inviata OK")


# ============================================================
# TIME HELPERS
# ============================================================
def now_rome() -> dt.datetime:
    return dt.datetime.now(TZ_ROME)

def today_rome() -> dt.date:
    return now_rome().date()

def target_dt_rome(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, SNAPSHOT_TIME_ROME, tzinfo=TZ_ROME)

def should_run_now() -> bool:
    # Permetti override manuale da workflow_dispatch
    if os.getenv("FORCE_RUN", "0").strip() == "1":
        return True
    t = now_rome().time()
    return (t >= RUN_WINDOW_START) and (t <= RUN_WINDOW_END)


# ============================================================
# YFINANCE HELPERS
# ============================================================
def fix_yahoo_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join(map(str, c)) for c in df.columns]
    return df

def extract_col(df: pd.DataFrame, key: str) -> pd.Series:
    cols = [c for c in df.columns if key in c.lower()]
    if not cols:
        raise RuntimeError(f"Colonna {key} non trovata")
    return df[cols[0]]

def to_rome_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    idx = idx.tz_convert(TZ_ROME)
    out = df.copy()
    out.index = idx
    return out

def yf_download(symbol: str, **kwargs) -> pd.DataFrame:
    last_err = None
    for _ in range(3):
        try:
            df = yf.download(symbol, progress=False, auto_adjust=False, **kwargs)
            df = fix_yahoo_df(df)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    return pd.DataFrame()

def yf_download_with_fallback(symbols: list, **kwargs) -> tuple[pd.DataFrame, str]:
    last_err = None
    for sym in symbols:
        try:
            df = yf_download(sym, **kwargs)
            if df is not None and not df.empty:
                return df, sym
        except Exception as e:
            last_err = e
    raise RuntimeError(f"yfinance fallito per tutti i simboli {symbols}. Ultimo errore: {last_err}")


# ============================================================
# DATA FETCH
# ============================================================
def get_ftse_intraday(today: dt.date) -> tuple[pd.DataFrame, str]:
    # FTSEMIB: su yfinance spesso ^FTMIB o FTSEMIB.MI
    symbols = ["FTSEMIB.MI", "^FTMIB"]
    df, sym = yf_download_with_fallback(
        symbols,
        period="5d",
        interval="1m",
    )
    df = to_rome_index(df)
    return df, sym

def get_spy_intraday() -> tuple[pd.DataFrame, str]:
    symbols = ["SPY"]
    df, sym = yf_download_with_fallback(
        symbols,
        period="5d",
        interval="1m",
    )
    df = to_rome_index(df)
    return df, sym

def get_vix_intraday() -> tuple[pd.DataFrame, str]:
    # VIX su Yahoo: ^VIX
    symbols = ["^VIX"]
    df, sym = yf_download_with_fallback(
        symbols,
        period="5d",
        interval="1m",
    )
    df = to_rome_index(df)
    return df, sym


# ============================================================
# SNAPSHOT LOGIC
# ============================================================
def pick_last_before(df: pd.DataFrame, t_end: dt.datetime) -> tuple[dt.datetime, float]:
    if df is None or df.empty:
        raise RuntimeError("DataFrame vuoto")
    df = df.sort_index()
    df = df[df.index <= t_end]
    if df.empty:
        raise RuntimeError("Nessun dato <= snapshot target")
    close = extract_col(df, "close")
    ts = close.index[-1]
    val = float(close.iloc[-1])
    return ts.to_pydatetime(), val

def compute_returns(ftse_close: float, ftse_prev_close: float,
                    spy_close: float, spy_prev_close: float,
                    vix_close: float, vix_prev_close: float) -> dict:
    gap_open = (ftse_close / ftse_prev_close) - 1.0 if ftse_prev_close else np.nan
    spy_ret = (spy_close / spy_prev_close) - 1.0 if spy_prev_close else np.nan
    vix_ret = (vix_close / vix_prev_close) - 1.0 if vix_prev_close else np.nan
    return {
        "gap_open": float(gap_open),
        "spy_ret": float(spy_ret),
        "vix_ret": float(vix_ret),
    }

def get_prev_close(df: pd.DataFrame, day: dt.date) -> float:
    # prende l'ultimo close del giorno precedente (in orario Rome)
    df = df.sort_index()
    prev_day = day - dt.timedelta(days=1)
    mask = (df.index.date == prev_day)
    if not mask.any():
        # fallback: prende il penultimo giorno disponibile
        days = sorted(set(df.index.date))
        if len(days) < 2:
            raise RuntimeError("Non ci sono abbastanza giorni per prev_close")
        prev_day = days[-2]
        mask = (df.index.date == prev_day)
    close = extract_col(df[mask], "close")
    return float(close.iloc[-1])

def day_of_week(day: dt.date) -> int:
    return dt.datetime.combine(day, dt.time(12, 0)).weekday()

def decide_signal(features: dict, dow: int) -> str:
    # Strategia semplice dimostrativa:
    # - se VIX spike > +4.75% => SHORT
    # - se VIX spike < -4.75% => LONG
    # - altrimenti FLAT
    if dow not in ALLOWED_DAYS:
        return "FLAT"
    vix_ret = features.get("vix_ret", 0.0)
    if vix_ret >= 0.0475:
        return "SHORT"
    if vix_ret <= -0.0475:
        return "LONG"
    return "FLAT"


# ============================================================
# FORMATTING
# ============================================================
def fmt_pct(x: float) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/a"
    return f"{float(x)*100:.3f}%"

def fmt_price(x: float) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/a"
    return f"{float(x):.4f}"

def build_email_body(run_ts: dt.datetime,
                     snapshot_target: dt.datetime,
                     reference_date: dt.date,
                     signal: str,
                     debug: dict) -> str:
    lines = []
    lines.append("=== LIVE SIGNAL @ SNAPSHOT ===")
    lines.append(f"Run time (Rome):        {run_ts}")
    lines.append(f"Snapshot target (Rome): {snapshot_target}")
    lines.append(f"Reference date (FTSE):  {reference_date}")
    lines.append(f"Signal:                 {signal}")
    lines.append("")
    lines.append("--- DATA USED (debug) ---")
    for k, v in debug.get("data_used", {}).items():
        lines.append(f"{k:<10} {v}")
    lines.append("")
    lines.append("--- SNAPSHOT SOURCES ---")
    for k, v in debug.get("sources", {}).items():
        lines.append(f"{k:<20} {v}")
    lines.append("")
    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================
def main():
    run_ts = now_rome()
    if not should_run_now():
        print(f"[skip] Ora Rome={run_ts.time()} fuori finestra {RUN_WINDOW_START}-{RUN_WINDOW_END}.")
        return

    ref_day = today_rome()
    dow = day_of_week(ref_day)

    snapshot_target = target_dt_rome(ref_day)

    # Fetch data
    ftse_df, ftse_sym = get_ftse_intraday(ref_day)
    spy_df, spy_sym = get_spy_intraday()
    vix_df, vix_sym = get_vix_intraday()

    # Snapshot prices
    ftse_ts, ftse_close = pick_last_before(ftse_df, snapshot_target)
    spy_ts, spy_close = pick_last_before(spy_df, snapshot_target)
    vix_ts, vix_close = pick_last_before(vix_df, snapshot_target)

    # Previous closes (day-1)
    ftse_prev_close = get_prev_close(ftse_df, ref_day)
    spy_prev_close = get_prev_close(spy_df, ref_day)
    vix_prev_close = get_prev_close(vix_df, ref_day)

    feats = compute_returns(
        ftse_close=ftse_close, ftse_prev_close=ftse_prev_close,
        spy_close=spy_close, spy_prev_close=spy_prev_close,
        vix_close=vix_close, vix_prev_close=vix_prev_close,
    )

    signal = decide_signal(feats, dow=dow)

    debug = {
        "data_used": {
            "dow:": f"{dow}   (0=Lun ... 6=Dom)",
            "gap_open:": fmt_pct(feats["gap_open"]),
            "spy_ret:": fmt_pct(feats["spy_ret"]),
            "vix_ret:": fmt_pct(feats["vix_ret"]),
        },
        "sources": {
            "FTSE symbol used:": ftse_sym,
            "FTSE close ts (Rome):": ftse_ts,
            "SPY symbol used:": spy_sym,
            "SPY price ts (Rome):": spy_ts,
            "VIX symbol used:": vix_sym,
            "VIX price ts (Rome):": vix_ts,
        }
    }

    subject = f"FAI-QUANT-SUPERIOR | {ref_day} | SIGNAL: {signal}"
    body = build_email_body(
        run_ts=run_ts,
        snapshot_target=snapshot_target,
        reference_date=ref_day,
        signal=signal,
        debug=debug
    )

    # send email
    EmailClient().send(subject, body)
    print("[ok] Email inviata.")

if __name__ == "__main__":
    main()
