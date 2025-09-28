import io, re
from PIL import Image
import imagehash, pytesseract, hashlib

def sha256_bytes(b: bytes)->str:
    h=hashlib.sha256(); h.update(b); return h.hexdigest()

def compute_hashes(img_bytes: bytes):
    im=Image.open(io.BytesIO(img_bytes)).convert('RGB')
    return sha256_bytes(img_bytes), str(imagehash.phash(im))

def ocr_extract(img_bytes: bytes)->dict:
    im=Image.open(io.BytesIO(img_bytes)).convert('RGB')
    txt=pytesseract.image_to_string(im, lang='eng')
    import re
    def find(label):
        m=re.search(label+r'.{0,12}?(\d[\d,\.]*)', txt, flags=re.I)
        if not m: return None
        return int(re.sub(r'[^\d]','', m.group(1)))
    return {
        'raw_text': txt,
        'bought_for': find(r'Bought\s*For') or find(r'won.*for'),
        'buy_now': find(r'Buy\s*Now\s*Price') or find(r'BIN') or find(r'Buy\s*Now'),
        'start_price': find(r'Start\s*Price')
    }

def tamper_heuristic(img_bytes: bytes)->float:
    return 0.3

def extract_and_price(img_bytes: bytes, fee_percent: float = 5.0, variable_deduction: int = None):
    sha, ph = compute_hashes(img_bytes)
    ocr = ocr_extract(img_bytes)
    tf = tamper_heuristic(img_bytes)
    buy_now = int(str(ocr.get('buy_now')).replace(',','')) if ocr.get('buy_now') else None
    bought_for = int(str(ocr.get('bought_for')).replace(',','')) if ocr.get('bought_for') else None
    if variable_deduction is None:
        variable_deduction = bought_for or 0
    net = None
    if buy_now is not None:
        fee_amount = round(buy_now * (fee_percent/100.0))
        net = round(buy_now - fee_amount - (variable_deduction or 0))
    return {'sha256': sha,'phash': ph,'ocr': ocr,'tamper_score': tf,'buy_now': buy_now,'bought_for': bought_for,'start_price': ocr.get('start_price'),'fee_percent': fee_percent,'variable_deduction': variable_deduction,'net': net}
