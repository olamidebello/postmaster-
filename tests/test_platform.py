import io,json,os,tempfile,unittest
os.environ['POSTMASTER_DATA']=tempfile.mkdtemp(prefix='postmaster-test-')
os.environ['POSTMASTER_INSECURE']='1'
from app import core
from app.server import application,ATTEMPTS
class Client:
    def __init__(self):self.cookie='';self.csrf=''
    def call(self,path,method='GET',data=None,**extra):
        raw=json.dumps(data).encode() if data is not None else b''; env={'REQUEST_METHOD':method,'PATH_INFO':'/api'+path,'QUERY_STRING':'','wsgi.input':io.BytesIO(raw),'CONTENT_LENGTH':str(len(raw)),'HTTP_COOKIE':self.cookie,'HTTP_X_CSRF_TOKEN':self.csrf,'REMOTE_ADDR':'test',**extra}; result={}
        def start(status,headers):
            result['status']=int(status.split()[0]);result['headers']=dict(headers)
        payload=b''.join(application(env,start));value=json.loads(payload) if result['headers']['Content-Type']=='application/json' else payload
        if result['headers'].get('Set-Cookie'):self.cookie=result['headers']['Set-Cookie'].split(';')[0]
        if isinstance(value,dict) and value.get('csrf'):self.csrf=value['csrf']
        return result['status'],value
    def register(self,email):return self.call('/register','POST',{'name':'Test User','email':email,'password':'Strong-test-passphrase!'})
