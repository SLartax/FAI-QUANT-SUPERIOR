# -*- coding: utf-8 -*-
"""
FTSEMIB OVERNIGHT — TOP3 PATTERN (RUN-LATEST) + EMAIL
-----------------------------------------------------
Basato sul tuo script RUNLATEST, con:
- invio email via SMTP (Gmail App Password)
- destinatario default: studiolegaleartax@gmail.com (se EMAIL_TO non impostato)
- supporto GitHub Actions headless (dashboard salvata in PNG)
- FORCE_RUN=1 per esecuzione forzata (opzionale)

NOTE:
- Il segnale è LONG se match_top3(last) and filters(last) al momento del run, altrimenti FLAT.
"""

import os
import sys
import warnings
import smtplib
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, date, time, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

warnings.filterwarnings("ignore")

# Headless (GitHub Actions / CI)
HEADLESS = (os.getenv("GITHUB_ACTIONS", "").lower() == "true") or (os.getenv("CI", "").lower() == "true")
if HEADLESS:
    import matplotlib
    matplotlib.use("Agg")

import matplotlib.pyplot as plt


# ============================================================
# TIMEZONES
# ============================================================
try:
    from zoneinfo import ZoneInfo
    TZ_ROME = ZoneInfo("Europe/Rome")
    TZ_NY = ZoneInfo("America/New_York")
except Exception:
    TZ_ROME = None
    TZ_NY = None


# ============================================================
# CONFIG
# ============================================================
START_DATE = "2010-01-01"
ALLOWED_DAYS = [0, 1, 2, 3]   # Lun–Gio (esclude Venerdì nel backtest)

# Finestra opzionale (se vuoi farlo girare SOLO in certi minuti).
# Di default è DISATTIVATA: se vuoi attivarla metti ENFORCE_RUN_WINDOW=1 in GitHub env/secrets.
ENFORCE_RUN_WINDOW = os.getenv("ENFORCE_RUN_WINDOW", "0").strip() == "1"
RUN_WINDOW_START = time(17, 33)
RUN_WINDOW_END   = time(17, 55)


# ============================================================
# EMAIL CLIENT
# ============================================================
class EmailClient:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = os.getenv("SMTP_PORT", "587")
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")

        email_to_raw = (os.getenv("EMAIL_TO") or "").strip()
        self.email_to = email_to_raw if email_to_raw else "studiolegaleartax@gmail.com"

        self.from_name = os.getenv("EMAIL_FROM_NAME", "FAI-QUANT-SUPERIOR")
        self._validate_secrets()

    def _validate_secrets(self):
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

        print(f"[email] Invio a {self.email_to} via {host}:{port}")

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
def now_rome():
    try:
        if TZ_ROME is not None:
            return datetime.now(TZ_ROME)
    except Exception:
        pass
    return datetime.now()

def should_run_now() -> bool:
    # Forza sempre se FORCE_RUN=1
    if os.getenv("FORCE_RUN", "0").strip() == "1":
        return True
    if not ENFORCE_RUN_WINDOW:
        return True
    t = now_rome().time()
    return (t >= RUN_WINDOW_START) and (t <= RUN_WINDOW_END)

def next_weekday(d: date) -> date:
    """Prossimo giorno lavorativo (lun-ven)."""
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:  # 5=sab, 6=dom
        nd += timedelta(days=1)
    return nd

def safe_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return float(np.asarray(x).item())

def _to_tz_index(df: pd.DataFrame, tz_target) -> pd.DataFrame:
    """Normalizza indice datetime: se naive -> assume UTC; poi converte in tz_target."""
    if df is None or df.empty:
        return df
    idx = pd.to_datetime(df.index)
    try:
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        if tz_target is not None:
            idx = idx.tz_convert(tz_target)
    except Exception:
        pass
    out = df.copy()
    out.index = idx
    return out


