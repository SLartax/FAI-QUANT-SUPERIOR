# GUIDA DI SETUP - FAI-QUANT-SUPERIOR

## Passo 1: Creare un Bot Telegram (5 minuti)

### 1.1 Aprire Telegram

Se non hai Telegram, scaricalo da:
- **Android/iOS**: App Store o Google Play Store
- **Desktop**: https://desktop.telegram.org
- **Web**: https://web.telegram.org

### 1.2 Contattare BotFather

1. Nel campo ricerca di Telegram, digita: `@BotFather`
2. Clicca sul primo risultato (verificato con una spunta blu)
3. Clicca il tasto **"START"** (se non compare, invia `/start`)
4. BotFather risponderà con un menu di opzioni

### 1.3 Creare un nuovo bot

1. Invia il comando: `/newbot`
2. BotFather chiederà un nome per il bot
   - Esempio: `FAI-QUANT-SUPERIOR Bot`
3. Poi chiederà un username (deve finire con `bot`)
   - Esempio: `fai_quant_superior_bot`
4. BotFather ti manderà il **TOKEN** (una stringa tipo: `123456:ABC...xyz`)

⚠️ **IMPORTANTE**: Salva questo token da qualche parte! Lo userai nel passo 3

---

## Passo 2: Ottenere il Chat ID (3 minuti)

### 2.1 Creare un gruppo privato

1. Su Telegram, clicca l'icona **"Matita"** (in alto a sinistra)
2. Scegli **"Nuovo gruppo"**
3. Seleziona il bot che hai creato (cerca il nome del bot)
4. Dai un nome al gruppo (es: "FAI-QUANT-SUPERIOR Alerts")
5. Clicca **"CREA"**

### 2.2 Inviare un messaggio

1. Nel gruppo appena creato, invia un messaggio qualsiasi (es: "test")

### 2.3 Ottenere il Chat ID

1. Apri una nuova scheda del browser
2. Incolla questo URL:
   ```
   https://api.telegram.org/botTUO_TOKEN/getUpdates
   ```
   Sostituisci `TUO_TOKEN` con il token che hai copiato nel Passo 1
   
   Esempio reale:
   ```
   https://api.telegram.org/bot123456:ABCxyz/getUpdates
   ```

3. Premi **INVIO**
4. Vedrai un testo JSON lungo
5. Cerca la parola `"chat"` e guarda il numero dopo di essa
6. Se è un gruppo, il numero sarà **negativo** (es: `-123456789`)

⚠️ **IMPORTANTE**: Salva questo Chat ID! Lo userai nel Passo 3

Esempio di risposta:
```json
{
  "ok": true,
  "result": [
    {
      "update_id": 123456789,
      "message": {
        "message_id": 1,
        "date": 1671717600,
        "chat": {
          "id": -123456789,
          "title": "FAI-QUANT-SUPERIOR Alerts"
        }
      }
    }
  ]
}
```

In questo esempio, il Chat ID è: `-123456789`

---

## Passo 3: Configurare i Secrets su GitHub (3 minuti)

### 3.1 Accedere a GitHub

1. Vai su: https://github.com
2. Se non sei loggato, fai login con il tuo account

### 3.2 Aprire le impostazioni dei secrets

1. Vai a questo URL:
   ```
   https://github.com/SLartax/FAI-QUANT-SUPERIOR/settings/secrets/actions
   ```
   Oppure:
   - Clicca su **"Settings"** nella pagina del repository
   - Nel menu a sinistra, vai a **"Secrets and variables"** → **"Actions"**

### 3.3 Aggiungere il primo secret (BOT TOKEN)

1. Clicca il pulsante verde **"New repository secret"**
2. Nel campo **"Name"**, scrivi esattamente:
   ```
   TELEGRAM_BOT_TOKEN
   ```
   (maiuscole, senza spazi)

3. Nel campo **"Value"**, incolla il TOKEN che hai copiato nel Passo 1
   Esempio:
   ```
   123456:ABCxyzdef...
   ```

4. Clicca **"Add secret"**

