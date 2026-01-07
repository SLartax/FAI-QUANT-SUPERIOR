#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAI-QUANT-SUPERIOR — TOP3 PATTERN (GitHub Actions compatible)
Versione adattata da quant_superior.py per esecuzione automatica con email.

Logica trading:
- TOP3 PATTERN: gap piccolo positivo + SPY leggermente positivo + VIX in calo + volume sotto media
- Esclusione venerdì
- Dati intraday sintetici per previsione live

Dipendenze: numpy, pandas, yfinance, matplotlib
"""

import os
import sys
import smtplib
import traceback
import warnings
from datetime import datetime, date, timedelta, time
from email.message import EmailMessage
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")  # Headless
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# Timezone
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Rome")
except Exception:
    TZ = None

# Costanti
START_DATE = "2010-01-01"
ALLOWED_DAYS = [0, 1, 2, 3]  # Lun-Gio (venerdì escluso)

# ========== UTILITY =========="

def now_rome():
    try:
        if TZ is not None:
            return datetime.now(TZ)
    except Exception:
        pass
    return datetime.now()

def next_weekday(d: date) -> date:
    """Prossimo giorno lavorativo (lun-ven)."""
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:
        nd += timedelta(days=1)
    return nd

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return float(np.asarray(x).item())

def rome_ts_label(ts):
    if ts is None:
        return "N/A"
    try:
        return ts.isoformat()
    except Exception:
        return str(ts)

# ========== YAHOO FINANCE UTILITIES ==========

def fix_yahoo_df(df):
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["".join(str(x) for x in col) for col in df.columns]
    else:
        df.columns = [str(c) for c in df.columns]
    return df

def extract_single_close(df):
    cols_low = [c.lower() for c in df.columns]
    for t in ["close", "adj close"]:
        if t in cols_low:
            return df[df.columns[cols_low.index(t)]]
    for i, c in enumerate(cols_low):
        if "close" in c:
            return df[df.columns[i]]
    for c in df.columns:
        if np.issubdtype(df[c].dtype, np.number):
            return df[c]
    raise RuntimeError("Nessuna colonna Close trovata.")

def ensure_dt_index(df):
    if df is None or df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df

def to_rome_tz(df):
    if df is None or df.empty:
        return df
    df = ensure_dt_index(df)
    idx = df.index
    try:
        if isinstance(idx, pd.DatetimeIndex):
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            if TZ is not None:
                idx = idx.tz_convert(TZ)
            else:
                idx = idx.tz_localize(None)
            df.index = idx
    except Exception:
        pass
    return df

def yf_download_safe(symbol, **kwargs):
    try:
        df = yf.download(symbol, progress=False, auto_adjust=False, **kwargs)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = fix_yahoo_df(df)
    df = df.sort_index()
    return df

# ========== DATA LOADERS ==========

def load_daily_ohlcv(symbol, start=START_DATE):
    df = yf_download_safe(symbol, start=start, interval="1d")
    if df is None or df.empty:
        return None
    c = extract_single_close(df)
    
    def find(*words):
        for w in words:
            for col in df.columns:
                if w in col.lower():
                    return col
        return None
    
    o = find("open")
    h = find("high")
    l = find("low")
    v = find("vol")
    
    out = pd.DataFrame(index=df.index)
    out["Close"] = c
    if o and h and l:
        out["Open"] = df[o]
        out["High"] = df[h]
        out["Low"] = df[l]
    else:
        out["Open"] = out["Close"].shift(1)
        out["High"] = out[["Open", "Close"]].max(axis=1)
        out["Low"] = out[["Open", "Close"]].min(axis=1)
    out["Volume"] = df[v] if v else 0
    return out.dropna()

def load_intraday_ohlcv(symbol):
    """Scarica intraday con fallback di intervalli."""
    attempts = [("1m", "7d"), ("2m", "60d"), ("5m", "60d"), 
                ("15m", "60d"), ("30m", "60d"), ("60m", "730d")]
    
    for interval, period in attempts:
        df = yf_download_safe(symbol, interval=interval, period=period)
        if df is None or df.empty:
            continue
        
        df = to_rome_tz(df)
        df = fix_yahoo_df(df)
        
        try:
            c = extract_single_close(df)
        except Exception:
            continue
        
        def find(*words):
            for w in words:
                for col in df.columns:
                    if w in col.lower():
                        return col
            return None
        
        o = find("open")
        h = find("high")
        l = find("low")
        v = find("vol")
        
        if o and h and l:
            out = pd.DataFrame(index=df.index)
            out["Open"] = df[o]
            out["High"] = df[h]
            out["Low"] = df[l]
            out["Close"] = c
            out["Volume"] = df[v] if v else 0
            out = out.dropna()
            if not out.empty:
                return out, interval
    
    return None, None

def synth_bar_for_day_upto(df_intra, day: date, runtime):
    """Barra sintetica per un giorno fino a runtime."""
    if df_intra is None or df_intra.empty:
        return None, None
    
    try:
        sub = df_intra[df_intra.index <= runtime]
    except Exception:
        sub = df_intra.copy()
    
    if sub.empty:
        return None, None
    
    try:
        mask = (sub.index.date == day)
        sub = sub[mask]
    except Exception:
        sub = sub.copy()
    
    if sub.empty:
        return None, None
    
    bar = {
        "Open": safe_float(sub["Open"].iloc[0]),
        "High": safe_float(sub["High"].max()),
        "Low": safe_float(sub["Low"].min()),
        "Close": safe_float(sub["Close"].iloc[-1]),
        "Volume": safe_float(sub["Volume"].sum()) if "Volume" in sub.columns else 0.0
    }
    last_ts = sub.index[-1]
    return bar, last_ts

# ========== TRADING LOGIC ==========

def match_top3(r):
    """TOP3 PATTERN: condizioni per segnale LONG."""
    cond = False
    if not pd.isna(r.get("spy_ret")):
        cond = (0 < r["gap_open"] < 0.01 and 
                0 < r["spy_ret"] < 0.01)
    # VIX e VOL_Z rimossi per aumentare numero trade
    return cond

def filters(r):
    """Filtri addizionali."""
    if not pd.isna(r.get("spy_ret")):
        if r["spy_ret"] < -0.005:
            return False
    if int(r["dow"]) not in ALLOWED_DAYS:
        return False
    return True

def build_dataset_history(runtime):
    """Dataset daily per backtest."""
    print("Download DAILY FTSEMIB.MI")
    ftse = load_daily_ohlcv("FTSEMIB.MI", start=START_DATE)
    if ftse is None or ftse.empty:
        raise RuntimeError("Errore: nessun dato FTSEMIB da Yahoo daily.")
    
    print("Download DAILY SPY + VIX")
    spy = load_daily_ohlcv("SPY", start=START_DATE)
    vix = load_daily_ohlcv("^VIX", start=START_DATE)
    
    df = ftse.copy()
    if spy is not None and not spy.empty:
        df = df.join(spy["Close"].rename("SPY_Close"))
    if vix is not None and not vix.empty:
        df = df.join(vix["Close"].rename("VIX_Close"))
    
    calday = runtime.date()
    if hasattr(df.index[-1], "date") and df.index[-1].date() == calday:
        cutoff = datetime.combine(calday, time(17, 40))
        if TZ is not None:
            cutoff = cutoff.replace(tzinfo=TZ)
        if runtime < cutoff:
            df = df.iloc[:-1].copy()
    
    df["spy_ret"] = df["SPY_Close"].pct_change() if "SPY_Close" in df.columns else np.nan
    df["vix_ret"] = df["VIX_Close"].pct_change() if "VIX_Close" in df.columns else np.nan
    df["Close_prev"] = df["Close"].shift(1)
    df["gap_open"] = (df["Open"] / df["Close_prev"]) - 1
    df["vol_ma"] = df["Volume"].rolling(20).mean()
    df["vol_std"] = df["Volume"].rolling(20).std()
    df["vol_z"] = (df["Volume"] - df["vol_ma"]) / df["vol_std"]
    df["Open_next"] = df["Open"].shift(-1)
    df["overnight_ret"] = (df["Open_next"] / df["Close"]) - 1
    df["dow"] = df.index.dayofweek
    
    return df.dropna()

def build_live_snapshot(history_df, runtime):
    """Snapshot live con dati intraday sintetici."""
    calday = runtime.date()
    
    if history_df is None or history_df.empty:
        raise RuntimeError("History DF vuoto")
    
    close_prev = safe_float(history_df["Close"].iloc[-1])
    
    ftse_intra, ftse_interval = load_intraday_ohlcv("FTSEMIB.MI")
    ftse_bar, ftse_ts = synth_bar_for_day_upto(ftse_intra, calday, runtime) if ftse_intra is not None else (None, None)
    ftse_source = "intraday_synth" if ftse_bar is not None else "daily_fallback"
    
    if ftse_bar is None:
        ftse_bar = {
            "Open": safe_float(history_df["Open"].iloc[-1]),
            "High": safe_float(history_df["High"].iloc[-1]),
            "Low": safe_float(history_df["Low"].iloc[-1]),
            "Close": safe_float(history_df["Close"].iloc[-1]),
            "Volume": safe_float(history_df["Volume"].iloc[-1])
        }
        ftse_ts = None
    
    spy_price_now = None
    spy_prev_close = None
    if "SPY_Close" in history_df.columns:
        s = history_df["SPY_Close"].dropna()
        if not s.empty:
            spy_prev_close = safe_float(s.iloc[-1])
    
    spy_intra, spy_interval = load_intraday_ohlcv("SPY")
    if spy_intra is not None and spy_prev_close is not None:
        spy_bar, spy_ts = synth_bar_for_day_upto(spy_intra, calday, runtime)
        if spy_bar is not None:
            spy_price_now = safe_float(spy_bar["Close"])
    
    if spy_price_now is None and spy_prev_close is not None:
        spy_price_now = spy_prev_close
    
    spy_ret_live = (spy_price_now / spy_prev_close - 1) if spy_price_now and spy_prev_close else np.nan
    
    vix_price_now = None
    vix_prev_close = None
    if "VIX_Close" in history_df.columns:
        v = history_df["VIX_Close"].dropna()
        if not v.empty:
            vix_prev_close = safe_float(v.iloc[-1])
    
    vix_intra, vix_interval = load_intraday_ohlcv("^VIX")
    if vix_intra is not None and vix_prev_close is not None:
        vix_bar, vix_ts = synth_bar_for_day_upto(vix_intra, calday, runtime)
        if vix_bar is not None:
            vix_price_now = safe_float(vix_bar["Close"])
    
    if vix_price_now is None and vix_prev_close is not None:
        vix_price_now = vix_prev_close
    
    vix_ret_live = (vix_price_now / vix_prev_close - 1) if vix_price_now and vix_prev_close else np.nan
    
    vol_today = safe_float(ftse_bar.get("Volume", 0.0))
    vol_ma = safe_float(history_df["Volume"].tail(20).mean()) if "Volume" in history_df.columns else 0.0
    vol_std = safe_float(history_df["Volume"].tail(20).std()) if "Volume" in history_df.columns else 0.0
    vol_z_live = (vol_today - vol_ma) / vol_std if vol_std and vol_std > 0 else 0.0
    
    live = {
        "Open": ftse_bar["Open"],
        "High": ftse_bar["High"],
        "Low": ftse_bar["Low"],
        "Close": ftse_bar["Close"],
        "Volume": vol_today,
        "Close_prev": close_prev,
        "gap_open": (ftse_bar["Open"] / close_prev - 1) if close_prev else np.nan,
        "SPY_Close": spy_price_now,
        "VIX_Close": vix_price_now,
        "spy_ret": spy_ret_live,
        "vix_ret": vix_ret_live,
        "vol_ma": vol_ma,
        "vol_std": vol_std,
        "vol_z": vol_z_live,
        "dow": calday.weekday()
    }
    
    return pd.Series(live)

def run_backtest(df):
    """Backtest con TOP3 PATTERN."""
    df = df.copy()
    df["signal"] = df.apply(lambda r: match_top3(r) and filters(r), axis=1)
    
    trades = df[df["signal"]].copy()
    if trades.empty:
        return trades, pd.Series(dtype=float), 0, 0, 0, 0, 0
    
    trades["pnl"] = trades["overnight_ret"]
    trades["pnl_points"] = trades["overnight_ret"] * trades["Close"]
    trades["raw_points"] = trades["Open_next"] - trades["Close"]
    
    equity = (1 + trades["overnight_ret"]).cumprod()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] ** (1/years)) - 1 if years > 0 else 0
    avg = trades["overnight_ret"].mean()
    avgpoints = trades["pnl_points"].mean()
    win = (trades["overnight_ret"] > 0).mean()
    
    return trades, equity, cagr, avg, win, avgpoints, trades["raw_points"].mean()

# ========== EMAIL ==========

def send_email(subject: str, body: str, attachment_path=None):
    """Invia email via Gmail SMTP."""
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    email_to = os.getenv("EMAIL_TO", "").strip()
    from_name = os.getenv("EMAIL_FROM_NAME", "FAI-QUANT-SUPERIOR").strip()
    
    if not smtp_host or not smtp_user or not smtp_pass or not email_to:
        raise RuntimeError("Variabili email mancanti")
    
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{smtp_user}>"
    msg["To"] = email_to
    msg.set_content(body)
    
    if attachment_path and Path(attachment_path).exists():
        data = Path(attachment_path).read_bytes()
        msg.add_attachment(data, maintype="image", subtype="png", 
                          filename=Path(attachment_path).name)
    
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

# ========== MAIN ==========

def main() -> int:
    runtime = now_rome()
    
    try:
        # Backtest
        df_hist = build_dataset_history(runtime)
        trades, equity, cagr, avg, winrate, avgpoints, avgraw = run_backtest(df_hist)
        
        print("\n=== METRICHE SISTEMA BACKTEST (Venerdì escluso) ===")
        print(f"Trades: {len(trades)}")
        print(f"Avg trade: {safe_float(avg)*100:.4f}%")
        print(f"Avg punti: {safe_float(avgpoints):.2f}")
        print(f"Avg punti raw: {safe_float(avgraw):.2f}")
        print(f"Winrate: {safe_float(winrate)*100:.2f}%")
        print(f"CAGR: {safe_float(cagr)*100:.2f}%")
        if equity is not None and not equity.empty:
            print(f"Total Return: {safe_float(equity.iloc[-1] - 1)*100:.2f}%")
        
        # Live prediction
        liverow = build_live_snapshot(df_hist, runtime)
        calday = runtime.date()
        forecastday = next_weekday(calday)
        
        sig = match_top3(liverow) and filters(liverow)
        
        # Costruisci report email
        signal_text = "LONG overnight" if sig else "FLAT"
        
        subject = f"FAI-QUANT-SUPERIOR — {signal_text} — Sessione {forecastday}"
        
        body = f"""=== FAI-QUANT-SUPERIOR - TOP3 PATTERN ===