def _intraday_snapshot(symbol: str,
                       run_time_rome: datetime,
                       tz_target,
                       session_open,
                       session_close,
                       period: str = "7d",
                       interval: str = "1m"):
    """
    Ritorna (px, ts_used, ohlcv_dict, source)
    - px: ultimo prezzo disponibile entro run_time_rome (in tz_target se possibile)
    - ts_used: timestamp dell'ultimo prezzo
    - ohlcv_dict: se session_open/session_close sono forniti, calcola OHLCV cumulati di OGGI in tz_target
    - source: "intraday" o "none"
    """
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         auto_adjust=False, progress=False)
    except Exception:
        return None, None, None, "none"

    if df is None or df.empty:
        return None, None, None, "none"

    df = _to_tz_index(df.copy(), tz_target)

    # limito al tempo del run convertito nel tz_target (se possibile)
    rt = run_time_rome
    try:
        if tz_target is not None and rt.tzinfo is not None:
            rt = rt.astimezone(tz_target)
    except Exception:
        pass

    df = df[df.index <= rt]
    if df.empty:
        return None, None, None, "none"

    ts_used = df.index[-1]

    # ultimo prezzo
    px = None
    if "Close" in df.columns:
        px = df["Close"].iloc[-1]
    else:
        for c in df.columns:
            if np.issubdtype(df[c].dtype, np.number):
                px = df[c].iloc[-1]
                break

    # OHLCV oggi (opzionale)
    ohlcv = None
    if session_open is not None and session_close is not None:
        today = ts_used.date()
        df_today = df[df.index.date == today]
        if not df_today.empty:
            try:
                df_today = df_today.between_time(session_open, session_close)
            except Exception:
                pass

            if not df_today.empty and all(k in df_today.columns for k in ["Open", "High", "Low", "Close"]):
                ohlcv = {
                    "Open": float(df_today["Open"].iloc[0]),
                    "High": float(df_today["High"].max()),
                    "Low": float(df_today["Low"].min()),
                    "Close": float(df_today["Close"].iloc[-1]),
                }
                if "Volume" in df_today.columns:
                    try:
                        ohlcv["Volume_raw"] = float(df_today["Volume"].sum())
                    except Exception:
                        ohlcv["Volume_raw"] = np.nan

    return px, ts_used, ohlcv, "intraday"


# ============================================================
# FIX YAHOO DF
# ============================================================
def fix_yahoo_df(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join([str(x) for x in col]) for col in df.columns]
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


# ============================================================
# LOADERS
# ============================================================
def load_ftsemib_daily():
    print("[*] Download FTSEMIB.MI (daily)…")
    df = yf.download("FTSEMIB.MI", start=START_DATE, interval="1d",
                     auto_adjust=False, progress=False)

    if df is None or df.empty:
        raise RuntimeError("Errore: nessun dato FTSEMIB da Yahoo (daily).")

    df = fix_yahoo_df(df).sort_index()
    close = extract_single_close(df)

    def find(words):
        for w in words:
            for col in df.columns:
                if w in col.lower():
                    return col
        return None

    o = find(["open"])
    h = find(["high"])
    l = find(["low"])
    v = find(["vol"])

    out = pd.DataFrame(index=df.index)
    if o and h and l:
        out["Open"]   = df[o]
        out["High"]   = df[h]
        out["Low"]    = df[l]
        out["Close"]  = close
        out["Volume"] = df[v] if v else 0.0
        return out.dropna()

    print("[WARN] OHLC non trovati → uso sintetici da Close (daily).")
    out["Close"] = close
    out["Open"]  = close.shift(1)
    out["High"]  = out[["Open", "Close"]].max(axis=1)
    out["Low"]   = out[["Open", "Close"]].min(axis=1)
    out["Volume"] = 0.0
    return out.dropna()


def load_aux_daily(symbol: str):
    df = yf.download(symbol, start=START_DATE, interval="1d",
                     auto_adjust=False, progress=False)
    if df is None or df.empty:
        return None
    df = fix_yahoo_df(df).sort_index()
    c = extract_single_close(df)
    return pd.DataFrame({"Close": c})


