#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
trading_system.py
-----------------
Script completo (GitHub Actions friendly) che:
1) scarica dati (FTSEMIB + VIX) via yfinance (con fallback simboli) oppure da CSV locale se presente
2) calcola una semplice strategia overnight (contrarian su VIX/FTSE)
3) produce metriche + equity curve (PNG)
4) invia una mail (anche con FLAT se SEND_ON_FLAT=1)

ENV richieste per email (GitHub Secrets):
- SMTP_HOST   (es. smtp.gmail.com)
- SMTP_PORT   (es. 587) [opzionale, default 587]
- SMTP_USER   (tuo gmail)
- SMTP_PASS   (App Password gmail)
- EMAIL_TO    (destinatario, es. studiolegaleartax@gmail.com)
- EMAIL_FROM_NAME (opzionale)

ENV strategia (opzionali):
- VIX_TH      (default 0.03 = 3%)
- FTSE_TH     (default 0.002 = 0.2%)
- SEND_ON_FLAT (default "1")  -> se "0" non invia mail quando FLAT
- LOOKBACK_YEARS (default 8)
- LOCAL_FTSE_CSV (default "FTSEMIB_D.csv")
- LOCAL_VIX_CSV  (default "VIX_D.csv")

Dipendenze (requirements.txt):
- pandas
- numpy
- matplotlib
- yfinance
"""

from __future__ import annotations

import os
import sys
import math
import traceback
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd

# Headless plotting (GitHub Actions)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import yfinance as yf
except Exception:
    yf = None


# =========================
# Config / Utils
# =========================

TZ_NAME = os.getenv("TZ", "Europe/Rome")  # GitHub Actions: set TZ=Europe/Rome nel workflow
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(TZ_NAME)
except Exception:
    TZ = timezone.utc  # fallback (non dovrebbe mai servire)

def now_rome() -> datetime:
    return datetime.now(tz=TZ)

def f(x) -> float:
    """Cast robusto a float built-in (per evitare numpy scalar nei print)."""
    try:
        return float(x)
    except Exception:
        return float("nan")

def pct(x) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    return f"{f(x)*100:.3f}%"

def ensure_cols(df: pd.DataFrame, cols: List[str], name: str):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: colonne mancanti {missing}. Colonne presenti: {list(df.columns)}")


@dataclass
class Metrics:
    n_trades: int
    winrate: float
    avg_trade: float
    total_return: float
    max_drawdown: float


# =========================
# Data loading
# =========================

def _read_local_csv(path: Path, name: str) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    # Provo diverse possibili colonne data
    dt_col = None
    for c in ["Date", "Datetime", "date", "datetime", "timestamp", "time"]:
        if c in df.columns:
            dt_col = c
            break
    if dt_col is None:
        raise ValueError(f"{name}: CSV locale {path} senza colonna data riconoscibile (Date/Datetime/...).")
    df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
    df = df.dropna(subset=[dt_col]).sort_values(dt_col).set_index(dt_col)
    # Normalizzo colonne OHLC se esistono
    colmap = {c: c.capitalize() for c in df.columns}
    df = df.rename(columns=colmap)
    return df

def _yf_download_with_fallback(symbols: List[str], start: pd.Timestamp) -> Tuple[str, pd.DataFrame]:
    if yf is None:
        raise RuntimeError("yfinance non disponibile. Aggiungi 'yfinance' a requirements.txt oppure usa CSV locali.")
    last_err = None
    for sym in symbols:
        try:
            df = yf.download(sym, start=start.date().isoformat(), progress=False, auto_adjust=False)
            if df is None or df.empty:
                continue
            df = df.copy()
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(TZ)
            # yfinance ritorna spesso colonne multiindex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            # Standardizza nomi
            df.columns = [str(c).capitalize() for c in df.columns]
            ensure_cols(df, ["Open", "High", "Low", "Close"], f"yfinance {sym}")
            return sym, df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Download yfinance fallito per simboli {symbols}. Ultimo errore: {last_err}")

def load_daily_data() -> Tuple[pd.DataFrame, pd.DataFrame, str, str]:
    """
    Ritorna:
    - ftse_df daily OHLC
    - vix_df daily OHLC
    - ftse_symbol_usato
    - vix_symbol_usato
    """
    lookback_years = int(os.getenv("LOOKBACK_YEARS", "8"))
    start = pd.Timestamp(now_rome().date()) - pd.DateOffset(years=lookback_years)

    local_ftse = Path(os.getenv("LOCAL_FTSE_CSV", "FTSEMIB_D.csv"))
    local_vix = Path(os.getenv("LOCAL_VIX_CSV", "VIX_D.csv"))

    ftse_df = _read_local_csv(local_ftse, "FTSE")
    vix_df = _read_local_csv(local_vix, "VIX")

    ftse_sym_used = "local_csv"
    vix_sym_used = "local_csv"

    if ftse_df is None:
        ftse_candidates = [
            os.getenv("FTSE_SYMBOL", "FTSEMIB.MI"),
            "^FTMIB", "FTMIB.MI", "FTSEMIB.MI"
        ]
        ftse_sym_used, ftse_df = _yf_download_with_fallback(ftse_candidates, start)

    if vix_df is None:
        vix_candidates = [
            os.getenv("VIX_SYMBOL", "^VIX"),
            "^VIX"
        ]
        vix_sym_used, vix_df = _yf_download_with_fallback(vix_candidates, start)

    # Allinea a date giornaliere (solo indice date) mantenendo tz
    ftse_df = ftse_df.sort_index()
    vix_df = vix_df.sort_index()

    # Teniamo solo giorni comuni (per semplicità)
    common_idx = ftse_df.index.normalize().intersection(vix_df.index.normalize())
    ftse_df = ftse_df[ftse_df.index.normalize().isin(common_idx)]
    vix_df = vix_df[vix_df.index.normalize().isin(common_idx)]

    if ftse_df.empty or vix_df.empty:
        raise RuntimeError("Dati vuoti dopo allineamento FTSE/VIX.")

    return ftse_df, vix_df, ftse_sym_used, vix_sym_used


# =========================
# Strategy + Backtest
# =========================

def compute_signals(ftse: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    """
    Strategy:
    - LONG overnight se:  vix_ret >= VIX_TH  e ftse_ret <= -FTSE_TH
    - SHORT overnight se: vix_ret <= -VIX_TH e ftse_ret >= +FTSE_TH
    - altrimenti FLAT

    Trade return (overnight): entry Close(t), exit Open(t+1).
    """
    vix_th = float(os.getenv("VIX_TH", "0.03"))
    ftse_th = float(os.getenv("FTSE_TH", "0.002"))

    df = pd.DataFrame(index=ftse.index.copy())
    df["ftse_close"] = ftse["Close"].astype(float)
    df["ftse_open"] = ftse["Open"].astype(float)
    df["vix_close"] = vix["Close"].astype(float)

    df["ftse_ret"] = df["ftse_close"].pct_change()
    df["vix_ret"] = df["vix_close"].pct_change()

    # Segnale generato a fine giornata t, eseguito overnight t->t+1
    signal = np.zeros(len(df), dtype=int)  # 1=long, -1=short, 0=flat

    long_mask = (df["vix_ret"] >= vix_th) & (df["ftse_ret"] <= -ftse_th)
    short_mask = (df["vix_ret"] <= -vix_th) & (df["ftse_ret"] >= ftse_th)

    signal[long_mask.fillna(False).values] = 1
    signal[short_mask.fillna(False).values] = -1

    df["signal"] = signal

    # Overnight return: from Close(t) to Open(t+1)
    df["next_open"] = df["ftse_open"].shift(-1)
    df["overnight_ret_long"] = (df["next_open"] / df["ftse_close"]) - 1.0
    df["overnight_ret_short"] = (df["ftse_close"] / df["next_open"]) - 1.0  # equivalente a -long su log, approx

    # Trade return applicata al segnale
    df["trade_ret"] = 0.0
    df.loc[df["signal"] == 1, "trade_ret"] = df.loc[df["signal"] == 1, "overnight_ret_long"]
    df.loc[df["signal"] == -1, "trade_ret"] = df.loc[df["signal"] == -1, "overnight_ret_short"]

    # Ultimo giorno non eseguibile (manca next_open)
    df.loc[df["next_open"].isna(), ["signal", "trade_ret"]] = 0

    # Equity curve
    df["equity"] = (1.0 + df["trade_ret"].fillna(0.0)).cumprod()

    # Drawdown
    df["peak"] = df["equity"].cummax()
    df["drawdown"] = (df["equity"] / df["peak"]) - 1.0

    return df

def compute_metrics(df: pd.DataFrame) -> Metrics:
    trades = df.loc[df["signal"] != 0, "trade_ret"].dropna()
    n = int(trades.shape[0])
    if n == 0:
        return Metrics(n_trades=0, winrate=0.0, avg_trade=0.0, total_return=f(df["equity"].iloc[-1] - 1.0),
                       max_drawdown=f(df["drawdown"].min()))
    winrate = f((trades > 0).mean())
    avg_trade = f(trades.mean())
    total_return = f(df["equity"].iloc[-1] - 1.0)
    max_dd = f(df["drawdown"].min())
    return Metrics(n_trades=n, winrate=winrate, avg_trade=avg_trade, total_return=total_return, max_drawdown=max_dd)

def plot_equity(df: pd.DataFrame, outpath: Path) -> None:
    plt.figure(figsize=(11, 5))
    plt.plot(df.index, df["equity"].values)
    plt.title("Equity Curve (Overnight)")
    plt.xlabel("Date")
    plt.ylabel("Equity (start=1.0)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outpath, dpi=160)
    plt.close()


# =========================
# Email
# =========================

def send_email(
    subject: str,
    body: str,
    attachment_path: Optional[Path] = None,
) -> None:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    email_to = os.getenv("EMAIL_TO", "").strip()
    from_name = os.getenv("EMAIL_FROM_NAME", "FAI-QUANT-SUPERIOR").strip()

    if not smtp_host or not smtp_user or not smtp_pass or not email_to:
        raise RuntimeError(
            "Variabili email mancanti: SMTP_HOST/SMTP_USER/SMTP_PASS/EMAIL_TO devono essere valorizzate."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{smtp_user}>"
    msg["To"] = email_to
    msg.set_content(body)

    if attachment_path is not None and attachment_path.exists():
        data = attachment_path.read_bytes()
        msg.add_attachment(
            data,
            maintype="image",
            subtype="png",
            filename=attachment_path.name
        )

    # SMTP with STARTTLS
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


# =========================
# Main
# =========================

def next_business_day(d: pd.Timestamp) -> pd.Timestamp:
    # Approx: business day (non gestisce festività italiane, ma va bene per report)
    return (d.normalize() + pd.offsets.BDay(1)).normalize()

def build_report(
    df: pd.DataFrame,
    metrics: Metrics,
    ftse_sym: str,
    vix_sym: str,
) -> Tuple[str, str]:
    # Ultimo giorno “completo” (cioè quello usato per generare segnale overnight)
    # Esempio: segnale basato su t, esecuzione verso t+1
    usable = df.copy()
    usable = usable[usable["next_open"].notna()]
    last_ts = usable.index[-1]
    last_date = pd.Timestamp(last_ts).tz_convert(TZ).date()

    # Segnale per overnight successivo (basato su last_ts)
    last_sig = int(usable.loc[last_ts, "signal"])
    sig_txt = "LONG" if last_sig == 1 else ("SHORT" if last_sig == -1 else "FLAT")

    # Data previsione: prossimo business day (approssimato)
    pred_day = next_business_day(pd.Timestamp(last_date))
    pred_day_str = pred_day.date().isoformat()

    # Debug values
    gap_proxy = f((usable.loc[last_ts, "ftse_open"] / df.loc[last_ts, "ftse_close"] - 1.0))  # solo indicativo
    vix_ret = f(usable.loc[last_ts, "vix_ret"])
    ftse_ret = f(usable.loc[last_ts, "ftse_ret"])

    run_time = now_rome().strftime("%Y-%m-%d %H:%M:%S %Z")

    subject = f"FAI-QUANT-SUPERIOR | Signal {sig_txt} | Prediction {pred_day_str}"

    body = (
        f"=== LIVE SIGNAL REPORT ===\n"
        f"Run time (Rome):        {run_time}\n"
        f"Data usata per calcolo: {last_date.isoformat()} (chiusura)\n"
        f"Previsione per giorno:  {pred_day_str}\n"
        f"Signal:                 {sig_txt}\n"
        f"\n"
        f"--- INPUT (debug) ---\n"
        f"FTSE symbol: {ftse_sym}\n"
        f"VIX  symbol: {vix_sym}\n"
        f"ftse_ret:    {pct(ftse_ret)}\n"
        f"vix_ret:     {pct(vix_ret)}\n"
        f"gap_proxy:   {pct(gap_proxy)}\n"
        f"\n"
        f"--- BACKTEST METRICS (overnight) ---\n"
        f"Trades:      {metrics.n_trades}\n"
        f"Winrate:     {pct(metrics.winrate)}\n"
        f"Avg trade:   {pct(metrics.avg_trade)}\n"
        f"Total ret:   {pct(metrics.total_return)}\n"
        f"Max DD:      {pct(metrics.max_drawdown)}\n"
    )
    return subject, body

def main() -> int:
    send_on_flat = os.getenv("SEND_ON_FLAT", "1").strip() == "1"
    out_plot = Path("equity_curve.png")

    try:
        ftse_df, vix_df, ftse_sym, vix_sym = load_daily_data()
        df = compute_signals(ftse_df, vix_df)
        metrics = compute_metrics(df)

        # Plot equity curve
        plot_equity(df, out_plot)

        # Report + subject
        subject, body = build_report(df, metrics, ftse_sym, vix_sym)

        # Decide se inviare mail con FLAT:
        # (qui la inviamo sempre di default, compreso FLAT, perché su GitHub vuoi sempre ricevere la notifica)
        # Se vuoi disattivare: SEND_ON_FLAT=0
        # Signal dell'ultimo giorno usabile:
        usable = df[df["next_open"].notna()]
        last_sig = int(usable["signal"].iloc[-1]) if not usable.empty else 0

        if last_sig == 0 and not send_on_flat:
            print(body)
            print("[i] Signal=FLAT e SEND_ON_FLAT=0 -> non invio email. Exit 0.")
            return 0

        # Invio email (con allegato equity curve)
        send_email(subject=subject, body=body, attachment_path=out_plot)

        # Log in console
        print(body)
        print("[i] Email inviata correttamente.")
        return 0

    except Exception as e:
        # Provo comunque a mandare una mail di errore (se i secrets ci sono)
        tb = traceback.format_exc()
        err_subject = "FAI-QUANT-SUPERIOR | ERROR in trading_system.py"
        err_body = (
            f"Errore durante l'esecuzione del sistema.\n\n"
            f"Run time (Rome): {now_rome().strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"Exception: {repr(e)}\n\n"
            f"Traceback:\n{tb}\n"
        )
        print(err_body)
        try:
            send_email(subject=err_subject, body=err_body, attachment_path=None)
            print("[i] Mail di errore inviata.")
        except Exception as mail_err:
            print(f"[!] Impossibile inviare mail di errore: {repr(mail_err)}")
        # Exit 1 così GitHub Actions segna failure (ma la mail è già partita se possibile)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
