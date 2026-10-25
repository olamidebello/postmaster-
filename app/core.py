"""Postmaster storage, validation, accounting and security primitives."""
import base64, csv, hashlib, hmac, io, json, os, re, secrets, sqlite3, struct, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT=Path(__file__).parent
DATA=Path(os.environ.get('POSTMASTER_DATA','./data')).resolve()
PLANS={'free':{'users':1,'checks':False},'premium':{'users':25,'checks':True},'enterprise':{'users':50,'checks':True}}
SERVICES={'standard':85,'first_class':120,'certified':575,'certified_return_receipt':825,'priority':1200,'express':3200}
KINDS={'recipients','senders','lists','templates','banks','tickets','integrations'}
def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return secrets.token_hex(16)
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def password(value):
    require(isinstance(value,str) and 12<=len(value)<=200,'Use a password of 12–200 characters')
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(value.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def check_password(value,stored):
    try:
        salt,hashed=stored.split(':'); return hmac.compare_digest(hashlib.scrypt(value.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex(),hashed)
    except (ValueError,AttributeError): return False
class Problem(Exception):
    def __init__(self,message,status=400): self.message,self.status=message,status
def require(condition,message,status=400):
    if not condition: raise Problem(message,status)
def connect():
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    (DATA/'documents').mkdir(exist_ok=True,mode=0o700)
    c=sqlite3.connect(DATA/'postmaster.sqlite',timeout=30,isolation_level=None)
    c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA journal_mode=WAL'); return c
def init():
    with connect() as c: c.executescript((ROOT/'schema.sql').read_text())
def obj(row): return dict(row) if row else None
def resource(row):
    r=dict(row); r['data']=json.loads(r['data']); return r
def audit(c,tenant,user,action,detail=''):
    c.execute('INSERT INTO audit(tenant_id,user_id,action,detail,created) VALUES(?,?,?,?,?)',(tenant,user,action,str(detail)[:1000],now()))
def email(value):
    value=str(value or '').strip().lower(); require(bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value)) and len(value)<=254,'A valid email is required'); return value
def address(data):
    for field in ('name','street','city','postal_code','country'): require(isinstance(data.get(field),str) and bool(data[field].strip()),'Address requires '+field)
    require(len(data['country'])==2,'Use a two-letter country code')
    data['country']=data['country'].upper()
    require(len(data.get('custom',{}))<=5,'Up to five custom fields are supported')
    return data
def totp(secret,code):
    if not code or not str(code).isdigit(): return False
    for offset in (-1,0,1):
        counter=int(time.time()//30)+offset
        raw=hmac.new(base64.b32decode(secret),struct.pack('>Q',counter),hashlib.sha1).digest(); pos=raw[-1]&15
        if hmac.compare_digest(str(code).zfill(6),str((struct.unpack('>I',raw[pos:pos+4])[0]&0x7fffffff)%1000000).zfill(6)): return True
    return False
def money(c,tenant,amount,reason,mail_id=None):
    require(type(amount)==int and amount!=0,'Invalid amount')
    changed=c.execute('UPDATE tenants SET balance=balance+? WHERE id=? AND balance+?>=0',(amount,tenant,amount)).rowcount
    require(changed,'Insufficient funds',409)
    c.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?)',(uid(),tenant,amount,reason,mail_id,now()))