# ============================================================
# BUILD DATASET (daily + intraday synth oggi)
# ============================================================
def build_dataset_run_latest():
    """
    Ritorna:
      df_full: include anche la riga OGGI sintetica (se intraday disponibile)
      df_bt:   dataset per backtest (dropna su overnight)
      meta:    info su quali timestamp sono stati usati per FTSE/SPY/VIX
    """
    run_time = now_rome()
    today_rome = run_time.date()

    ftse = load_ftsemib_daily()
    df = ftse.copy()

    spy = load_aux_daily("SPY")
    vix = load_aux_daily("^VIX")

    if spy is not None:
        df = df.join(spy.rename(columns={"Close": "SPY_Close"}))
    else:
        df["SPY_Close"] = np.nan

    if vix is not None:
        df = df.join(vix.rename(columns={"Close": "VIX_Close"}))
    else:
        df["VIX_Close"] = np.nan

    meta = {
        "run_time_rome": run_time,
        "ftse_source": "daily",
        "ftse_ts_used": None,
        "spy_source": "daily",
        "spy_ts_used": None,
        "vix_source": "daily",
        "vix_ts_used": None,
    }

    # FTSE intraday (Roma 09:00–17:30)
    _, ftse_ts, ftse_ohlcv, _ = _intraday_snapshot(
        "FTSEMIB.MI",
        run_time_rome=run_time,
        tz_target=TZ_ROME,
        session_open=time(9, 0),
        session_close=time(17, 30),
        period="7d",
        interval="1m",
    )
    if ftse_ohlcv is not None and ftse_ts is not None and ftse_ts.date() == today_rome:
        row_ts = pd.Timestamp(today_rome)
        df.loc[row_ts, "Open"] = ftse_ohlcv["Open"]
        df.loc[row_ts, "High"] = ftse_ohlcv["High"]
        df.loc[row_ts, "Low"] = ftse_ohlcv["Low"]
        df.loc[row_ts, "Close"] = ftse_ohlcv["Close"]
        df.loc[row_ts, "Volume"] = ftse_ohlcv.get("Volume_raw", np.nan)

        meta["ftse_source"] = "intraday_synth"
        meta["ftse_ts_used"] = ftse_ts

    # SPY intraday (NY 09:30–16:00)
    spy_px, spy_ts, _, _ = _intraday_snapshot(
        "SPY",
        run_time_rome=run_time,
        tz_target=TZ_NY,
        session_open=time(9, 30),
        session_close=time(16, 0),
        period="7d",
        interval="1m",
    )
    if spy_px is not None and spy_ts is not None:
        try:
            spy_day_rome = spy_ts.astimezone(TZ_ROME).date() if TZ_ROME is not None else spy_ts.date()
        except Exception:
            spy_day_rome = spy_ts.date()
        if spy_day_rome == today_rome:
            row_ts = pd.Timestamp(today_rome)
            df.loc[row_ts, "SPY_Close"] = float(spy_px)
            meta["spy_source"] = "intraday"
            meta["spy_ts_used"] = spy_ts

    # VIX intraday (NY 09:30–16:00)
    vix_px, vix_ts, _, _ = _intraday_snapshot(
        "^VIX",
        run_time_rome=run_time,
        tz_target=TZ_NY,
        session_open=time(9, 30),
        session_close=time(16, 0),
        period="7d",
        interval="1m",
    )
    if vix_px is not None and vix_ts is not None:
        try:
            vix_day_rome = vix_ts.astimezone(TZ_ROME).date() if TZ_ROME is not None else vix_ts.date()
        except Exception:
            vix_day_rome = vix_ts.date()
        if vix_day_rome == today_rome:
            row_ts = pd.Timestamp(today_rome)
            df.loc[row_ts, "VIX_Close"] = float(vix_px)
            meta["vix_source"] = "intraday"
            meta["vix_ts_used"] = vix_ts

    # ---- features
    df = df.sort_index()

    df["Close_prev"] = df["Close"].shift(1)
    df["gap_open"] = df["Open"] / df["Close_prev"] - 1

    df["spy_ret"] = df["SPY_Close"].pct_change()
    df["vix_ret"] = df["VIX_Close"].pct_change()

    # volume z-score (per oggi: proiezione semplice su sessione Roma)
    df["Volume_raw"] = df["Volume"].copy()
    df["Volume_for_z"] = df["Volume"].copy()

    row_ts_today = pd.Timestamp(today_rome)
    if row_ts_today in df.index and meta["ftse_source"] == "intraday_synth":
        vol_raw = df.loc[row_ts_today, "Volume_raw"]
        try:
            vol_raw_f = float(vol_raw) if pd.notna(vol_raw) else np.nan
        except Exception:
            vol_raw_f = np.nan

        try:
            rt = meta["run_time_rome"]
            if rt.tzinfo is None and TZ_ROME is not None:
                rt = rt.replace(tzinfo=TZ_ROME)
            rt = rt.astimezone(TZ_ROME) if TZ_ROME is not None else rt
            session_start = datetime.combine(today_rome, time(9, 0))
            session_end = datetime.combine(today_rome, time(17, 30))
            if TZ_ROME is not None:
                session_start = session_start.replace(tzinfo=TZ_ROME)
                session_end = session_end.replace(tzinfo=TZ_ROME)

            total_secs = max(1.0, (session_end - session_start).total_seconds())
            elapsed = (min(rt, session_end) - session_start).total_seconds()
            frac = max(0.0, min(1.0, elapsed / total_secs))
        except Exception:
            frac = 0.0

        if pd.notna(vol_raw_f) and vol_raw_f > 0 and frac > 0.05:
            df.loc[row_ts_today, "Volume_for_z"] = vol_raw_f / frac
        else:
            df.loc[row_ts_today, "Volume_for_z"] = vol_raw_f

    vol_ma = df["Volume_for_z"].rolling(20).mean()
    vol_std = df["Volume_for_z"].rolling(20).std(ddof=0)
    df["vol_z"] = (df["Volume_for_z"] - vol_ma) / vol_std
    df["vol_z"] = df["vol_z"].replace([np.inf, -np.inf], np.nan)

    # ricalcolo spy_ret/vix_ret per oggi se intraday: (px_now / prev_close - 1)
    if row_ts_today in df.index:
        if meta["spy_source"] == "intraday":
            prev = df.loc[df.index < row_ts_today, "SPY_Close"].dropna()
            if not prev.empty and pd.notna(df.loc[row_ts_today, "SPY_Close"]):
                df.loc[row_ts_today, "spy_ret"] = df.loc[row_ts_today, "SPY_Close"] / prev.iloc[-1] - 1
        if meta["vix_source"] == "intraday":
            prev = df.loc[df.index < row_ts_today, "VIX_Close"].dropna()
            if not prev.empty and pd.notna(df.loc[row_ts_today, "VIX_Close"]):
                df.loc[row_ts_today, "vix_ret"] = df.loc[row_ts_today, "VIX_Close"] / prev.iloc[-1] - 1

    # overnight per backtest
    df["Open_next"] = df["Open"].shift(-1)
    df["overnight_ret"] = df["Open_next"] / df["Close"] - 1

    df["dow"] = df.index.dayofweek

    df_bt = df.dropna(subset=["Open", "Close", "Open_next", "overnight_ret"]).copy()
    return df, df_bt, meta


