# FC26 Bot + Cloudflare Worker Option A (Backend /ingest)
- Telegram bot (polling by default)
- FastAPI backend (/ingest) to receive photo events from Cloudflare Worker
- OCR, duplicate hashing, Excel invoice, admin flows

## Setup
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app/db.py
```

## Run
Terminal 1 (bot):
```
python app/bot.py
```

Terminal 2 (backend):
```
uvicorn app.backend:app --host 0.0.0.0 --port 8090
```

Point your Cloudflare Worker secret BACKEND_URL to your backend domain that proxies /ingest to this service.