### 3.4 Aggiungere il secondo secret (CHAT ID)

1. Clicca di nuovo il pulsante verde **"New repository secret"**
2. Nel campo **"Name"**, scrivi esattamente:
   ```
   TELEGRAM_CHAT_ID
   ```
   (maiuscole, senza spazi)

3. Nel campo **"Value"**, incolla il CHAT ID che hai copiato nel Passo 2
   Esempio:
   ```
   -123456789
   ```
   Includi il **meno** se è un gruppo!

4. Clicca **"Add secret"**

✅ **Fatto!** I secrets sono ora configurati su GitHub.

---

## Passo 4: Testare il Sistema (2 minuti)

### 4.1 Eseguire il workflow manualmente

1. Vai a: https://github.com/SLartax/FAI-QUANT-SUPERIOR/actions
2. Nel menu a sinistra, clicca il workflow **"FAI-QUANT-SUPERIOR Trading System"**
3. Clicca il pulsante **"Run workflow"** (bianco)
4. Seleziona il branch **"main"** e clicca **"Run workflow"**

### 4.2 Monitorare l'esecuzione

1. Aspetta che il workflow finisca (1-2 minuti)
2. Vedrai un indicatore verde ✅ se è riuscito, rosso ❌ se ha errori
3. Se vedi errori, clicca sull'esecuzione per leggere i log

### 4.3 Verificare il messaggio Telegram

1. Apri il gruppo Telegram che hai creato nel Passo 2
2. Se tutto funziona, vedrai un messaggio come:

```
FAI-QUANT-SUPERIOR
Ora: 2025-12-22T20:00:00+01:00
Raccomandazione: BUY
...
```

✅ **Successo!** Il sistema è operativo.

---

## Passo 5: Automatizzazione (Non serve far nulla)

Da ora in poi, il sistema si eseguirà **automaticamente** ogni giorno feriale alle 19:00 CET senza che tu faccia nulla.

Non è necessario avere il PC acceso.
Non è necessario avere Telegram aperto.

I messaggi arriveranno al gruppo che hai creato nel Passo 2.

---

## 🚠 Risoluzione Problemi

### Problema: "Unauthorized" o errore 401 nel workflow

**Causa**: Il TOKEN BOT è scorretto o il valore del secret non è esatto.

**Soluzione**:
1. Copia di nuovo il TOKEN direttamente da BotFather
2. Vai a GitHub → Settings → Secrets
3. Clicca il secret `TELEGRAM_BOT_TOKEN`
4. Clicca **"Update secret"**
5. Cancella il valore e incolla il nuovo TOKEN
6. Salva e riprova il test

### Problema: Bot non invia il messaggio

**Causa**: Il CHAT ID è scorretto o il bot non è nel gruppo.

**Soluzione**:
1. Verifica che il bot sia stato aggiunto al gruppo (deve comparire tra i membri)
2. Ripeti il Passo 2 per ottenere il Chat ID corretto
3. Controlla che il numero sia **negativo** se è un gruppo
4. Aggiorna il secret `TELEGRAM_CHAT_ID` su GitHub
5. Riprova il test

### Problema: Workflow non esiste / non compare in Actions

**Causa**: Il file `.github/workflows/trading-overnight.yml` non è caricato correttamente.

**Soluzione**:
1. Vai a: https://github.com/SLartax/FAI-QUANT-SUPERIOR/tree/main/.github/workflows
2. Verifica che esista il file `trading-overnight.yml`
3. Se manca, crealo manualmente seguendo il README

---

## ✅ Checklist Finale

- [ ] Ho creato un bot con BotFather
- [ ] Ho copiato il TOKEN BOT
- [ ] Ho aggiunto il bot a un gruppo privato
- [ ] Ho ottenuto il CHAT ID
- [ ] Ho aggiunto i due secrets su GitHub
- [ ] Ho testato il workflow manualmente
- [ ] Ho ricevuto un messaggio su Telegram

🎉 **Se tutti i checkbox sono spuntati, il sistema è OPERATIVO!**
