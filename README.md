# FAI-QUANT-SUPERIOR

## Sistema di Trading Algoritmico Overnight su FIB (FTSE MIB Futures)

**Status**: ✅ Operativo con GitHub Actions  
**Notifiche**: 📧 Email (Gmail SMTP)  
**Esecuzione**: Automatica ogni giorno feriale alle 19:00 CET via GitHub Actions  


---

## 🎯 Caratteristiche

- ✅ **Analisi automatica del FTSE MIB (FIB1!)**
- ✅ **Notifiche via Email (Gmail SMTP + App Password)**
- ✅ **Validazione secrets con fallback intelligente**
- ✅ **Logging comprensivo con timezone Europe/Rome**
- ✅ **Esecuzione schedulata: feriali ore 19:00 CET**
- ✅ **Esecuzione manuale via workflow_dispatch**
- ✅ **Robustezza rete: timeout e retry**
- ✅ **Headless: nessun input interattivo richiesto**

---

## 🚀 Setup Iniziale (IMPORTANTE!)

### 1. Generare Gmail App Password

1. Vai a https://myaccount.google.com/apppasswords
2. Seleziona **Mail** e **Windows (o altro device)**
3. Google genererà una password di 16 caratteri (esempio: `abcd efgh ijkl mnop`)
4. **Copia questa password** (la userai come SMTP_PASS)

> **Nota**: Non usare la tua password Gmail normale! Le App Password funzionano solo se hai l'autenticazione a 2 fattori abilitata.

### 2. Configurare GitHub Secrets

Vai a: **Settings → Secrets and variables → Actions**

Aggiungi i seguenti secrets:

| Secret | Valore | Obbligatorio | Esempio |
|--------|--------|--------------|----------|
| `SMTP_HOST` | smtp.gmail.com | ✅ Si | `smtp.gmail.com` |
| `SMTP_PORT` | 587 (default TLS) | ❌ No | `587` |
| `SMTP_USER` | Tuo indirizzo Gmail | ✅ Si | `tuoemail@gmail.com` |
| `SMTP_PASS` | Gmail App Password | ✅ Si | `abcd efgh ijkl mnop` |
| `EMAIL_TO` | Destinatario email | ❌ No | `pioggiamarrone@gmail.com` |
| `EMAIL_FROM_NAME` | Nome del mittente | ❌ No | `FAI-QUANT-SUPERIOR` |

**Secrets Obbligatori**: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`  
Senza questi, il workflow fallirà con messaggio d'errore esplicito.

---

## 📋 File Principali

```
.
├── trading_system.py          # Sistema di trading principale (SMTP email integration)
├── requirements.txt           # Dipendenze Python (pandas, requests, pytz, yfinance)
├── .github/workflows/
│   └── trading-overnight.yml  # GitHub Actions workflow
├── README.md                  # Questo file
└── SETUP.md                   # Guida dettagliata setup
```

---

## ⏰ Schedule di Esecuzione

**Automatico**: Ogni giorno feriale (lunedì-venerdì) alle **19:00 CET (18:00 UTC)**

Cron expression: `0 18 * * 1-5`

```
19:00 CET = 18:00 UTC
```

Verifica esecuzioni su GitHub: [Actions](https://github.com/SLartax/FAI-QUANT-SUPERIOR/actions)

---

## 🔍 Verificare che Funziona

### Test Manuale (Consigliato)

1. Vai a: **Actions → FAI-QUANT-SUPERIOR Trading System (Email Only)**
2. Clicca **"Run workflow"** → **"Run workflow"**
3. Aspetta qualche secondo
4. Controlla i log e verifica l'email ricevuta

### Controllare i Log

Nel run del workflow, accedi ai log e verifica:

- ✅ `Secrets validated. Email will be sent to: ...`
- ✅ `Fetching FTSE MIB market data...`
- ✅ `BUY/SELL/FLAT signal generated`
- ✅ `Email sent successfully to ...`

Se vedi **`FATAL: Missing required secrets`**, significa che uno o più secrets non sono stati impostati correttamente.

---

## 📧 Contenuto Email

Ogni email conterrà:

- **Soggetto**: `FAI-QUANT-SUPERIOR — BUY/SELL/FLAT — 2025-12-22 19:00 Europe/Rome`
- **Corpo**:
  - Strumento: FTSE MIB (FIB1!)
  - Data/Ora Europe/Rome
  - **Segnale**: BUY | SELL | FLAT
  - Prezzo di riferimento
  - Regola del segnale (motivazione)
  - Link al GitHub Actions run

**Nota**: Le email vengono inviate SOLO per segnali BUY/SELL. I segnali FLAT non generano email (configurable in `trading_system.py` line ~280).

---

## 🔧 Customizzazione

### Modificare l'Orario di Esecuzione

Modifica `.github/workflows/trading-overnight.yml` linea 8:

```yaml
- cron: '0 19 * * 1-5'  # 19:00 UTC (cambiar il primo valore)
```

**Convertitore CET ↔ UTC**: CET = UTC + 1 (o UTC + 2 in ora legale)

Esempi:
- `19:00 CET` = `18:00 UTC` → cron: `0 18 * * 1-5`
- `21:00 CET` = `20:00 UTC` → cron: `0 20 * * 1-5`

### Aggiungere Nuovi Strumenti

Modifica `trading_system.py` metodo `calculate_signals()`:

```python
def calculate_signals(self, market_data):
    # ... codice esistente ...
    
    # Aggiungi nuova logica per altri strumenti
    if self.some_condition():
        signals['signal'] = 'BUY'
        signals['reason'] = 'Tua regola qui'
