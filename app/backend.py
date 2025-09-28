import os, io, time, json, requests
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel
from app.processing import extract_and_price
from app.db import connect, next_order_id

BOT_TOKEN=os.environ.get('TG_BOT_TOKEN')
API_URL=f'https://api.telegram.org/bot{BOT_TOKEN}'

app = FastAPI(title='FC26 Backend Ingest')

class IngestPayload(BaseModel):
    chat_id:int; message_id:int; user_id:int
    file_id: Optional[str]=None; file_url: Optional[str]=None
    caption: Optional[str]=None; ts: Optional[int]=None

def tg_send_message(chat_id:int, text:str):
    try: requests.post(f'{API_URL}/sendMessage', json={'chat_id':chat_id,'text':text})
    except Exception as e: print('sendMessage error:', e)

def tg_get_file_url(file_id:str)->Optional[str]:
    try:
        r=requests.get(f'{API_URL}/getFile', params={'file_id':file_id}, timeout=10); r.raise_for_status()
        fp=r.json().get('result',{}).get('file_path'); 
        return f'https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}' if fp else None
    except Exception as e: print('getFile error:', e); return None

def download_bytes(url:str)->Optional[bytes]:
    try: 
        r=requests.get(url, timeout=20); r.raise_for_status(); return r.content
    except Exception as e: print('download error:', e); return None

@app.post('/ingest')
async def ingest(p:IngestPayload):
    url=p.file_url or (tg_get_file_url(p.file_id) if p.file_id else None)
    if not url: tg_send_message(p.chat_id,'❌ فایل دریافت نشد. دوباره ارسال کن.'); return {'ok':False}
    data=download_bytes(url)
    if not data: tg_send_message(p.chat_id,'❌ دانلود ناموفق بود.'); return {'ok':False}
    res=extract_and_price(data)
    order_id=next_order_id()
    os.makedirs(f'data/images/{order_id}', exist_ok=True)
    with open(f'data/images/{order_id}/ingest_{int(time.time())}.jpg','wb') as w: w.write(data)
    con=connect(); cur=con.cursor()
    cur.execute("INSERT INTO images(order_id, role, path, sha256, phash, ocr_json, tamper_score, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (order_id,'card_front',f'data/images/{order_id}/ingest_{int(time.time())}.jpg', res['sha256'], res['phash'], json.dumps(res['ocr']), res['tamper_score'], int(time.time())))
    cur.execute("INSERT INTO orders(order_id, user_id, status, created_at, updated_at, buy_now, bought_for, start_price, variable_deduction, net_amount, fee_percent) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (order_id, p.user_id, 'priced', int(time.time()), int(time.time()), res.get('buy_now'), res.get('bought_for'), res.get('start_price'), res.get('variable_deduction'), res.get('net'), res.get('fee_percent')))
    con.commit(); con.close()
    fee_amt=round((res.get('buy_now') or 0)*((res.get('fee_percent') or 0)/100.0)) if res.get('buy_now') else 0
    msg=(f'Order: {order_id}\nBuy Now: {res.get('buy_now')}\nBought For: {res.get('bought_for')}\nFee ({res.get('fee_percent')}%): -{fee_amt}\nVariable deduction: -{res.get('variable_deduction')}\nNet: **{res.get('net')}**\nTamper score: {res['tamper_score']:.2f}\n/confirm برای ادامه')
    tg_send_message(p.chat_id, msg)
    return {'ok':True, 'order_id':order_id, 'net':res.get('net')}
