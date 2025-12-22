# GUIDA DI SETUP - FAI-QUANT-SUPERIOR

**Tempo stimato: 15 minuti**

Questa guida spiega come configurare completamente il sistema di trading con email notifications.

---

## Passo 1: Abilitare Autenticazione 2FA su Gmail (5 minuti)

Le **Gmail App Passwords** richiedono l'autenticazione a due fattori.

### 1.1 Vai al tuo Account Google

1. Accedi a: https://myaccount.google.com
2. Clicca su **"Sicurezza"** (a sinistra)
3. Cerca **"Verifica in due passaggi"**
4. Se non è ancora abilitata:
   - Clicca **"Attiva"**
   - Segui le istruzioni (riceverai un codice SMS)
   - Completa la verifica

### 1.2 Verifica il Completamento

Dovresti vedere:
```
Verifica in due passaggi
✓ Attiva
```

---

## Passo 2: Generare Gmail App Password (3 minuti)

### 2.1 Accedi al Pannello App Password

1. Vai a: https://myaccount.google.com/apppasswords
2. Se ti chiede di accedere di nuovo, fallo
3. Seleziona:
   - **App**: Mail (o Email)
   - **Dispositivo**: Windows (non importa quale)
4. Clicca **"Genera"**

### 2.2 Copia la Password

Google genererà una password di 16 caratteri simile a:
```
abcd efgh ijkl mnop
```

**COPIA QUESTA PASSWORD** - la userai come `SMTP_PASS` in GitHub Secrets.

> ⚠️ **IMPORTANTE**: Questa password è diversa dalla tua password Gmail normale. Non condividerla!

---

## Passo 3: Configurare GitHub Secrets (5 minuti)

### 3.1 Vai a Settings del Repository

1. Vai al repository: https://github.com/SLartax/FAI-QUANT-SUPERIOR
2. Clicca **"Settings"** (menu top)
3. A sinistra, clicca **"Secrets and variables"** → **"Actions"**

### 3.2 Crea i Secrets

Clicca **"New repository secret"** e aggiungi questi secrets uno per uno:

#### Secret 1: SMTP_HOST
- **Name**: `SMTP_HOST`
- **Value**: `smtp.gmail.com`
- Clicca **"Add secret"**

#### Secret 2: SMTP_PORT
- **Name**: `SMTP_PORT`
- **Value**: `587`
- Clicca **"Add secret"**

#### Secret 3: SMTP_USER
- **Name**: `SMTP_USER`
- **Value**: Il tuo indirizzo Gmail (es: `tuoemail@gmail.com`)
- Clicca **"Add secret"**

#### Secret 4: SMTP_PASS (OBBLIGATORIO!)
- **Name**: `SMTP_PASS`
- **Value**: La App Password che hai copiato (es: `abcd efgh ijkl mnop`)
- Clicca **"Add secret"**

#### Secret 5: EMAIL_TO (opzionale)
- **Name**: `EMAIL_TO`
- **Value**: `pioggiamarrone@gmail.com` (o altra email destinataria)
- Clicca **"Add secret"**

#### Secret 6: EMAIL_FROM_NAME (opzionale)
- **Name**: `EMAIL_FROM_NAME`
- **Value**: `FAI-QUANT-SUPERIOR`
- Clicca **"Add secret"**

### 3.3 Verifica i Secrets

Dovrebbe apparire una lista simile a:
```
✓ SMTP_HOST
✓ SMTP_PORT
✓ SMTP_USER
✓ SMTP_PASS
✓ EMAIL_TO
✓ EMAIL_FROM_NAME
```