def quote(c,tenant,kind,data):
    require(kind in ('letter','postcard','check'),'Invalid mail type')
    require(len(str(data.get('body','')))<=100000,'Written content exceeds 100,000 characters')
    service=data.get('service','first_class'); require(service in SERVICES,'Invalid mailing service')
    recipients=data.get('recipients',[]); require(isinstance(recipients,list) and 1<=len(recipients)<=1000,'Select 1–1000 recipients')
    for rec in recipients: address(rec)
    address(data.get('sender',{}))
    pages=1
    if not data.get('document_id') and kind=='letter' and str(data.get('body','')).strip():
        from .printing import text_pages
        pages=text_pages(data)
    if data.get('document_id'):
        doc=c.execute('SELECT * FROM documents WHERE id=? AND tenant_id=?',(data['document_id'],tenant)).fetchone(); require(doc,'Document not found',404); pages=doc['pages']
    else: require(bool(str(data.get('body','')).strip()) or kind=='check','Upload a document or write content')
    international=any(x['country']!='US' for x in recipients)
    require(not international or pages<=10,'International letters permit up to 10 pages')
    require(pages<=(118 if data.get('duplex') else 59),'Document exceeds the selected page limit')
    if kind=='postcard':
        require(service=='first_class','Postcards require First Class service'); require(data.get('size','4x6') in ('4x6','6x9'),'Invalid postcard size'); require(pages<=2,'Postcard design must have one or two pages')
    if kind=='check':
        t=c.execute('SELECT * FROM tenants WHERE id=?',(tenant,)).fetchone(); require(PLANS[t['plan']]['checks'],'Checks require Premium or Enterprise',403)
        bank=c.execute("SELECT * FROM resources WHERE id=? AND tenant_id=? AND kind='banks'",(data.get('bank_id',''),tenant)).fetchone()
        require(bank and json.loads(bank['data']).get('status')=='approved','Select an approved bank account',409)
        require(not international and len(recipients)==1 and data['sender']['country']=='US','Checks require a US sender and one US payee')
        require(type(data.get('amount_cents'))==int and 1<=data['amount_cents']<=100000000,'Invalid check amount')
        require(pages<=5,'Check attachment may have up to five pages')
    scheduled=data.get('scheduled') or now()
    try: dt=datetime.fromisoformat(scheduled.replace('Z','+00:00')); require(dt.tzinfo is not None,'Scheduling date must include timezone')
    except (ValueError,TypeError): raise Problem('Invalid scheduling date')
    require(dt<=datetime.now(timezone.utc)+timedelta(days=170),'Schedule up to 170 days ahead')
    cost=SERVICES[service]+max(0,pages-1)*(30 if data.get('color') else 12)+(150 if international else 0)
    if kind=='postcard': cost=110+(60 if data.get('size')=='6x9' else 0)+(150 if international else 0)
    if kind=='check': cost+=100
    if data.get('return_envelope'): cost+=50
    if data.get('prepaid_return_envelope'): cost+=125
    return {'unit_cents':cost,'total_cents':cost*len(recipients),'recipients':len(recipients),'pages':pages,'currency':'USD','scheduled':dt.isoformat(),'rate_type':'operator-configured estimate','check_principal_included':False}
def create_mail(c,tenant,user,kind,data,key=None):
    if key:
        previous=c.execute('SELECT response FROM idempotency WHERE tenant_id=? AND key=?',(tenant,key)).fetchone()
        if previous: return json.loads(previous['response'])
    q=quote(c,tenant,kind,data); ident=uid(); stamp=now()
    if kind=='check' and not data.get('check_number'):
        used=c.execute("SELECT data FROM mail WHERE tenant_id=? AND kind='check'",(tenant,)).fetchall()
        data['check_number']=str(max([1000]+[int(json.loads(x['data']).get('check_number','1000')) for x in used if str(json.loads(x['data']).get('check_number','')).isdigit()])+1)
    if kind=='check':
        for row in c.execute("SELECT data FROM mail WHERE tenant_id=? AND kind='check' AND status!='cancelled'",(tenant,)):
            existing=json.loads(row['data']); require(not(existing.get('bank_id')==data.get('bank_id') and existing.get('check_number')==data.get('check_number')),'Check number already used',409)
    c.execute('INSERT INTO mail VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ident,tenant,user,kind,'unpaid',json.dumps(data),q['total_cents'],q['scheduled'],None,None,stamp,stamp))
    audit(c,tenant,user,'mail.created',ident)
    result={'id':ident,'status':'unpaid','quote':q}
    if key: c.execute('INSERT INTO idempotency VALUES(?,?,?)',(tenant,key,json.dumps(result)))
    return result
