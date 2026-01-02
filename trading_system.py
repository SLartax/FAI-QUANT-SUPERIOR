# -*- coding: utf-8 -*-
"""
FAI QUANT SUPERIOR – OVERNIGHT SIGNAL (LIVE @ 17:30 Europe/Rome)
---------------------------------------------------------------
Obiettivo (richiesta utente):
- Il segnale del giorno deve usare i dati della seduta italiana del giorno stesso
- SPY/VIX NON devono richiedere la chiusura USA: usare snapshot prezzo alle 17:30 Europe/Rome
- Nessun look-ahead: per SPY/VIX uso solo il prezzo <= 17:30 Europe/Rome
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
ALLOWED_DAYS = [0, 1, 2, 3]  # Lun–Gio

TZ_ROME = ZoneInfo("Europe/Rome")
SNAPSHOT_TIME_ROME = dt.time(17, 30)  # come richiesto: 17:30 Europe/Rome
INTRADAY_INTERVAL = "1m"
INTRADAY_PERIOD = "7d"  # sufficiente per 1m

# =========================
# EMAIL CLIENT
# =========================
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
        # Meglio: Nome <email>
        msg["From"] = f"{self.from_name} <{self.smtp_user}>"
        msg["To"] = self.email_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(self.smtp_host, int(self.smtp_port)) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.send_message(msg)


# =========================
# HELPERS TIME / YFINANCE
# =========================
def now_rome() -> dt.datetime:
    return dt.datetime.now(TZ_ROME)

def today_rome() -> dt.date:
    return now_rome().date()

def target_dt_rome(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, SNAPSHOT_TIME_ROME, tzinfo=TZ_ROME)

def _fix_yahoo_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join(map(str, c)) for c in df.columns]
    return df

def _extract_col(df: pd.DataFrame, key: str) -> pd.Series:
    # key: "open"/"high"/"low"/"close"/"vol"
    cols = [c for c in df.columns if key in c.lower()]
    if not cols:
        raise RuntimeError(f"Colonna {key} non trovata")
    return df[cols[0]]

def _to_rome_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    idx = df.index
    # yfinance a volte dà tz-aware (es. US/Eastern), a volte naive
    if getattr(idx, "tz", None) is None:
        # assumo UTC se naive (runner GitHub spesso così)
        idx = idx.tz_localize("UTC")
    idx = idx.tz_convert(TZ_ROME)
    df = df.copy()
    df.index = idx
    return df

def _yf_download(symbol: str, **kwargs) -> pd.DataFrame:
    # piccolo retry per robustezza
    last_err = None
    for _ in range(3):
        try:
            df = yf.download(symbol, progress=False, auto_adjust=False, **kwargs)
            df = _fix_yahoo_df(df)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            last_err = e
    if last_err:
        raise RuntimeError(f"Download fallito per {symbol}: {last_err}")
    return pd.DataFrame()

def load_daily_ohlcv(symbol: str) -> pd.DataFrame:
    df = _yf_download(symbol, start=START_DATE, interval="1d")
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.sort_index()
    out = pd.DataFrame(index=df.index)
    out["Open"] = _extract_col(df, "open")
    out["High"] = _extract_col(df, "high")
    out["Low"] = _extract_col(df, "low")
    out["Close"] = _extract_col(df, "close")
    out["Volume"] = _extract_col(df, "vol")
    return out

def load_daily_close(symbol: str) -> pd.Series:
    df = _yf_download(symbol, start=START_DATE, interval="1d")
    if df is None or df.empty:
        return pd.Series(dtype=float)
    df = df.sort_index()
    close = _extract_col(df, "close")
    close.name = "Close"
    return close

def load_intraday(symbol: str) -> pd.DataFrame:
    df = _yf_download(symbol, period=INTRADAY_PERIOD, interval=INTRADAY_INTERVAL)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.sort_index()
    df = _to_rome_index(df)
    # uniformo colonne
    out = pd.DataFrame(index=df.index)
    out["Open"] = _extract_col(df, "open")
    out["High"] = _extract_col(df, "high")
    out["Low"] = _extract_col(df, "low")
    out["Close"] = _extract_col(df, "close")
    if any("vol" in c.lower() for c in df.columns):
        out["Volume"] = _extract_col(df, "vol")
    else:
        out["Volume"] = np.nan
    return out

def intraday_close_at(symbol: str, day: dt.date) -> tuple[float, dt.datetime] | tuple[None, None]:
    """Ritorna (prezzo_close, timestamp_usato) per l'ultima barra <= 17:30 Europe/Rome del giorno."""
    target = target_dt_rome(day)
    intr = load_intraday(symbol)
    if intr is None or intr.empty:
        return None, None

    intr_day = intr[(intr.index.date == day)]
    if intr_day.empty:
        return None, None

    intr_upto = intr_day[intr_day.index <= target]
    if intr_upto.empty:
        # fallback: ultimo prezzo disponibile del giorno (meglio di niente)
        ts = intr_day.index.max()
        px = float(intr_day.loc[ts, "Close"])
        return px, ts

    ts = intr_upto.index.max()
    px = float(intr_upto.loc[ts, "Close"])
    return px, ts

