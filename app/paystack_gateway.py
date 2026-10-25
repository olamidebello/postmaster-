"""USD Paystack wallet funding for merchant accounts enabled for USD."""
import json,os,urllib.request,urllib.error
from .core import *
from .credentials import get
def ready():return get('PAYSTACK_ENABLED','false')=='true' and bool(get('PAYSTACK_SECRET_KEY'))
def request(path,payload=None):
    req=urllib.request.Request('https://api.paystack.co'+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Authorization':'Bearer '+get('PAYSTACK_SECRET_KEY'),'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=20) as response: result=json.load(response)
    except (OSError,ValueError):raise Problem('Paystack unavailable; retry verification later',503)
    require(result.get('status') is True and isinstance(result.get('data'),dict),'Paystack rejected the request',503);return result['data']
def checkout(c,tenant,user,em,amount):
    require(ready(),'Paystack is not enabled',503);require(type(amount)==int and 500<=amount<=1000000,'Top-up must be $5–$10,000')
    base=os.environ.get('PUBLIC_URL','');require(base.startswith('https://'),'HTTPS PUBLIC_URL required',503)
    reference='pm-'+uid();result=request('/transaction/initialize',{'email':em,'amount':amount,'currency':'USD','reference':reference,'callback_url':base+'/#billing','metadata':{'tenant_id':tenant,'purpose':'postmaster_wallet'}})
    url=result.get('authorization_url','');require(result.get('reference')==reference and url.startswith('https://checkout.paystack.com/'),'Unexpected Paystack checkout response',503)
    c.execute('INSERT INTO gateway_checkouts VALUES(?,?,?,?,?,?,?,0,?)',(reference,tenant,user,'paystack',amount,'USD',em,now()));audit(c,tenant,user,'paystack.checkout',reference);return {'url':url,'reference':reference}
def verify(c,tenant,user,reference):
    row=c.execute("SELECT * FROM gateway_checkouts WHERE id=? AND tenant_id=? AND provider='paystack'",(reference,tenant)).fetchone();require(row,'Payment not found',404)
    if row['credited']:return {'credited':True}
    require(bool(get('PAYSTACK_SECRET_KEY')),'Paystack verification key is missing',503);result=request('/transaction/verify/'+row['id'])
    require(result.get('status')=='success','Payment is not completed',409)
    require(result.get('reference')==row['id'] and type(result.get('amount'))==int and result['amount']==row['amount'] and result.get('currency')==row['currency'] and result.get('customer',{}).get('email','').lower()==row['email'].lower(),'Payment details do not match checkout',409)
    money(c,tenant,row['amount'],'Paystack payment '+row['id']);c.execute('UPDATE gateway_checkouts SET credited=1 WHERE id=?',(row['id'],));audit(c,tenant,user,'paystack.verified',row['id']);return {'credited':True}