```

### Modificare Logica Email

In `trading_system.py` linea ~280, modifica la condizione:

```python
# ATTUALE: Invia solo BUY/SELL
if signal['signal'] in ['BUY', 'SELL']:
    self.send_email(signal)

# ALTERNATIVA: Invia sempre (anche FLAT)
if signal:  # Rimuovi la condizione
    self.send_email(signal)
```

---

## ⚠️ Troubleshooting

### "FATAL: Missing required secrets"

**Causa**: Uno o più secrets non sono configurati.  
**Soluzione**:
1. Vai a Settings → Secrets
2. Verifica che `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` siano presenti
3. Non lasciare campi vuoti

### "SMTP Authentication failed"

**Causa**: Username o password SMTP errati.  
**Soluzione**:
1. Verifica che `SMTP_USER` sia il tuo indirizzo Gmail completo (es: `nome@gmail.com`)
2. Verifica che `SMTP_PASS` sia l'**App Password**, non la password Gmail normale
3. Assicurati di avere l'autenticazione 2FA abilitata su Gmail

### "Timeout fetching market data (10s)"

**Causa**: Yahoo Finance non risponde entro 10 secondi.  
**Soluzione**:
- Il sistema ritornerà FLAT signal
- Verifica la connessione internet
- Riprova manualmente (Actions → Run workflow)

### "Workflow not running on schedule"

**Causa**: GitHub Actions potrebbe non eseguire il workflow se il repository è inattivo.  
**Soluzione**:
1. Fai un push di una modifica al repository
2. Il workflow dovrebbe riprendere a girare
3. Nel frattempo, puoi testare manualmente con workflow_dispatch

---

## 📊 Segnali di Esempio

### Email ricevuta con BUY

```
Soggetto: FAI-QUANT-SUPERIOR — BUY — 2025-12-22 19:45 Europe/Rome

Strumento: FTSE MIB (FIB1!)
Data/Ora (Europe/Rome): 2025-12-22 19:45:30
Segnale: BUY
Prezzo di riferimento: 34567.89
Ultima candela disponibile: 2025-12-22 19:45
Regola del segnale: Market hours 19:00-21:00 CET - BUY signal triggered
Run GitHub Actions: [Link]
Risk Level: medium
```

---

## 📚 Documentazione

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [Python SMTP Library](https://docs.python.org/3/library/smtplib.html)
- [Pytz Timezone Documentation](https://pypi.org/project/pytz/)
- [YFinance Documentation](https://github.com/ranaroussi/yfinance)

---

## 📝 Disclaimer

Questo sistema di trading **non fornisce garanzie di profitto**. Usa il sistema a **tuo rischio**. Non fornisce consigli finanziari.

---

## 👨‍💼 Autore

[SLartax](https://github.com/SLartax) - Studio Legale Artax