**Secrets obbligatori**: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`

Senza questi, il workflow fallirà immediatamente.

---

## Passo 4: Testare il Sistema (2 minuti)

### 4.1 Vai alla Pagina Actions

1. Nel repository, clicca **"Actions"** (menu top)
2. A sinistra, seleziona **"FAI-QUANT-SUPERIOR Trading System (Email Only)"**

### 4.2 Esegui il Workflow Manualmente

1. Clicca il pulsante **"Run workflow"** (a destra)
2. Seleziona il branch: **"main"**
3. Clicca **"Run workflow"** (verde)

### 4.3 Attendi l'Esecuzione

Il workflow deve:
1. Partire (cambierà da `queued` a `in progress`)
2. Eseguire in ~30-60 secondi
3. Terminare con status **verde** (✅ success) o **rosso** (❌ failure)

### 4.4 Controlla i Log

Clicca sul run per vedere i log:

```
✓ Checkout code
✓ Set up Python
✓ Check required secrets
✓ Install dependencies
✓ Verify Python environment
✓ Run trading system
✓ Log execution summary
```

Nei log, cerca questi messaggi positivi:

```
Secrets validated. Email will be sent to: pioggiamarrone@gmail.com
Fetching FTSE MIB market data...
Market data fetched successfully
BUY signal generated (o FLAT signal)
Connecting to SMTP: smtp.gmail.com:587
TLS connection established
Authenticated as tuoemail@gmail.com
Email sent successfully to pioggiamarrone@gmail.com
```

### 4.5 Verifica l'Email

Controlla la inbox di **pioggiamarrone@gmail.com** (o l'email che hai configurato).

Dovrebbe arrivare un'email con:
- **Mittente**: `FAI-QUANT-SUPERIOR <tuoemail@gmail.com>`
- **Soggetto**: `FAI-QUANT-SUPERIOR — BUY/SELL/FLAT — 2025-12-22 19:00 Europe/Rome`
- **Corpo**: Dettagli del segnale, prezzo, link a GitHub Actions

---

## Troubleshooting: Errori Comuni

### Errore: "FATAL: Missing required secrets"

**Cosa significa**: Uno o più secrets non sono configurati.

**Soluzione**:
1. Vai a Settings → Secrets
2. Verifica che questi secrets esistano:
   - `SMTP_HOST` = `smtp.gmail.com`
   - `SMTP_USER` = il tuo email
   - `SMTP_PASS` = la App Password
3. Se manca uno, crealo
4. Riprova manualmente

### Errore: "SMTP Authentication failed"

**Cosa significa**: Le credenziali SMTP sono sbagliate.

**Soluzione**:
1. Verifica che `SMTP_USER` sia il tuo Gmail completo (es: `nome@gmail.com`)
2. Verifica che `SMTP_PASS` sia l'**App Password**, non la password Gmail normale
3. Se hai sbagliato, elimina il secret e ricrealo
4. Controlla che l'autenticazione 2FA sia attiva su Gmail

### Errore: "Timeout fetching market data"

**Cosa significa**: Yahoo Finance non ha risposto in 10 secondi.

**Soluzione**:
- Il sistema ritornerà FLAT signal automaticamente
- Questo è temporaneo (problema di connessione)
- Riprova manualmente tra qualche minuto

### Email non ricevuta

**Cosa fare**:
1. Controlla che il workflow sia passato (status verde)
2. Leggi i log per verificare "Email sent successfully"
3. Controlla la spam folder
4. Verifica che `EMAIL_TO` sia l'indirizzo corretto

---

## Configurazione Avanzata

### Cambiar e l'Orario di Esecuzione

Modifica `.github/workflows/trading-overnight.yml` linea ~7:

```yaml
schedule:
  - cron: '0 18 * * 1-5'  # Modifica questo valore
```

Esempi di cron:
- `0 18 * * 1-5` = 18:00 UTC (19:00 CET)
- `0 20 * * 1-5` = 20:00 UTC (21:00 CET)
- `30 17 * * 1-5` = 17:30 UTC (18:30 CET)

### Modificare il Destinatario Email

Modifica il secret `EMAIL_TO` in GitHub Secrets.

### Inviare Email anche per Segnali FLAT

Modifica `trading_system.py` linea ~280:

```python
# PRIMA (invia solo BUY/SELL):
if signal['signal'] in ['BUY', 'SELL']:
    self.send_email(signal)

# DOPO (invia sempre):
if signal:
    self.send_email(signal)
```

Fai commit e il prossimo run userà la nuova logica.

---

## Verifica Finale Checklist

- [ ] Gmail 2FA abilitato
- [ ] Gmail App Password generato
- [ ] `SMTP_HOST` secret creato = `smtp.gmail.com`
- [ ] `SMTP_USER` secret creato = il tuo Gmail
- [ ] `SMTP_PASS` secret creato = App Password
- [ ] Test manuale eseguito (Run workflow)
- [ ] Log mostra "Email sent successfully"
- [ ] Email ricevuta in inbox
- [ ] Workflow aggiunto al calendario (ogni feriale 19:00 CET)

---

## Link Utili

- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [GitHub Actions Workflows](https://docs.github.com/en/actions/learn-github-actions)
- [Python SMTP Documentation](https://docs.python.org/3/library/smtplib.html)

---

**Supporto**: Se hai problemi, controlla i log e verifica il Troubleshooting.