# ============================================================
# TOP3 pattern logico
# ============================================================
def match_top3(r):
    cond = False

    if not pd.isna(r.get("spy_ret")):
        cond |= (0 <= r["gap_open"] < 0.01) and (0 <= r["spy_ret"] < 0.01)

    if not pd.isna(r.get("vix_ret")):
        cond |= (-0.10 <= r["vix_ret"] < -0.05)

    if not pd.isna(r.get("vol_z")):
        cond |= (-1.5 <= r["vol_z"] < -0.5)

    return bool(cond)


# ============================================================
# FILTRI (Venerdì escluso)
# ============================================================
def filters(r):
    if not pd.isna(r.get("spy_ret")):
        if r["spy_ret"] < -0.005:
            return False

    if int(r["dow"]) not in ALLOWED_DAYS:
        return False

    return True


# ============================================================
# BACKTEST
# ============================================================
def run_backtest(df_bt: pd.DataFrame):
    df_bt = df_bt.copy()
    df_bt["signal"] = df_bt.apply(lambda r: match_top3(r) and filters(r), axis=1)
    trades = df_bt[df_bt["signal"]].copy()

    if trades.empty:
        return trades, pd.Series(dtype=float), 0, 0, 0, 0, 0

    trades["pnl"] = trades["overnight_ret"]
    trades["pnl_points"] = trades["overnight_ret"] * trades["Close"]
    trades["raw_points"] = trades["Open_next"] - trades["Close"]

    equity = (1 + trades["overnight_ret"]).cumprod()

    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = equity.iloc[-1] ** (1 / years) - 1 if years > 0 else 0

    avg = trades["overnight_ret"].mean()
    avg_points = trades["pnl_points"].mean()
    win = (trades["overnight_ret"] > 0).mean()

    return trades, equity, cagr, avg, win, avg_points, trades["raw_points"].mean()