class PlatformTests(unittest.TestCase):
    def setUp(self):
        core.init()
        with core.connect() as c:
            c.execute('PRAGMA foreign_keys=OFF')
            for row in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='sqlite_sequence'").fetchall():c.execute('DELETE FROM '+row['name'])
        ATTEMPTS.clear();self.a=Client();self.b=Client();self.assertEqual(self.a.register('a@example.com')[0],200);self.assertEqual(self.b.register('b@example.com')[0],200)
        self.tenant=self.a.call('/me')[1]['tenant']['id'];self.user=self.a.call('/me')[1]['user']['id']
    def mailing(self,**extra):
        return {'kind':'letter','body':'Dear {{name}}, thank you.','service':'first_class','sender':{'name':'Sender','street':'1 Main St','city':'Austin','country':'US','postal_code':'78701'},'recipients':[{'name':'Recipient','street':'2 Oak St','city':'Dallas','country':'US','postal_code':'75201'}],**extra}
    def credit(self,amount=10000):
        with core.connect() as c:c.execute('BEGIN IMMEDIATE');core.money(c,self.tenant,amount,'Test verified funds');c.commit()
    def promote(self):
        with core.connect() as c:c.execute('UPDATE users SET superadmin=1 WHERE id=?',(self.user,))
    def test_platform_role_profile_and_audit_controls(self):
        target=self.b.call('/me')[1]['user']['id']
        self.assertEqual(self.a.call('/admin/user-role','POST',{'id':target,'superadmin':True})[0],403)
        self.promote()
        self.assertEqual(self.a.call('/admin/user-role','POST',{'id':self.user,'superadmin':False})[0],409)
        self.assertEqual(self.a.call('/admin/user-edit','POST',{'id':target,'name':'Updated','email':'a@example.com'})[0],409)
        self.assertEqual(self.a.call('/admin/user-edit','POST',{'id':target,'name':'Updated','email':'b@example.com'})[0],200)
        self.assertEqual(self.a.call('/admin/user-role','POST',{'id':target,'superadmin':'true'})[0],400)
        self.assertEqual(self.a.call('/admin/user-role','POST',{'id':target,'superadmin':True})[0],200)
        self.assertEqual(self.b.call('/me')[0],401)
        with core.connect() as c:
            self.assertEqual(c.execute('SELECT superadmin FROM users WHERE id=?',(target,)).fetchone()[0],1)
        logs=self.a.call('/admin/audit')[1]
        self.assertTrue(any(x['action']=='admin.user_role' for x in logs))

    def test_admin_provider_settings_and_token_revocation(self):
        from app import credentials
        path=core.DATA/'provider-credentials.json';path.unlink(missing_ok=True)
        try:
            self.assertEqual(self.a.call('/admin/keys')[0],403)
            self.promote()
            secret='sk_test_private_example'
            self.assertEqual(self.a.call('/admin/keys','POST',{'key':'STRIPE_SECRET_KEY','value':secret})[0],200)
            self.assertEqual(credentials.get('STRIPE_SECRET_KEY'),secret)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertNotIn(secret,json.dumps(self.a.call('/admin/keys')[1]))
            self.assertEqual(self.a.call('/admin/keys','POST',{'key':'SMTP_PORT','value':'wrong'})[0],400)
            self.assertEqual(self.a.call('/admin/keys','POST',{'key':'PUBLIC_URL','value':'anything'})[0],400)
            token=self.a.call('/tokens','POST',{'name':'Integration'})[1]
            self.assertEqual(self.a.call('/admin/keys',HTTP_AUTHORIZATION='Bearer '+token['token'])[0],403)
            listing=self.a.call('/admin/tokens')[1]
            self.assertNotIn(token['token'],json.dumps(listing))
            self.assertEqual(self.a.call('/admin/revoke-token','POST',{'id':token['id']})[0],200)
            self.assertEqual(self.a.call('/mail',HTTP_AUTHORIZATION='Bearer '+token['token'])[0],401)
            self.assertNotIn(secret,json.dumps(self.a.call('/admin/audit')[1]))
        finally:path.unlink(missing_ok=True)

    def test_marketplace_purchase_replay_isolation_and_refund(self):
        self.promote();self.credit(10000)
        product={'name':'Print design','description':'Operator service','category':'Services','price_cents':1500,'active':True}
        self.assertEqual(self.b.call('/admin/marketplace/product','POST',product)[0],403)
        status,p=self.a.call('/admin/marketplace/product','POST',product);self.assertEqual(status,200)
        b={'product_id':p['id'],'quantity':2,'unit_price_cents':1500,'request_key':'purchase-one'}
        self.assertEqual(self.a.call('/marketplace/purchase','POST',{**b,'unit_price_cents':1})[0],409)
        status,order=self.a.call('/marketplace/purchase','POST',b);self.assertEqual(status,200)
        self.assertEqual(order['total'],3000)
        self.assertEqual(self.a.call('/marketplace/purchase','POST',b)[1]['id'],order['id'])
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],7000)
        self.assertEqual(self.b.call('/marketplace/orders')[1],[])
        action={'id':order['id'],'status':'refunded','note':'Customer request'}
        self.assertEqual(self.a.call('/admin/marketplace/order','POST',action)[0],200)
        self.assertEqual(self.a.call('/admin/marketplace/order','POST',action)[0],200)
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],10000)
        self.assertEqual(self.a.call('/admin/marketplace/order','POST',{**action,'status':'completed'})[0],409)
        self.assertEqual(self.a.call('/admin/marketplace/product','POST',{**product,'id':p['id'],'active':False})[0],200)
        self.assertEqual(self.b.call('/marketplace')[1],[])

    def test_paystack_verification_matches_amount_and_credits_once(self):
        from unittest.mock import patch
        from app import credentials,paystack_gateway
        ref='pm-test-reference';stamp=core.now()
        with core.connect() as c:
            c.execute('INSERT INTO gateway_checkouts VALUES(?,?,?,?,?,?,?,0,?)',(ref,self.tenant,self.user,'paystack',1000,'USD','a@example.com',stamp))
        result={'reference':ref,'status':'success','amount':1000,'currency':'USD','customer':{'email':'a@example.com'}}
        with patch.object(paystack_gateway,'get',return_value='test-key'),patch.object(paystack_gateway,'request',return_value=result) as provider:
            self.assertEqual(self.b.call('/billing/paystack/verify','POST',{'reference':ref})[0],404)
            self.assertEqual(self.a.call('/billing/paystack/verify','POST',{'reference':ref})[0],200)
            self.assertEqual(self.a.call('/billing/paystack/verify','POST',{'reference':ref})[0],200)
            self.assertEqual(provider.call_count,1)
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],1000)
        with core.connect() as c:c.execute('UPDATE gateway_checkouts SET credited=0 WHERE id=?',(ref,))
        with patch.object(paystack_gateway,'get',return_value='test-key'),patch.object(paystack_gateway,'request',return_value={**result,'amount':999}):
            self.assertEqual(self.a.call('/billing/paystack/verify','POST',{'reference':ref})[0],409)
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],1000)

    def test_starter_catalog_seed_preserves_operator_edits(self):
        self.assertEqual(self.a.call('/admin/marketplace/seed','POST',{})[0],403)
        self.promote()
        status,result=self.a.call('/admin/marketplace/seed','POST',{});self.assertEqual(status,200);self.assertEqual(result['added'],8)
        products=self.b.call('/marketplace')[1];self.assertEqual(len(products),8)
        p=products[0]
        self.assertEqual(self.a.call('/admin/marketplace/product','POST',{'id':p['id'],'name':'Operator edited','description':'Custom scope','category':'Services','price_cents':12345,'active':False})[0],200)
        self.assertEqual(self.a.call('/admin/marketplace/seed','POST',{})[1]['added'],0)
        d=self.a.call('/admin/marketplace')[1]
        kept=next(x for x in d['products'] if x['id']==p['id'])
        self.assertEqual((kept['name'],kept['price'],kept['active']),('Operator edited',12345,0))

    def test_brand_assets_served_and_traversal_rejected(self):
        for path in ['/assets/postmaster-mark.png','/assets/postmaster-concept-portrait.png']:
            result={};env={'REQUEST_METHOD':'GET','PATH_INFO':path}
            payload=b''.join(application(env,lambda status,headers:result.update(status=status,headers=dict(headers))))
            self.assertTrue(result['status'].startswith('200'));self.assertEqual(result['headers']['Content-Type'],'image/png');self.assertTrue(payload.startswith(b'\x89PNG\r\n\x1a\n'))
        result={};payload=b''.join(application({'REQUEST_METHOD':'GET','PATH_INFO':'/assets/../server.py'},lambda status,headers:result.update(status=status)))
        self.assertTrue(result['status'].startswith('404'))
    def test_tenant_isolation(self):
        status,resource=self.a.call('/resources/recipients','POST',self.mailing()['recipients'][0]);self.assertEqual(status,200)
        self.assertEqual(self.b.call('/resources/recipients')[1],[])
        self.assertEqual(self.b.call('/resources/recipients/'+resource['id'],'DELETE')[0],404)
        _,mail=self.a.call('/mail','POST',self.mailing());self.assertEqual(self.b.call('/mail/'+mail['id'])[0],404)
    def test_atomic_payment_cancel_and_refund(self):
        self.credit();status,mail=self.a.call('/mail','POST',self.mailing());self.assertEqual(status,200)
        self.assertEqual(self.a.call('/mail/'+mail['id']+'/pay','POST',{})[0],200)
        self.assertEqual(self.a.call('/mail/'+mail['id']+'/pay','POST',{})[0],409)
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],10000-mail['quote']['total_cents'])
        self.assertEqual(self.a.call('/mail/'+mail['id']+'/cancel','POST',{})[0],200)
        self.assertEqual(self.a.call('/mail/'+mail['id']+'/cancel','POST',{})[0],409)
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],10000)
    def test_insufficient_funds_rolls_back(self):
        _,mail=self.a.call('/mail','POST',self.mailing());self.assertEqual(self.a.call('/mail/'+mail['id']+'/pay','POST',{})[0],409);self.assertEqual(self.a.call('/mail/'+mail['id'])[1]['status'],'unpaid');self.assertEqual(self.a.call('/ledger')[1],[])
    def test_idempotency(self):
        a=self.a.call('/mail','POST',self.mailing(),HTTP_IDEMPOTENCY_KEY='unique');b=self.a.call('/mail','POST',self.mailing(),HTTP_IDEMPOTENCY_KEY='unique');self.assertEqual(a,b);self.assertEqual(len(self.a.call('/mail')[1]),1)
    def test_csrf_and_admin(self):
        self.assertEqual(self.a.call('/resources/lists','POST',{'name':'Bad'},HTTP_X_CSRF_TOKEN='wrong')[0],403)
        self.assertEqual(self.a.call('/admin/overview')[0],403)
        self.assertEqual(self.a.call('/admin/credit','POST',{'tenant_id':self.tenant,'amount_cents':100,'reason':'test'})[0],403)
    def test_csv_atomic_and_formula_escape(self):
        self.assertEqual(self.a.call('/import','POST',{'name':'Broken','csv':'name,street,city,postal_code,country\nGood,1 Main,Austin,78701,US\nBad,,,,'})[0],400)
        self.assertEqual(self.a.call('/resources/recipients')[1],[]);self.assertEqual(self.a.call('/resources/lists')[1],[])
        self.assertEqual(self.a.call('/import','POST',{'csv':'name,street,city,postal_code,country\n=Evil,1 Main,Austin,78701,US'})[0],200)
        self.assertIn(b"'=Evil",self.a.call('/export')[1])
    def test_check_gating_and_no_raw_bank_data(self):
        self.assertEqual(self.a.call('/quote','POST',self.mailing(kind='check',amount_cents=10000))[0],403)
        self.assertEqual(self.a.call('/resources/banks','POST',{'company':'Test LLC','bank_name':'Bank','last4':'1234','account_number':'123412341234'})[0],400)
        self.promote();self.a.call('/admin/plan','POST',{'tenant_id':self.tenant,'plan':'premium'});status,bank=self.a.call('/resources/banks','POST',{'company':'Test LLC','bank_name':'Bank','last4':'1234'});self.assertEqual(status,200)
        data=self.mailing(kind='check',amount_cents=10000,bank_id=bank['id']);self.assertEqual(self.a.call('/quote','POST',data)[0],409)
        self.assertEqual(self.a.call('/admin/bank','POST',{'id':bank['id'],'status':'approved','verification_reference':'verified-by-operator'})[0],200)
        self.assertEqual(self.a.call('/quote','POST',data)[0],200)
    def test_fulfillment_and_single_failed_refund(self):
        self.promote();self.credit();_,m=self.a.call('/mail','POST',self.mailing());self.a.call('/mail/'+m['id']+'/pay','POST',{})
        self.assertEqual(self.a.call('/admin/fulfill','POST',{'id':m['id'],'status':'delivered','note':'fake'})[0],409)
        self.assertEqual(self.a.call('/admin/fulfill','POST',{'id':m['id'],'status':'preparing','note':'Operator picked job'})[0],200)
        self.assertEqual(self.a.call('/mail/'+m['id']+'/cancel','POST',{})[0],409)
        self.assertEqual(self.a.call('/admin/fulfill','POST',{'id':m['id'],'status':'on_the_way','note':'No reference'})[0],400)
        self.a.call('/admin/fulfill','POST',{'id':m['id'],'status':'failed','note':'Printer failed'})
        self.assertEqual(self.a.call('/admin/refund','POST',{'id':m['id'],'reason':'Not produced'})[0],200)
        self.assertEqual(self.a.call('/admin/refund','POST',{'id':m['id'],'reason':'Again'})[0],409)
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],10000)
    def test_api_tokens_restricted_and_revocable(self):
        status,t=self.a.call('/tokens','POST',{'name':'test'});self.assertEqual(status,200)
        client=Client();auth={'HTTP_AUTHORIZATION':'Bearer '+t['token']}
        self.assertEqual(client.call('/mail','POST',self.mailing(),**auth)[0],200)
        self.assertEqual(client.call('/admin/credit','POST',{},**auth)[0],403)
        self.assertEqual(client.call('/resources/lists','POST',{'name':'no'},**auth)[0],403)
        self.a.call('/tokens/'+t['id'],'DELETE');self.assertEqual(client.call('/mail',**auth)[0],401)
    def test_schedule_worker_does_not_fake_postal_status(self):
        self.credit();future=(core.datetime.now(core.timezone.utc)+core.timedelta(days=1)).isoformat();_,m=self.a.call('/mail','POST',self.mailing(scheduled=future));self.assertEqual(self.a.call('/mail/'+m['id']+'/pay','POST',{})[1]['status'],'scheduled')
        with core.connect() as c:c.execute('UPDATE mail SET scheduled=? WHERE id=?',(core.now(),m['id']))
        from app.worker import run
        run();self.assertEqual(self.a.call('/mail/'+m['id'])[1]['status'],'queued')
    def test_pdf_parser_and_document_scope(self):
        from pypdf import PdfWriter
        import base64
        writer=PdfWriter();writer.add_blank_page(width=612,height=792);buf=io.BytesIO();writer.write(buf)
        status,doc=self.a.call('/documents','POST',{'name':'sample.pdf','content':base64.b64encode(buf.getvalue()).decode()});self.assertEqual(status,200);self.assertEqual(doc['pages'],1)
        self.assertEqual(self.b.call('/documents/'+doc['id'])[0],404)
        self.assertEqual(self.a.call('/documents','POST',{'name':'bad.pdf','content':base64.b64encode(b'%PDF-not-valid').decode()})[0],400)
    def test_team_viewer_and_revocation(self):
        self.promote();self.a.call('/admin/plan','POST',{'tenant_id':self.tenant,'plan':'premium'});_,inv=self.a.call('/team/invite','POST',{'email':'b@example.com','role':'viewer'});self.assertEqual(self.b.call('/team/accept','POST',{'token':inv['invitation_token']})[0],200)
        self.b.call('/workspace','POST',{'id':self.tenant});self.assertEqual(self.b.call('/mail','POST',self.mailing())[0],403);self.assertEqual(self.b.call('/mail')[0],200)
        user=self.b.call('/me')[1]['user']['id'];self.a.call('/team/'+user,'DELETE');self.assertEqual(self.b.call('/mail')[0],401)
    def test_printable_merge_and_page_count(self):
        from pypdf import PdfReader
        _,mail=self.a.call('/mail','POST',self.mailing(body='Dear {{name}},\n\nYour invoice reference is {{custom_1}}.'))
        status,pdf=self.a.call('/mail/'+mail['id']+'/print');self.assertEqual(status,200)
        reader=PdfReader(io.BytesIO(pdf));self.assertEqual(len(reader.pages),2);self.assertIn('Dear Recipient',reader.pages[1].extract_text())
        self.assertEqual(self.b.call('/mail/'+mail['id']+'/print')[0],404)
    def test_bank_edit_invalidates_approval(self):
        self.promote();self.a.call('/admin/plan','POST',{'tenant_id':self.tenant,'plan':'premium'})
        data={'company':'Test LLC','bank_name':'Bank','last4':'1234'}
        _,bank=self.a.call('/resources/banks','POST',data);self.a.call('/admin/bank','POST',{'id':bank['id'],'status':'approved','verification_reference':'verified'})
        _,mail=self.a.call('/mail','POST',self.mailing(kind='check',bank_id=bank['id'],amount_cents=12345))
        self.a.call('/resources/banks/'+bank['id'],'PUT',{**data,'last4':'9999'})
        self.credit();self.assertEqual(self.a.call('/mail/'+mail['id']+'/pay','POST',{})[0],409)
    def test_signed_stripe_webhook_is_replay_safe(self):
        from unittest.mock import patch
        from app.payments import webhook
        event={'type':'checkout.session.completed','data':{'object':{'id':'cs_test_1','amount_total':2500,'currency':'usd','client_reference_id':self.tenant,'payment_status':'paid'}}}
        with core.connect() as c:
            c.execute('INSERT INTO checkouts VALUES(?,?,?,0,?)',('cs_test_1',self.tenant,2500,core.now()))
        env={'STRIPE_SECRET_KEY':'sk_test_placeholder','STRIPE_WEBHOOK_SECRET':'whsec_test'}
        import hashlib,hmac
        with patch.dict(os.environ,env):
            raw=json.dumps(event).encode();stamp=str(int(core.time.time()));signature=hmac.new(b'whsec_test',stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
            def deliver(payload=raw,sig='t='+stamp+',v1='+signature):
                result={};env={'REQUEST_METHOD':'POST','PATH_INFO':'/api/payments/webhook','QUERY_STRING':'','wsgi.input':io.BytesIO(payload),'CONTENT_LENGTH':str(len(payload)),'HTTP_STRIPE_SIGNATURE':sig,'REMOTE_ADDR':'stripe'}
                data=b''.join(application(env,lambda status,headers:result.update(status=int(status.split()[0]))));return result['status'],json.loads(data)
            self.assertEqual(deliver()[0],200);self.assertEqual(deliver()[0],200)
            self.assertEqual(deliver(sig='t='+stamp+',v1=bad')[0],400)
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],2500)
        self.assertEqual(len(self.a.call('/ledger')[1]),1)
    def test_stripe_rejects_amount_mismatch(self):
        from unittest.mock import patch
        from app.payments import webhook
        event={'type':'checkout.session.completed','data':{'object':{'id':'cs_test_2','amount_total':2501,'currency':'usd','client_reference_id':self.tenant,'payment_status':'paid'}}}
        with core.connect() as c:
            c.execute('INSERT INTO checkouts VALUES(?,?,?,0,?)',('cs_test_2',self.tenant,2500,core.now()))
            with patch.dict(os.environ,{'STRIPE_SECRET_KEY':'test','STRIPE_WEBHOOK_SECRET':'test'}),patch('stripe.Webhook.construct_event',return_value=event):
                with self.assertRaises(core.Problem):webhook(c,b'{}','test')
        self.assertEqual(self.a.call('/me')[1]['tenant']['balance'],0)
if __name__=='__main__':unittest.main()
