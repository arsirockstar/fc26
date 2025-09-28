import sqlite3, os, time
DB_PATH = os.environ.get("DB_PATH", "data/app.db")
def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)
def init_db():
    con = connect(); cur=con.cursor()
    cur.executescript("""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS offers (offer_id TEXT PRIMARY KEY, channel_id INTEGER, message_id INTEGER, caption TEXT, created_at INTEGER);
CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, offer_id TEXT, user_id INTEGER, status TEXT, created_at INTEGER, updated_at INTEGER, buy_now INTEGER, bought_for INTEGER, start_price INTEGER, fee_percent REAL, variable_deduction INTEGER, net_amount INTEGER, currency TEXT DEFAULT 'TOMAN');
CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, role TEXT, path TEXT, sha256 TEXT, phash TEXT, ocr_json TEXT, tamper_score REAL DEFAULT 0, created_at INTEGER);
CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, status TEXT, provider_txn_id TEXT, amount INTEGER, created_at INTEGER, verified_by_admin INTEGER, verified_at INTEGER);
""")
    cur.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('order_seq','100000')"); con.commit(); con.close()
def next_order_id():
    con=connect(); cur=con.cursor()
    cur.execute("SELECT v FROM meta WHERE k='order_seq'"); v=int(cur.fetchone()[0]); nv=v+1
    cur.execute("UPDATE meta SET v=? WHERE k='order_seq'", (str(nv),)); con.commit(); con.close()
    return f"ORD-{nv}"
if __name__=='__main__': init_db(); print('DB initialized', DB_PATH)
