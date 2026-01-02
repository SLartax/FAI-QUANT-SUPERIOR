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
SNAPSHOT_TIME_ROME = dt.time(17, 30)     # prezzo target: 17:30 Europe/Rome
RUN_WINDOW_START = dt.time(17, 33)       # esegui (e manda mail) solo dopo che Yahoo ha pubblicato i minuti
RUN_WINDOW_END = dt.time(17, 55)         # finestra di tolleranza

INTRADAY_INTERVAL = "1m"
INTRADAY_PERIOD = "7d"


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
        required = {
            "SMTP_HOST": self.smtp_host,
            "SMTP_PORT": self.smtp_port,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASS": self.smtp_pass,
            "EMAIL_TO": self.email_to,
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

        with smtplib.SMTP(self.smtp_host, int(self.smtp_port)) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.send_message(msg)


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
        raise RuntimeError(f"Download fallito per {symbol}: {last_err}")
    return pd.DataFrame()

def load_daily_ohlcv(symbol: str) -> pd.DataFrame:
    df = yf_download(symbol, start=START_DATE, interval="1d")
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.sort_index()
    out = pd.DataFrame(index=df.index)
    out["Open"] = extract_col(df, "open")
    out["High"] = extract_col(df, "high")
    out["Low"] = extract_col(df, "low")
    out["Close"] = extract_col(df, "close")
    out["Volume"] = extract_col(df, "vol")
    return out

def load_daily_close(symbol: str) -> pd.Series:
    df = yf_download(symbol, start=START_DATE, interval="1d")
    if df is None or df.empty:
        return pd.Series(dtype=float)
    df = df.sort_index()
    s = extract_col(df, "close")
    s.name = "Close"
    return s

def load_intraday(symbol: str) -> pd.DataFrame:
    df = yf_download(symbol, period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.sort_index()
    df = to_rome_index(df)
    out = pd.DataFrame(index=df.index)
    out["Open"] = extract_col(df, "open")
    out["High"] = extract_col(df, "high")
    out["Low"] = extract_col(df, "low")
    out["Close"] = extract_col(df, "close")
    out["Volume"] = extract_col(df, "vol") if any("vol" in c.lower() for c in df.columns) else np.nan
    return out

def intraday_close_at(symbols: list[str], day: dt.date):
    """
    Prova una lista di simboli; ritorna (symbol_usato, prezzo, timestamp_rome) per l'ultima barra <= 17:30.
    """
    target = target_dt_rome(day)
    for sym in symbols:
        intr = load_intraday(sym)
        if intr is None or intr.empty:
            continue

        intr_day = intr[intr.index.date == day]
        if intr_day.empty:
            continue

        upto = intr_day[intr_day.index <= target]
        if upto.empty:
            # fallback: ultimo tick disponibile del giorno
            ts = intr_day.index.max()
            px = float(intr_day.loc[ts, "Close"])
            return sym, px, ts

        ts = upto.index.max()
        px = float(upto.loc[ts, "Close"])
        return sym, px, ts

    return None, None, None

def synth_daily_from_intraday(symbol: str, day: dt.date):
    """
    Crea una riga daily usando dati intraday del giorno (fino a 17:30 Rome per Close).
    Ritorna (row_series, ts_close_rome) oppure (None, None).
    """
    target = target_dt_rome(day)
    intr = load_intraday(symbol)
    if intr is None or intr.empty:
        return None, None

    intr_day = intr[intr.index.date == day]
    if intr_day.empty:
        return None, None

    open_px = float(intr_day.iloc[0]["Open"])
    high_px = float(intr_day["High"].max())
    low_px = float(intr_day["Low"].min())

    upto = intr_day[intr_day.index <= target]
    if upto.empty:
        close_ts = intr_day.index.max()
        close_px = float(intr_day.loc[close_ts, "Close"])
    else:
        close_ts = upto.index.max()
        close_px = float(upto.loc[close_ts, "Close"])

    vol = float(intr_day["Volume"].fillna(0).sum()) if "Volume" in intr_day.columns else np.nan

    row = pd.Series(
        {"Open": open_px, "High": high_px, "Low": low_px, "Close": close_px, "Volume": vol},
        name=pd.Timestamp(day)
    )
    return row, close_ts


# ============================================================
# DATASET BUILD
# ============================================================
def build_dataset():
    meta = {
        "today_rome": str(today_rome()),
        "ftse_source_today": "daily",
        "ftse_close_ts_rome": None,
        "spy_symbol_used": None,
        "spy_snapshot_ts_rome": None,
        "vix_symbol_used": None,
        "vix_snapshot_ts_rome": None,
    }

    day = today_rome()

    # FTSEMIB daily history
    df = load_daily_ohlcv("FTSEMIB.MI")
    if df is None or df.empty:
        raise RuntimeError("Nessun dato FTSEMIB disponibile")

    df = df.sort_index()

    # Prova sempre a costruire la riga di oggi da intraday (real-time)
    ftse_row, ftse_ts = synth_daily_from_intraday("FTSEMIB.MI", day)
    if ftse_row is not None:
        meta["ftse_source_today"] = "intraday_synth"
        meta["ftse_close_ts_rome"] = str(ftse_ts)
        df.loc[pd.Timestamp(day)] = ftse_row.values
        df = df.sort_index()

    # SPY / VIX daily close history (per prendere la close di ieri)
    spy_close = load_daily_close("SPY")
    vix_close = load_daily_close("^VIX")

    df["spy_close"] = spy_close.reindex(df.index) if spy_close is not None else np.nan
    df["vix_close"] = vix_close.reindex(df.index) if vix_close is not None else np.nan

    df["spy_ret"] = df["spy_close"].pct_change()
    df["vix_ret"] = df["vix_close"].pct_change()

    # Override OGGI: snapshot intraday alle 17:30 (Rome) anche senza chiusura USA
    # SPY
    prev_spy = df.loc[df.index < pd.Timestamp(day), "spy_close"].dropna()
    if not prev_spy.empty:
        prev_close = float(prev_spy.iloc[-1])
        sym, px, ts = intraday_close_at(["SPY"], day)
        if px is not None and prev_close > 0:
            df.loc[pd.Timestamp(day), "spy_ret"] = (float(px) / prev_close) - 1.0
            meta["spy_symbol_used"] = sym
            meta["spy_snapshot_ts_rome"] = str(ts)

    # VIX: ^VIX intraday spesso è instabile; fallback su ETF proxy
    prev_vix = df.loc[df.index < pd.Timestamp(day), "vix_close"].dropna()
    if not prev_vix.empty:
        prev_close = float(prev_vix.iloc[-1])
        sym, px, ts = intraday_close_at(["^VIX", "VIXY", "VXX"], day)
        if px is not None and prev_close > 0:
            df.loc[pd.Timestamp(day), "vix_ret"] = (float(px) / prev_close) - 1.0
            meta["vix_symbol_used"] = sym
            meta["vix_snapshot_ts_rome"] = str(ts)

    # Feature FTSE
    df["Close_prev"] = df["Close"].shift(1)
    df["gap_open"] = df["Open"] / df["Close_prev"] - 1

    df["vol_ma"] = df["Volume"].rolling(20).mean()
    df["vol_std"] = df["Volume"].rolling(20).std()
    df["vol_z"] = (df["Volume"] - df["vol_ma"]) / df["vol_std"]

    df["dow"] = df.index.dayofweek

    return df, meta


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
# SEGNALE LIVE (oggi incluso)
# ============================================================
def get_next_overnight_signal(df):
    day = today_rome()

    # NON richiedere spy_ret/vix_ret non-NaN: la riga di oggi deve sopravvivere.
    df_live = df.dropna(subset=["gap_open", "vol_z", "dow"]).copy()
    if df_live.empty:
        raise RuntimeError("ERRORE: Nessun dato valido dopo dropna(gap_open, vol_z, dow)")

    last_row = df_live.iloc[-1]
    last_date = df_live.index[-1].date()

    if last_date > day:
        raise RuntimeError(f"ERRORE: data piu recente ({last_date}) non è chiusa")

    signal = match_top3(last_row) and filters(last_row)

    debug = {
        "ref_date": str(last_date),
        "gap_open": float(last_row["gap_open"]),
        "vol_z": float(last_row["vol_z"]),
        "spy_ret": None if pd.isna(last_row.get("spy_ret")) else float(last_row.get("spy_ret")),
        "vix_ret": None if pd.isna(last_row.get("vix_ret")) else float(last_row.get("vix_ret")),
        "dow": int(last_row["dow"]),
    }

    return last_date, signal, debug


# ============================================================
# MAIN
# ============================================================
def main():
    # Se siamo fuori finestra (doppio cron), esci senza mandare mail
    if not should_run_now():
        print(f"[skip] Ora Rome={now_rome()} fuori finestra {RUN_WINDOW_START}-{RUN_WINDOW_END}.")
        return

    mailer = EmailClient()

    df, meta = build_dataset()
    ref_date, signal, dbg = get_next_overnight_signal(df)

    status = "LONG" if signal else "FLAT"
    subject = f"FAI QUANT SUPERIOR – Overnight {status}"

    body = f"""
FAI QUANT SUPERIOR – SEGNALE OVERNIGHT (snapshot <= 17:30 Europe/Rome)

Esecuzione (Rome): {now_rome()}
Seduta di riferimento (FTSE): {ref_date}
Fonte FTSE oggi: {meta.get("ftse_source_today")}
FTSE close timestamp (Rome): {meta.get("ftse_close_ts_rome")}

SPY symbol: {meta.get("spy_symbol_used")}
SPY snapshot timestamp (Rome): {meta.get("spy_snapshot_ts_rome")}

VIX symbol: {meta.get("vix_symbol_used")}
VIX snapshot timestamp (Rome): {meta.get("vix_snapshot_ts_rome")}

Segnale valido per il prossimo overnight utile
Segnale: {status}

--- DEBUG (valori usati) ---
gap_open: {dbg["gap_open"]:+.6f}
vol_z:    {dbg["vol_z"]:+.6f}
spy_ret:  {("NA" if dbg["spy_ret"] is None else f"{dbg['spy_ret']:+.6f}")}
vix_ret:  {("NA" if dbg["vix_ret"] is None else f"{dbg['vix_ret']:+.6f}")}
dow:      {dbg["dow"]}
"""

    print(body)
    mailer.send(subject, body)


if __name__ == "__main__":
    main()