def synthesize_daily_from_intraday(symbol: str, day: dt.date) -> tuple[pd.Series, dict] | tuple[None, dict]:
    """Crea una riga daily (Open/High/Low/Close/Volume) dal minuto intraday del giorno."""
    target = target_dt_rome(day)
    intr = load_intraday(symbol)
    meta = {"used": False, "ts_close": None}
    if intr is None or intr.empty:
        return None, meta

    intr_day = intr[(intr.index.date == day)]
    if intr_day.empty:
        return None, meta

    open_px = float(intr_day.iloc[0]["Open"])
    high_px = float(intr_day["High"].max())
    low_px = float(intr_day["Low"].min())

    intr_upto = intr_day[intr_day.index <= target]
    if intr_upto.empty:
        close_ts = intr_day.index.max()
        close_px = float(intr_day.loc[close_ts, "Close"])
    else:
        close_ts = intr_upto.index.max()
        close_px = float(intr_upto.loc[close_ts, "Close"])

    # volume: somma se presente
    if "Volume" in intr_day.columns and intr_day["Volume"].notna().any():
        vol = float(intr_day["Volume"].fillna(0).sum())
    else:
        vol = np.nan

    meta["used"] = True
    meta["ts_close"] = close_ts

    row = pd.Series(
        {"Open": open_px, "High": high_px, "Low": low_px, "Close": close_px, "Volume": vol},
        name=pd.Timestamp(day)
    )
    return row, meta


