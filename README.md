# FAI-QUANT-SUPERIOR

## Sistema di Trading Algoritmico Overnight su FIB (FTSE MIB Futures)

**Status**: Operativo con GitHub Actions ✅
**Esecuzione**: Automatica ogni giorno feriale alle 19:00 CET  
**Segnali**: Inviati a Telegram anche con PC spento

---

## 🎯 Caratteristiche

- ✅ Analisi automatica del FTSE MIB (FIB1!)
- ✅ Calcolo segnali di trading basati su volatilità e trend
- ✅ Invio notifiche a Telegram in tempo reale
- ✅ Esecuzione notturna senza PC acceso (GitHub Actions)
- ✅ Gestione risk/reward personalizzato
- ✅ Log completo di ogni ciclo di trading

---

## 🚀 Setup Iniziale (IMPORTANTE!)

### 1. Creare un Bot Telegram

1. Apri Telegram e cerca **@BotFather**
2. Invia il comando `/start`
3. Invia `/newbot`
4. Dagli un nome (es: "FAI-QUANT-SUPERIOR Bot")
5. Scegli un username (es: "fai_quant_superior_bot")
6. Copia il **TOKEN BOT** (es: `123456:ABC...`)

### 2. Ottenere il Chat ID

1. Crea un gruppo privato e aggiungi il bot
2. Invia un messaggio nel gruppo
3. Apri nel browser: `https://api.telegram.org/botTUO_TOKEN/getUpdates`
4. Sostituisci `TUO_TOKEN` con il token del bot
5. Cerca il `chat` (es: `-123456789`)
6. Copia il **CHAT ID**

### 3. Configurare i Secrets su GitHub

1. Vai su: https://github.com/SLartax/FAI-QUANT-SUPERIOR/settings/secrets/actions
2. Clicca **"New repository secret"**
3. Crea due secrets:

   **Secret 1**:
   - Name: `TELEGRAM_BOT_TOKEN`
   - Value: (il token copiato da BotFather)
   
   **Secret 2**:
   - Name: `TELEGRAM_CHAT_ID`
   - Value: (il chat ID ottenuto dal link getUpdates)

4. Clicca **"Add secret"**

---

## 📋 File Principali

```
├── trading_system.py           # Motore principale del trading
├── requirements.txt            # Dipendenze Python
├── .github/workflows/
│   └── trading-overnight.yml   # Automazione GitHub Actions
└── README.md                   # Questo file
```

---

## ⏰ Schedule di Esecuzione

Il workflow si esegue **automaticamente**:
- **Giorni**: Lunedì - Venerdì
- **Ora**: 19:00 CET (18:00 UTC)
- **Azione**: Scarica dati, calcola segnali, invia a Telegram

Puoi anche eseguire manualmente:
1. Vai su: https://github.com/SLartax/FAI-QUANT-SUPERIOR/actions
2. Seleziona **"FAI-QUANT-SUPERIOR Trading System"**
3. Clicca **"Run workflow"**

---

## 🔍 Verificare che Funziona

### Test Manual (Consigliato)

1. Vai a: https://github.com/SLartax/FAI-QUANT-SUPERIOR/actions
2. Seleziona il workflow **"FAI-QUANT-SUPERIOR Trading System"**
3. Clicca il bottone verde **"Run workflow"**
4. Aspetta 1-2 minuti
5. Controlla il gruppo Telegram per il messaggio di segnale

### Controllare i Log

1. Vai a **Actions** → **FAI-QUANT-SUPERIOR Trading System**
2. Clicca sull'ultima esecuzione
3. Espandi il job **"trading"**
4. Leggi i log per diagnosticare problemi

---

## 📊 Segnali di Esempio

Quando il sistema rileva un setup, invia a Telegram:

```
🎯 FAI-QUANT-SUPERIOR

Ora: 2025-12-22T19:00:00+01:00
Raccomandazione: BUY
Livello di rischio: medium

Strumenti:
FIB1!
• Azione: BUY
• Entrata: Market
• Stop Loss: -100
• Take Profit: +150

⚠️ Questo è un segnale algoritmico. Non è consulenza finanziaria.
```

---

## 🔧 Customizzazione

### Modificare l'Orario di Esecuzione

Edita `.github/workflows/trading-overnight.yml`:

```yaml
on:
  schedule:
    # Formato cron: minute hour day-of-month month day-of-week
    - cron: '0 18 * * 1-5'  # Cambia questo
```

Esempi:
- `'0 19 * * *'` = Ogni giorno alle 19:00 CET
- `'0 16 * * 1-5'` = Lunedì-Venerdì alle 16:00
- `'30 19 * * 5'` = Venerdì alle 19:30

### Aggiungere Nuovi Strumenti

Edita `trading_system.py` nella funzione `calculate_signals()`:

```python
signals['instruments'].append({
    'symbol': 'EUR/USD',  # Aggiungi nuovo
    'action': 'SELL',
    'entry': 'Limit 1.0850',
    'stop_loss': '+50 pips',
    'take_profit': '-150 pips'
})
```

---

## ⚠️ Troubleshooting

### "No secrets found"

**Problema**: Il workflow fallisce dicendo che mancano i secrets

**Soluzione**:
1. Verifica di aver aggiunto i secrets in Settings → Secrets and variables
2. Controlla che i nomi siano ESATTAMENTE:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. I nomi sono case-sensitive!

### "Failed to send message to Telegram"

**Problema**: Il messaggio non arriva su Telegram

**Soluzione**:
1. Verifica che il bot sia aggiunto al gruppo/chat
2. Controlla che il CHAT ID sia corretto (negativo per gruppi)
3. Verifica che il BOT TOKEN sia corretto

### "Workflow not running on schedule"

**Problema**: Il workflow non parte all'orario stabilito

**Soluzione**:
1. GitHub Actions ha un delay di pochi minuti
2. L'orario è in **UTC**, non in ora locale
3. Prova il test manuale per verificare che il codice funziona

---

## 📚 Documentazione

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Python Async Programming](https://docs.python.org/3/library/asyncio.html)

---

## 📝 Disclaimer

Questo è un sistema algoritmico di trading sperimentale. Non è consulenza finanziaria. Il trading comporta rischi significativi. Non investire denaro che non puoi permetterti di perdere.

---

## 👨‍💼 Autore

**Studio Legale Artax** - Sistema di Trading Quantitativo  
Torino, Italia