# ============================================================
# SYSTEM → dashboard
# ============================================================
class System:
    def __init__(self, trades):
        self.initial_capital = 100000
        self.trades = trades.copy()

        self.trades["pnl_$"] = self.trades["pnl"] * self.initial_capital
        self.trades["cum_pnl"] = self.trades["pnl_$"].cumsum()
        self.equity_curve = list(self.initial_capital + self.trades["cum_pnl"])

        peaks = np.maximum.accumulate(self.equity_curve)
        self.drawdown = (peaks - np.array(self.equity_curve)) / peaks * 100

        self.trades["result"] = ["WIN" if x > 0 else "LOSS" for x in self.trades["pnl_$"]]
        self.trades["trade"] = list(range(len(self.trades)))
        self.trades["position_pct"] = 100


# ============================================================
# MEGA DASHBOARD
# ============================================================
def plot_mega_dashboard(system, out_png="mega_dashboard.png"):
    df = system.trades.copy()
    n = range(len(df))

    fig = plt.figure(figsize=(22, 16))
    gs = fig.add_gridspec(4, 3, hspace=0.35, wspace=0.3)

    ax1 = fig.add_subplot(gs[0, :2])
    ax1.plot(system.equity_curve)
    ax1.fill_between(n, system.initial_capital, system.equity_curve, alpha=0.3)
    ax1.set_title("EQUITY CURVE")
    ax1.grid(True)

    ax2 = fig.add_subplot(gs[0, 2])
    ax2.fill_between(n, 0, system.drawdown)
    ax2.set_title(f"MAX DD: {system.drawdown.max():.2f}%")
    ax2.grid(True)

    ax3 = fig.add_subplot(gs[1, 0])
    colors = ['green' if x > 0 else 'red' for x in df["pnl_$"]]
    ax3.bar(df["trade"], df["pnl_$"], color=colors)
    ax3.set_title("P&L PER TRADE")
    ax3.grid(True, axis='y')

    ax4 = fig.add_subplot(gs[1, 1])
    wins = len(df[df["result"] == "WIN"])
    losses = len(df[df["result"] == "LOSS"])
    ax4.pie([wins, losses], labels=["WIN", "LOSS"], autopct="%1.1f%%")
    ax4.set_title("WIN / LOSS")

    ax5 = fig.add_subplot(gs[1, 2])
    ax5.plot(df["cum_pnl"])
    ax5.set_title("CUMULATIVE P&L")
    ax5.grid(True)

    ax6 = fig.add_subplot(gs[2, 0])
    ax6.plot(df["position_pct"])
    ax6.set_title("POSITION SIZE")
    ax6.grid(True)

    ax7 = fig.add_subplot(gs[2, 1])
    ax7.hist(df[df["result"] == "WIN"]["pnl_$"], bins=30)
    ax7.set_title("WIN DISTRIBUTION")

    ax8 = fig.add_subplot(gs[2, 2])
    ax8.hist(df[df["result"] == "LOSS"]["pnl_$"], bins=30)
    ax8.set_title("LOSS DISTRIBUTION")

    ax9 = fig.add_subplot(gs[3, 0])
    seq = [1 if x == "WIN" else -1 for x in df["result"]]
    ax9.bar(n, seq)
    ax9.set_title("TRADE SEQUENCE")
    ax9.grid(True, axis='y')

    ax10 = fig.add_subplot(gs[3, 1])
    ret_pct = [(x - system.initial_capital) / system.initial_capital * 100 for x in system.equity_curve]
    ax10.plot(ret_pct)
    ax10.set_title("RETURN %")
    ax10.grid(True)

    ax11 = fig.add_subplot(gs[3, 2])
    step = max(1, len(df) // 27)
    monthly = [df["pnl_$"].iloc[i * step:(i + 1) * step].sum() for i in range(27)]
    ax11.bar(range(len(monthly)), monthly)
    ax11.set_title("MONTHLY P&L")
    ax11.grid(True, axis='y')

    fig.suptitle("FAI QUANT SUPERIOR — MEGA DASHBOARD", fontsize=20)

    if HEADLESS:
        fig.savefig(out_png, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return out_png
    else:
        plt.show()
        return None


# ============================================================
# EMAIL BODY
# ============================================================
def _fmt_ts(ts):
    if ts is None:
        return "n/a"
    try:
        return ts.isoformat()
    except Exception:
        return str(ts)

def build_email_body(df_full, meta, metrics, signal_label, data_day_ftse, forecast_day) -> str:
    run_time = meta["run_time_rome"]
    calendar_day = run_time.date()

    spy_last_day = df_full["SPY_Close"].dropna().index[-1].date() if not df_full["SPY_Close"].dropna().empty else None
    vix_last_day = df_full["VIX_Close"].dropna().index[-1].date() if not df_full["VIX_Close"].dropna().empty else None

    last = df_full.iloc[-1]

    lines = []
    lines.append("=== FAI QUANT SUPERIOR — RUN-LATEST ===")
    lines.append(f"Previsione emessa (Rome):   {run_time.isoformat()}")
    lines.append(f"Giorno calendario (Rome):   {calendar_day}")
    lines.append("")
    lines.append("=== DATI USATI ===")
    if meta.get("ftse_ts_used") is not None:
        lines.append(f"FTSE day: {data_day_ftse} | source: {meta['ftse_source']} | ts: {_fmt_ts(meta['ftse_ts_used'])}")
    else:
        lines.append(f"FTSE day: {data_day_ftse} | source: {meta['ftse_source']}")
    if meta.get("spy_ts_used") is not None:
        lines.append(f"SPY  day: {spy_last_day} | source: {meta['spy_source']} | ts: {_fmt_ts(meta['spy_ts_used'])}")
    else:
        lines.append(f"SPY  day: {spy_last_day} | source: {meta['spy_source']}")
    if meta.get("vix_ts_used") is not None:
        lines.append(f"VIX  day: {vix_last_day} | source: {meta['vix_source']} | ts: {_fmt_ts(meta['vix_ts_used'])}")
    else:
        lines.append(f"VIX  day: {vix_last_day} | source: {meta['vix_source']}")
    lines.append("")
    lines.append(f"Sessione prevista (giorno): {forecast_day}")
    lines.append(f"SEGNALE: {signal_label}")
    lines.append("")
    lines.append("--- INPUT SEGNALE (ultimo record) ---")
    try:
        lines.append(f"dow:      {int(last['dow'])}   (0=Lun ... 4=Ven)")
    except Exception:
        lines.append("dow:      n/a")
    lines.append(f"gap_open: {safe_float(last['gap_open']):+.6f}" if not pd.isna(last.get("gap_open")) else "gap_open: n/a")
    lines.append(f"vol_z:    {safe_float(last['vol_z']):+.6f}" if not pd.isna(last.get("vol_z")) else "vol_z:    n/a")
    lines.append(f"spy_ret:  {safe_float(last['spy_ret']):+.6f}" if not pd.isna(last.get("spy_ret")) else "spy_ret:  n/a")
    lines.append(f"vix_ret:  {safe_float(last['vix_ret']):+.6f}" if not pd.isna(last.get("vix_ret")) else "vix_ret:  n/a")
    lines.append("")
    lines.append("=== METRICHE BACKTEST (Venerdì escluso) ===")
    for k, v in metrics.items():
        lines.append(f"{k:<14} {v}")

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================
def main():
    if not should_run_now():
        rt = now_rome()
        print(f"[skip] Ora Rome={rt.time()} fuori finestra {RUN_WINDOW_START}-{RUN_WINDOW_END}.")
        return

    df_full, df_bt, meta = build_dataset_run_latest()
    trades, equity, cagr, avg, winrate, avg_points, avg_raw = run_backtest(df_bt)

    # Metriche
    metrics = {
        "Trades:": f"{len(trades)}",
        "Avg %:": f"{avg*100:.4f}%" if len(trades) else "n/a",
        "Avg punti:": f"{avg_points:.2f}" if len(trades) else "n/a",
        "Avg raw:": f"{avg_raw:.2f}" if len(trades) else "n/a",
        "Winrate:": f"{winrate*100:.2f}%" if len(trades) else "n/a",
        "CAGR:": f"{cagr*100:.2f}%" if len(trades) else "n/a",
        "TotalRet:": f"{(equity.iloc[-1]-1)*100:.2f}%" if (equity is not None and not equity.empty) else "n/a",
    }

    # Giorni
    run_time = meta["run_time_rome"]
    today_rome = run_time.date()

    data_day_ftse = df_full.index[-1].date()
    forecast_day = next_weekday(data_day_ftse)

    # Segnale
    last = df_full.iloc[-1]
    sig = match_top3(last) and filters(last)
    signal_label = "LONG (overnight)" if sig else "FLAT"

    # Dashboard (solo se ci sono trades)
    dashboard_path = None
    if not trades.empty:
        system = System(trades)
        dashboard_path = plot_mega_dashboard(system)

    # Log console
    print("\n=== SEGNALE PER PROSSIMA SESSIONE ===")
    print(f"Previsione emessa (Rome): {run_time.isoformat()}")
    print(f"Giorno calendario (Rome): {today_rome}")
    print(f"Dati FTSE (day):          {data_day_ftse} | source: {meta['ftse_source']} | ts: {meta['ftse_ts_used'].isoformat() if meta['ftse_ts_used'] is not None else 'n/a'}")
    print(f"Sessione prevista:        {forecast_day}")
    print(f"SEGNALE:                  {signal_label}")
    if dashboard_path:
        print(f"[i] Dashboard salvata: {dashboard_path}")

    # Email
    subject = f"FAI-QUANT-SUPERIOR | Data:{data_day_ftse} | Prev:{forecast_day} | {signal_label}"
    body = build_email_body(df_full, meta, metrics, signal_label, data_day_ftse, forecast_day)
    if dashboard_path:
        body += f"\n\n[Dashboard] File generato nel run: {dashboard_path} (headless)."

    EmailClient().send(subject, body)


if __name__ == "__main__":
    main()

