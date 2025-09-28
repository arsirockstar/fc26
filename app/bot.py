import os, json, time, uuid
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from app.db import init_db, next_order_id, connect
from app.processing import extract_and_price
from app.invoice import build_invoice_xlsx

load_dotenv()
BOT_TOKEN=os.environ.get('TG_BOT_TOKEN'); FEE_PERCENT=float(os.environ.get('FEE_PERCENT','5'))
ALLOWED=os.environ.get('ALLOWED_CHANNEL_IDS','').split(','); ADMIN_IDS=[int(x) for x in os.environ.get('ADMIN_IDS','').split(',') if x.strip()]
DISPLAY_CURRENCY=os.environ.get('DISPLAY_CURRENCY','TOMAN')

def is_admin(uid): return uid in ADMIN_IDS

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    args=context.args
    if args and args[0].startswith('offer_'): return await start_offer_flow(update, context, args[0].split('offer_',1)[1])
    await update.message.reply_text('سلام! از کانال دکمه سفارش رو بزن یا همینجا عکس کارت رو بفرست. /support /sell')

async def support(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Support: contact channel admins.')

async def start_offer_flow(update:Update, context:ContextTypes.DEFAULT_TYPE, offer_id:str):
    order_id=next_order_id(); uid=update.effective_user.id
    con=connect(); cur=con.cursor(); now=int(time.time())
    cur.execute("INSERT INTO orders(order_id, offer_id, user_id, status, created_at, updated_at, fee_percent, currency) VALUES(?,?,?,?,?,?,?,?)",
                (order_id, offer_id, uid, 'awaiting_photos', now, now, FEE_PERCENT, DISPLAY_CURRENCY)); con.commit(); con.close()
    context.user_data['order_id']=order_id
    await update.message.reply_text(f'سفارش ثبت شد: {order_id}\nعکس کارت رو بفرست.')

async def channel_post(update:Update, context:ContextTypes.DEFAULT_TYPE):
    post=update.channel_post; chat=post.chat
    if (str(chat.id) not in ALLOWED) and (('@'+(chat.username or '')) not in ALLOWED): return
    offer_id=str(uuid.uuid4())
    con=connect(); cur=con.cursor()
    cur.execute("INSERT OR REPLACE INTO offers(offer_id, channel_id, message_id, caption, created_at) VALUES(?,?,?,?,?)",
                (offer_id, chat.id, post.message_id, post.caption or post.text or '', int(time.time()))); con.commit(); con.close()
    deep=f'https://t.me/{context.bot.username}?start=offer_{offer_id}'
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🟢 سفارش / Order', url=deep)]])
    try: await context.bot.edit_message_reply_markup(chat_id=chat.id, message_id=post.message_id, reply_markup=kb)
    except Exception as e: print('edit markup failed:', e)

async def photo_handler(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo: return
    uid=update.effective_user.id; order_id=context.user_data.get('order_id')
    if not order_id:
        order_id=next_order_id(); context.user_data['order_id']=order_id
        con=connect(); cur=con.cursor(); now=int(time.time())
        cur.execute("INSERT INTO orders(order_id, user_id, status, created_at, updated_at, fee_percent, currency) VALUES(?,?,?,?,?,?,?)",
                    (order_id, uid, 'awaiting_photos', now, now, FEE_PERCENT, DISPLAY_CURRENCY)); con.commit(); con.close()
    photo=update.message.photo[-1]; f=await photo.get_file(); b=await f.download_as_bytearray()
    res=extract_and_price(bytes(b), fee_percent=FEE_PERCENT)
    import os
    os.makedirs(f'data/images/{order_id}', exist_ok=True)
    with open(f'data/images/{order_id}/{int(time.time())}.jpg','wb') as w: w.write(b)
    con=connect(); cur=con.cursor()
    cur.execute("INSERT INTO images(order_id, role, path, sha256, phash, ocr_json, tamper_score, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (order_id,'card_front',f'data/images/{order_id}/{int(time.time())}.jpg', res['sha256'], res['phash'], json.dumps(res['ocr']), res['tamper_score'], int(time.time())))
    cur.execute("UPDATE orders SET buy_now=?, bought_for=?, start_price=?, variable_deduction=?, net_amount=?, status=?, updated_at=? WHERE order_id=?",
                (res['buy_now'], res['bought_for'], res['start_price'], res['variable_deduction'], res['net'], 'priced', int(time.time()), order_id)); con.commit(); con.close()
    fee_amt=round((res['buy_now'] or 0)*(FEE_PERCENT/100.0)) if res['buy_now'] else 0
    txt=(f'Order: {order_id}\nBuy Now: {res['buy_now']}\nBought For: {res['bought_for']}\nFee ({FEE_PERCENT}%): -{fee_amt}\nVariable deduction: -{res['variable_deduction']}\nNet: **{res['net']}**\nTamper score: {res['tamper_score']:.2f}\n/confirm برای ادامه')
    await update.message.reply_text(txt, parse_mode='Markdown')

async def confirm(update:Update, context:ContextTypes.DEFAULT_TYPE):
    order_id=context.user_data.get('order_id'); 
    if not order_id: return await update.message.reply_text('سفارشی در جریان نیست.')
    con=connect(); cur=con.cursor(); cur.execute("UPDATE orders SET status=?, updated_at=? WHERE order_id=?", ('awaiting_payment', int(time.time()), order_id)); con.commit(); con.close()
    await update.message.reply_text('تایید شد ✅ لطفاً فیش را ارسال کن.')

async def receipt(update:Update, context:ContextTypes.DEFAULT_TYPE):
    order_id=context.user_data.get('order_id'); 
    if not order_id: return
    con=connect(); cur=con.cursor(); cur.execute("SELECT status FROM orders WHERE order_id=?", (order_id,)); row=cur.fetchone()
    if not row or row[0] != 'awaiting_payment': return
    photo=update.message.photo[-1]; f=await photo.get_file(); b=await f.download_as_bytearray()
    os.makedirs(f'data/images/{order_id}', exist_ok=True)
    path=f'data/images/{order_id}/receipt_{int(time.time())}.jpg'; open(path,'wb').write(b)
    cur.execute("INSERT INTO images(order_id, role, path, created_at) VALUES(?,?,?,?)", (order_id,'receipt',path,int(time.time())))
    cur.execute("INSERT INTO transactions(order_id, status, amount, created_at) VALUES(?,?,?,?)", (order_id,'unknown',0,int(time.time()))); con.commit(); con.close()
    await update.message.reply_text('فیش دریافت شد — وضعیت: زرد/نامشخص.')

async def admin(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text('Admin: /orders /approve <id> /reject <id>')

async def orders_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    con=connect(); cur=con.cursor(); cur.execute("SELECT order_id,status,net_amount,created_at FROM orders ORDER BY created_at DESC LIMIT 20"); rows=cur.fetchall(); con.close()
    if not rows: return await update.message.reply_text('No orders.')
    await update.message.reply_text('\n'.join([f"{r[0]} — {r[1]} — {r[2]}" for r in rows]))

async def approve(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return await update.message.reply_text('Usage: /approve <order_id>')
    oid=context.args[0]; con=connect(); cur=con.cursor()
    cur.execute("UPDATE transactions SET status='paid', verified_by_admin=?, verified_at=? WHERE order_id=?", (update.effective_user.id, int(time.time()), oid))
    cur.execute("UPDATE orders SET status='paid', updated_at=? WHERE order_id=?", (int(time.time()), oid)); con.commit()
    inv={'invoice_id': f'INV-{int(time.time())}','order_id': oid,'user_id': update.effective_user.id,'card_name':'','buy_now':None,'bought_for':None,'fee_percent':FEE_PERCENT,'variable_deduction':None,'net_amount':None,'currency':'TOMAN','created_at': time.strftime('%Y-%m-%d %H:%M:%S'),'payment_status':'paid','provider_txn_id':''}
    cur.execute("SELECT buy_now,bought_for,variable_deduction,net_amount FROM orders WHERE order_id=?", (oid,)); r=cur.fetchone()
    if r: inv['buy_now'],inv['bought_for'],inv['variable_deduction'],inv['net_amount']=r
    path=f'data/invoices/invoice_{oid}.xlsx'; build_invoice_xlsx(path, inv); con.close()
    await update.message.reply_document(document=InputFile(path))
    await update.message.reply_text(f'{oid} approved ✅')

async def reject(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args: return await update.message.reply_text('Usage: /reject <order_id>')
    oid=context.args[0]; con=connect(); cur=con.cursor()
    cur.execute("UPDATE transactions SET status='failed', verified_by_admin=?, verified_at=? WHERE order_id=?", (update.effective_user.id, int(time.time()), oid))
    cur.execute("UPDATE orders SET status='failed', updated_at=? WHERE order_id=?", (int(time.time()), oid)); con.commit(); con.close()
    await update.message.reply_text(f'{oid} rejected ❌')

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & (~filters.UpdateType.EDITED_CHANNEL_POST), channel_post))
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('support', support))
    app.add_handler(CommandHandler('admin', admin))
    app.add_handler(CommandHandler('orders', orders_cmd))
    app.add_handler(CommandHandler('approve', approve))
    app.add_handler(CommandHandler('reject', reject))
    app.add_handler(CommandHandler('confirm', confirm))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, receipt))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, photo_handler))
    print('Bot running with polling (set webhook in separate infra if needed).')
    app.run_polling(drop_pending_updates=True)

if __name__=='__main__': main()
