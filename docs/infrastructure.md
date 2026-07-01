# Ward Protocol — Infrastructure

## Production Stack

| Component | Details |
|-----------|---------|
| **Site** | Netlify — static deploy, wardprotocol.org |
| **API** | Railway — sdk/python FastAPI, api.wardprotocol.org |
| **Runtime** | Python 3.12, FastAPI + Uvicorn |
| **XRPL** | Altnet (testnet) / Mainnet via xrpl-py |
| **State** | XRPL ledger is authoritative — no Ward database |
| **DNS** | CNAME → Netlify for site, Railway for API |

## Key Principle

Ward has no authoritative state outside the XRPL ledger. There is no Ward database, no Ward custody, no Ward signing keys in production. The API constructs unsigned transactions and returns them. Institutions sign and submit with their own wallets.

## API Deployment (Railway)

```bash
# railway.toml
[deploy]
startCommand = "cd sdk/python && uvicorn main:app --host 0.0.0.0 --port $PORT"
```

## Site Deployment (Netlify)

Static HTML deploy from repo root. Redirects configured in `netlify.toml`.

Routes: `/flow`, `/topology`, `/xrpl`, `/api`, `/calendar`, `/tweets`

## API Health

```bash
curl https://api.wardprotocol.org/health
```

## Monitoring

```bash
# Unit tests — no network required
pytest test_ward.py -v -m "not integration"  # 296/296 pass

# Full testnet simulation — XRPL Altnet required
python testnet_sim.py
```

See `security_notes.md` for 15 attack vectors and mitigations.