# =========================
# DATASET BUILD
# =========================
def build_dataset() -> tuple[pd.DataFrame, dict]:
    meta = {
        "today": str(today_rome()),
        "ftse_today_source": "daily",
        "ftse_today_close_ts_rome": None,
        "spy_snapshot_ts_rome": None,
        "vix_snapshot_ts_rome": None,
        "vix_symbol_used": "^VIX",
    }

    day = today_rome()

    # 1) FTSEMIB daily
    df = load_daily_ohlcv("FTSEMIB.MI")
    if df is None or df.empty:
        raise RuntimeError("Nessun dato FTSEMIB disponibile")

    df = df.sort_index()

    # Se Yahoo daily non ha ancora la riga di oggi, la ricostruisco da intraday
    if df.index.max().date() < day:
        row, m = synthesize_daily_from_intraday("FTSEMIB.MI", day)
        if row is not None:
            meta["ftse_today_source"] = "intraday_synth"
            if m.get("ts_close") is not None:
                meta["ftse_today_close_ts_rome"] = str(m["ts_close"])
            df.loc[pd.Timestamp(day)] = row.values
            df = df.sort_index()

    # 2) SPY / VIX daily close history
    spy_close = load_daily_close("SPY")
    vix_close = load_daily_close("^VIX")

    # fallback VIX proxy se ^VIX daily vuoto
    if vix_close is None or vix_close.empty:
        vix_close = load_daily_close("VIXY")
        meta["vix_symbol_used"] = "VIXY"

    # allineo su index FTSE
    if spy_close is not None and not spy_close.empty:
        df["spy_close"] = spy_close.reindex(df.index)
        df["spy_ret"] = df["spy_close"].pct_change()

    if vix_close is not None and not vix_close.empty:
        df["vix_close"] = vix_close.reindex(df.index)
        df["vix_ret"] = df["vix_close"].pct_change()

    # 3) Override OGGI: SPY/VIX intraday snapshot @ 17:30 Rome (anche se USA non chiusi)
    # spy_ret_today = (spy_price_1730 / spy_prev_close - 1)
    if "spy_close" in df.columns:
        # prev close = ultimo non-NaN PRIMA di oggi
        prev = df.loc[df.index < pd.Timestamp(day), "spy_close"].dropna()
        if not prev.empty:
            prev_close = float(prev.iloc[-1])
            spy_px, spy_ts = intraday_close_at("SPY", day)
            if spy_px is not None and prev_close > 0:
                df.loc[pd.Timestamp(day), "spy_ret"] = (float(spy_px) / prev_close) - 1.0
                meta["spy_snapshot_ts_rome"] = str(spy_ts)

    # vix_ret_today con simbolo principale, altrimenti proxy VIXY
    vix_symbol = "^VIX" if meta["vix_symbol_used"] == "^VIX" else "VIXY"
    if "vix_close" in df.columns:
        prev = df.loc[df.index < pd.Timestamp(day), "vix_close"].dropna()
        if not prev.empty:
            prev_close = float(prev.iloc[-1])
            vix_px, vix_ts = intraday_close_at(vix_symbol, day)
            if vix_px is not None and prev_close > 0:
                df.loc[pd.Timestamp(day), "vix_ret"] = (float(vix_px) / prev_close) - 1.0
                meta["vix_snapshot_ts_rome"] = str(vix_ts)

    # 4) Feature FTSE (causali)
    df["Close_prev"] = df["Close"].shift(1)
    df["gap_open"] = df["Open"] / df["Close_prev"] - 1

    df["vol_ma"] = df["Volume"].rolling(20).mean()
    df["vol_std"] = df["Volume"].rolling(20).std()
    df["vol_z"] = (df["Volume"] - df["vol_ma"]) / df["vol_std"]

    df["dow"] = df.index.dayofweek

    return df, meta


# =========================
# STRATEGIA
# =========================
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


# =========================
# SEGNALE LIVE (oggi incluso)
# =========================
def get_next_overnight_signal(df: pd.DataFrame):
    day = today_rome()

    # NOTA: NON richiedo spy_ret/vix_ret non-NaN per tenere la riga di oggi
    df_live = df.dropna(subset=["gap_open", "vol_z", "dow"]).copy()
    if df_live.empty:
        raise RuntimeError("ERRORE: Nessun dato valido dopo dropna(gap_open, vol_z, dow)")

    last_row = df_live.iloc[-1]
    last_date = df_live.index[-1].date()

    if last_date > day:
        raise RuntimeError(f"ERRORE: data più recente ({last_date}) non è chiusa")

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


# =========================
# MAIN
# =========================
def main():
    mailer = EmailClient()

    df, meta = build_dataset()
    ref_date, signal, dbg = get_next_overnight_signal(df)

    status = "LONG" if signal else "FLAT"
    subject = f"FAI QUANT SUPERIOR – Overnight {status}"

    body = f"""
FAI QUANT SUPERIOR – SEGNALE OVERNIGHT (LIVE @ 17:30 Europe/Rome)

Seduta di riferimento (FTSE): {ref_date}
Fonte FTSE oggi: {meta.get("ftse_today_source")}
FTSE close timestamp (Rome): {meta.get("ftse_today_close_ts_rome")}

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
