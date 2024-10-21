# Descrizione del Progetto

Questo progetto è un sistema automatizzato per gestire la configurazione di Pi-hole utilizzando Traefik come reverse proxy. Il programma esegue le seguenti operazioni:

1. **Recupero degli Host**: Recupera gli host configurati per un determinato entrypoint da un'API di Traefik.
2. **Scrittura del File di Configurazione**: Scrive un file di configurazione `99-swarm.conf` con gli host e gli indirizzi IP forniti.
3. **Caricamento del File sul Server Remoto**: Carica il file di configurazione sul server remoto solo se è cambiato rispetto alla versione precedente.
4. **Verifica della Sintassi**: Esegue un controllo della sintassi del file di configurazione utilizzando il comando `pihole-FTL --test`.
5. **Riavvio del Servizio Pi-hole**: Riavvia il servizio `pihole-FTL` se il controllo della sintassi è superato.

## Requisiti

- Python 3.x
- Moduli Python: `paramiko`, `requests`, `python-dotenv`
- Un file `.env` con le seguenti variabili:
  - `TRAEFIK_API_URL`: URL dell'API di Traefik
  - `SWARM_IP_ADDRESSES`: Indirizzi IP del cluster Swarm, separati da virgole
  - `SSH_USER`: Nome utente per la connessione SSH
- Una chiave SSH per l'accesso al server remoto

## Utilizzo

1. **Installazione delle Dipendenze**:
   ```sh
   pip install -r requirements.txt