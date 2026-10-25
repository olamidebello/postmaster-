"""Stripe hosted wallet funding. Webhooks, never redirects, grant funds."""
import os,time
from .core import *
from .credentials import get
def ready():return bool(get('STRIPE_SECRET_KEY') and get('STRIPE_WEBHOOK_SECRET'))
def checkout(c,tenant,user,amount):
    require(ready(),'Card funding is not configured',503);require(type(amount)==int and 500<=amount<=1000000,'Top-up must be $5–$10,000')
    import stripe
    base=os.environ.get('PUBLIC_URL','');require(base.startswith('https://'),'HTTPS public URL required for checkout',503)
    try:
        result=stripe.checkout.Session.create(api_key=get('STRIPE_SECRET_KEY'),mode='payment',payment_method_types=['card'],client_reference_id=tenant,metadata={'purpose':'postmaster_wallet','tenant_id':tenant},line_items=[{'price_data':{'currency':'usd','unit_amount':amount,'product_data':{'name':'Postmaster mailing balance'}},'quantity':1}],success_url=base+'/#billing',cancel_url=base+'/#billing')
    except stripe.StripeError:raise Problem('Payment provider unavailable; try again later',503)
    c.execute('INSERT INTO checkouts VALUES(?,?,?,0,?)',(result.id,tenant,amount,now()));audit(c,tenant,user,'checkout.created',result.id);return {'url':result.url}
def webhook(c,raw,signature):
    require(ready(),'Payments not configured',503)
    import stripe
    try:event=stripe.Webhook.construct_event(raw,signature,get('STRIPE_WEBHOOK_SECRET'),tolerance=300)
    except (ValueError,stripe.SignatureVerificationError):raise Problem('Invalid payment signature',400)
    if event['type'] not in ('checkout.session.completed','checkout.session.async_payment_succeeded'):return {'received':True}
    obj=event['data']['object'];obj=obj.to_dict() if hasattr(obj,'to_dict') else obj;row=c.execute('SELECT * FROM checkouts WHERE id=?',(obj.get('id'),)).fetchone()
    if not row:return {'received':True}
    require(obj.get('payment_status')=='paid' and obj.get('currency')=='usd' and obj.get('amount_total')==row['amount'] and obj.get('client_reference_id')==row['tenant_id'],'Payment details do not match checkout')
    if row['credited']:return {'received':True}
    money(c,row['tenant_id'],row['amount'],'Stripe payment '+obj['id']);c.execute('UPDATE checkouts SET credited=1 WHERE id=?',(obj['id'],));audit(c,row['tenant_id'],None,'payment.verified',obj['id']);return {'received':True}