Run time (Rome): {runtime.isoformat()}
Data usata per calcolo: {calday} (chiusura)
Sessione prevista: {forecastday}

SEGNALE: {signal_text}

--- INPUT SEGNALE (dati disponibili al run) ---
dow: {int(liverow['dow'])} (0=Lun ... 4=Ven)
gap_open: {safe_float(liverow['gap_open']):.6f}
vol_z: {safe_float(liverow['vol_z']):.6f}
spy_ret: {f'{safe_float(liverow["spy_ret"]):.6f}' if not pd.isna(liverow.get('spy_ret', np.nan)) else 'N/A'}
vix_ret: {f'{safe_float(liverow["vix_ret"]):.6f}' if not pd.isna(liverow.get('vix_ret', np.nan)) else 'N/A'}

--- BACKTEST METRICS (overnight, Venerdì escluso) ---
Trades: {len(trades)}
Avg trade: {safe_float(avg)*100:.4f}%
Avg punti: {safe_float(avgpoints):.2f}
Winrate: {safe_float(winrate)*100:.2f}%
CAGR: {safe_float(cagr)*100:.2f}%
Total Return: {safe_float(equity.iloc[-1] - 1)*100:.2f}% se equity disponibile

---
Sistema: FAI-QUANT-SUPERIOR TOP3 PATTERN
GitHub Actions run: {os.getenv('GITHUB_SERVER_URL', '')}/{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID', '')}
"""
        
        # Invia email
        send_email(subject=subject, body=body)
        print("\n[i] Email inviata correttamente.")
        print(f"\nSEGNALE LIVE: {signal_text}")
        print(f"Snapshot: {calday} (run) → Sessione: {forecastday}")
        
        return 0
    
    except Exception as e:
        tb = traceback.format_exc()
        err_subject = "FAI-QUANT-SUPERIOR | ERROR"
        err_body = f"""Errore durante l'esecuzione del sistema.

Run time (Rome): {now_rome().isoformat()}
Exception: {repr(e)}

Traceback:
{tb}
"""
        print(err_body)
        try:
            send_email(subject=err_subject, body=err_body)
            print("[i] Mail di errore inviata.")
        except Exception as mail_err:
            print(f"[!] Impossibile inviare mail di errore: {repr(mail_err)}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
