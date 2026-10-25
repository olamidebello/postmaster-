"""Dependency-light WSGI application. Serve with Gunicorn behind TLS."""
import argparse, base64, csv, hmac, io, json, mimetypes, os, secrets, smtplib, time, traceback
from email.message import EmailMessage
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server
from .core import *
MAX_BODY=22*1024*1024
ATTEMPTS={}
def send_email(to,subject,body):
    require(os.environ.get('SMTP_HOST'),'Email delivery is not configured',503)
    message=EmailMessage(); message['From']=os.environ.get('SMTP_FROM','postmaster@localhost'); message['To']=to; message['Subject']=subject; message.set_content(body)
    with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.environ.get('SMTP_PORT','587')),timeout=15) as smtp:
        smtp.starttls()
        if os.environ.get('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
        smtp.send_message(message)
def client_ip(r):
    addr=r.env.get('REMOTE_ADDR','')
    return r.env.get('HTTP_X_REAL_IP',addr) if addr in ('127.0.0.1','::1') else addr
def limit(key):
    current=time.time(); recent=[x for x in ATTEMPTS.get(key,[]) if x>current-900]; require(len(recent)<12,'Too many attempts; try again in 15 minutes',429); recent.append(current); ATTEMPTS[key]=recent
    if len(ATTEMPTS)>10000:
        for old in list(ATTEMPTS):
            if not ATTEMPTS[old] or ATTEMPTS[old][-1]<current-900: ATTEMPTS.pop(old,None)
class Request:
    def __init__(self,env):
        self.env=env; self.method=env['REQUEST_METHOD']; self.path=env.get('PATH_INFO','/'); self.query=parse_qs(env.get('QUERY_STRING','')); self.headers=[]; self.user=None; self.tenant=None; self.role=None; self.token_auth=False
        length=int(env.get('CONTENT_LENGTH') or 0); require(0<=length<=MAX_BODY,'Request too large',413); self.raw=env['wsgi.input'].read(length)
        try: self.body=json.loads(self.raw) if self.raw else {}; require(isinstance(self.body,dict),'JSON object required')
        except (ValueError,UnicodeDecodeError): raise Problem('Invalid JSON')
    def auth(self,c):
        bearer=self.env.get('HTTP_AUTHORIZATION','')
        if bearer.startswith('Bearer '):
            row=c.execute('SELECT * FROM api_tokens WHERE hash=?',(digest(bearer[7:]),)).fetchone(); require(row,'Invalid token',401)
            self.token_auth=True; self.tenant=row['tenant_id']; self.user=c.execute('SELECT * FROM users WHERE id=?',(row['user_id'],)).fetchone()
            require(self.method=='GET' or self.path in ('/api/mail','/api/quote'),'API tokens only permit reading, quoting and creating mail',403)
        else:
            cookies={x.strip().split('=',1)[0]:x.strip().split('=',1)[1] for x in self.env.get('HTTP_COOKIE','').split(';') if '=' in x}
            row=c.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(digest(cookies.get('session','')),int(time.time()))).fetchone(); require(row,'Sign in to continue',401)
            self.tenant=row['tenant_id']; self.user=c.execute('SELECT * FROM users WHERE id=?',(row['user_id'],)).fetchone(); self.session=row
            if self.method!='GET': require(hmac.compare_digest(self.env.get('HTTP_X_CSRF_TOKEN',''),row['csrf']),'Refresh the page and try again',403)
        require(self.user and self.user['active'],'Account unavailable',403)
        member=c.execute('SELECT role FROM members WHERE tenant_id=? AND user_id=?',(self.tenant,self.user['id'])).fetchone(); require(member,'Workspace access revoked',403); self.role=member['role']
    def can(self,*roles): require(self.role in roles,'Your role cannot perform this action',403)
    def admin(self): require(self.user['superadmin'],'Super administrator access required',403)
    def cookie(self,token): self.headers.append(('Set-Cookie','session='+token+'; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200'+('' if os.environ.get('POSTMASTER_INSECURE')=='1' else '; Secure')))
def session(c,r,user,tenant):
    token=secrets.token_urlsafe(40); csrf=secrets.token_urlsafe(32)
    c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(token),user,tenant,csrf,int(time.time())+43200)); r.cookie(token)
    return {'csrf':csrf}
def dispatch(c,r):
    p=r.path; b=r.body; method=r.method
    if p=='/api/health': return {'status':'ok','database':bool(c.execute('SELECT 1').fetchone())}
    if p=='/api/payments/webhook' and method=='POST':
        from .payments import webhook
        return webhook(c,r.raw,r.env.get('HTTP_STRIPE_SIGNATURE',''))
    if p=='/api/catalog': return {'plans':PLANS,'services':SERVICES,'currency':'USD','rates_are_estimates':True,'integrations':['Zapier','Clio','FileVine','HubSpot','QuickBooks Online','Xero','Google Docs'],'fulfillment':'manual operator dispatch','payments':'stripe' if __import__('app.payments',fromlist=['ready']).ready() else 'manual credit with audit trail'}
    if p=='/api/register' and method=='POST':
        limit('register:'+client_ip(r)); em=email(b.get('email')); pw=password(b.get('password')); name=str(b.get('name','')).strip(); require(name,'Name required')
        require(not c.execute('SELECT id FROM users WHERE email=?',(em,)).fetchone(),'Email is already registered',409)
        user,tenant=uid(),uid(); c.execute('INSERT INTO users(id,email,name,password,created) VALUES(?,?,?,?,?)',(user,em,name,pw,now())); c.execute('INSERT INTO tenants(id,name,created) VALUES(?,?,?)',(tenant,str(b.get('company') or name),now())); c.execute('INSERT INTO members VALUES(?,?,?)',(tenant,user,'owner')); audit(c,tenant,user,'account.registered'); return session(c,r,user,tenant)
    if p=='/api/login' and method=='POST':
        limit('login:'+client_ip(r)); em=email(b.get('email')); u=c.execute('SELECT * FROM users WHERE email=?',(em,)).fetchone()
        require(u and u['active'] and check_password(b.get('password',''),u['password']),'Invalid credentials',401)
        require(not u['totp'] or totp(u['totp'],b.get('code')),'Authenticator code required',401)
        tenant=c.execute('SELECT tenant_id FROM members WHERE user_id=? ORDER BY rowid LIMIT 1',(u['id'],)).fetchone(); require(tenant,'No workspace access',403)
        audit(c,tenant[0],u['id'],'account.login'); return session(c,r,u['id'],tenant[0])
    if p=='/api/password-reset' and method=='POST':
        limit('reset:'+client_ip(r)); em=email(b.get('email')); require(os.environ.get('SMTP_HOST'),'Password reset email is not configured',503)
        u=c.execute('SELECT * FROM users WHERE email=?',(em,)).fetchone()
        if u:
            token=secrets.token_urlsafe(40); c.execute('INSERT INTO resets VALUES(?,?,?)',(digest(token),u['id'],int(time.time())+1800)); send_email(em,'Reset your Postmaster password',os.environ.get('PUBLIC_URL','http://localhost:8080')+'/#reset='+token)
        return {'message':'If the account exists, a reset link has been sent.'}
    if p=='/api/password-reset/complete' and method=='POST':
        limit('reset-complete:'+client_ip(r)); token=c.execute('SELECT * FROM resets WHERE hash=? AND expires>?',(digest(str(b.get('token',''))),int(time.time()))).fetchone(); require(token,'Reset link invalid or expired')
        c.execute('UPDATE users SET password=? WHERE id=?',(password(b.get('password')),token['user_id'])); c.execute('DELETE FROM resets WHERE user_id=?',(token['user_id'],)); c.execute('DELETE FROM sessions WHERE user_id=?',(token['user_id'],)); return {'message':'Password changed; sign in again.'}
    r.auth(c); tenant=r.tenant; user=r.user['id']
    if p=='/api/me':
        t=obj(c.execute('SELECT * FROM tenants WHERE id=?',(tenant,)).fetchone()); return {'user':{k:r.user[k] for k in ('id','email','name','superadmin')},'tenant':t,'role':r.role,'two_factor':bool(r.user['totp']),'csrf':r.session['csrf'] if not r.token_auth else None,'workspaces':[dict(x) for x in c.execute('SELECT t.id,t.name,m.role FROM tenants t JOIN members m ON m.tenant_id=t.id WHERE m.user_id=?',(user,))]}
    if p=='/api/logout' and method=='POST': c.execute('DELETE FROM sessions WHERE token=?',(r.session['token'],)); r.cookie(''); return {'ok':True}
    if p=='/api/workspace' and method=='POST':
        require(c.execute('SELECT 1 FROM members WHERE tenant_id=? AND user_id=?',(b.get('id'),user)).fetchone(),'Workspace not found',404); c.execute('UPDATE sessions SET tenant_id=? WHERE token=?',(b['id'],r.session['token'])); return {'ok':True}
    if p=='/api/dashboard':
        counts={x['status']:x['n'] for x in c.execute('SELECT status,count(*) n FROM mail WHERE tenant_id=? GROUP BY status',(tenant,))}; return {'counts':counts,'recent':[resource(x) for x in c.execute('SELECT * FROM mail WHERE tenant_id=? ORDER BY created DESC LIMIT 8',(tenant,))],'balance':c.execute('SELECT balance FROM tenants WHERE id=?',(tenant,)).fetchone()[0]}
    if p=='/api/profile' and method=='POST':
        em=email(b.get('email')); require(not c.execute('SELECT id FROM users WHERE email=? AND id!=?',(em,user)).fetchone(),'Email already registered',409); require(b.get('name'),'Name required'); c.execute('UPDATE users SET name=?,email=? WHERE id=?',(b['name'],em,user)); audit(c,tenant,user,'profile.updated'); return {'ok':True}
    if p=='/api/password' and method=='POST':
        require(check_password(b.get('current',''),r.user['password']),'Current password is incorrect',403); c.execute('UPDATE users SET password=? WHERE id=?',(password(b.get('password')),user)); c.execute('DELETE FROM sessions WHERE user_id=? AND token!=?',(user,r.session['token'])); return {'ok':True}
    if p=='/api/two-factor' and method=='POST':
        require(check_password(b.get('password',''),r.user['password']),'Password required',403)
        if b.get('action')=='setup':
            secret=base64.b32encode(secrets.token_bytes(20)).decode(); c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('totp-pending:'+user,json.dumps({'secret':secret,'expires':time.time()+600}))); return {'secret':secret,'issuer':'Postmaster','account':r.user['email']}
        if b.get('action')=='enable':
            row=c.execute('SELECT value FROM settings WHERE key=?',('totp-pending:'+user,)).fetchone(); pending=json.loads(row[0]) if row else {}; require(pending.get('expires',0)>time.time() and totp(pending.get('secret',''),b.get('code')),'Invalid or expired setup code'); c.execute('UPDATE users SET totp=? WHERE id=?',(pending['secret'],user)); c.execute('DELETE FROM settings WHERE key=?',('totp-pending:'+user,)); return {'ok':True}
        require(totp(r.user['totp'] or '',b.get('code')),'Authenticator code required'); c.execute('UPDATE users SET totp=NULL WHERE id=?',(user,)); return {'ok':True}
    if p=='/api/settings' and method=='POST':
        r.can('owner','admin'); t=c.execute('SELECT * FROM tenants WHERE id=?',(tenant,)).fetchone(); days=b.get('retention',90); require(type(days)==int and 1<=days<=1095,'Retention must be 1–1095 days'); require(t['plan']!='free' or days==90,'Retention controls require Premium',403); c.execute('UPDATE tenants SET name=?,retention=? WHERE id=?',(str(b.get('name') or t['name']),days,tenant)); return {'ok':True}
    if p=='/api/delete-account' and method=='POST':
        require(check_password(b.get('password',''),r.user['password']),'Password required',403); ident=uid(); c.execute('INSERT INTO resources VALUES(?,?,?,?,?,?)',(ident,tenant,'tickets',json.dumps({'subject':'Account deletion request','body':'Requested by '+r.user['email'],'status':'open'}),now(),now())); audit(c,tenant,user,'account.deletion_requested'); return {'message':'Deletion request recorded for administrator review.','id':ident}
    if p=='/api/documents':
        if method=='GET': return [dict(x) for x in c.execute('SELECT * FROM documents WHERE tenant_id=? ORDER BY created DESC',(tenant,))]
        r.can('owner','admin','sender'); require(method=='POST','Method not allowed',405)
        try: content=base64.b64decode(b.get('content',''),validate=True)
        except ValueError: raise Problem('Invalid document encoding')
        require(0<len(content)<=15*1024*1024,'PDF must be between 1 byte and 15 MB'); require(content.startswith(b'%PDF-'),'Upload a PDF document')
        try:
            from pypdf import PdfReader
            pdf=PdfReader(io.BytesIO(content)); require(not pdf.is_encrypted,'Encrypted PDFs are not supported'); pages=len(pdf.pages); require(1<=pages<=118,'PDF must contain 1–118 pages')
        except ImportError: raise Problem('PDF parser is not installed',503)
        except Problem: raise
        except Exception: raise Problem('PDF could not be read')
        ident=uid(); (DATA/'documents'/ident).write_bytes(content); os.chmod(DATA/'documents'/ident,0o600); c.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?)',(ident,tenant,str(b.get('name','document.pdf'))[:200],'application/pdf',pages,len(content),now())); audit(c,tenant,user,'document.uploaded',ident); return {'id':ident,'pages':pages}
    if p.startswith('/api/documents/'):
        ident=p.split('/')[-1]; doc=c.execute('SELECT * FROM documents WHERE id=? AND tenant_id=?',(ident,tenant)).fetchone(); require(doc,'Document not found',404); path=DATA/'documents'/ident
        if method=='DELETE':
            r.can('owner','admin'); require(not c.execute("SELECT 1 FROM mail WHERE tenant_id=? AND status NOT IN ('delivered','cancelled','failed') AND json_extract(data,'$.document_id')=?",(tenant,ident)).fetchone(),'Document is used by an active order',409); path.unlink(missing_ok=True); c.execute('DELETE FROM documents WHERE id=?',(ident,)); return {'ok':True}
        require(method=='GET','Method not allowed',405); require(path.exists(),'Document preview has expired',410); return (path.read_bytes(),'application/pdf')
    if p.startswith('/api/resources/'):
        parts=p.split('/'); kind=parts[3]; require(kind in KINDS,'Unknown resource',404); ident=parts[4] if len(parts)>4 else None
        if method=='GET':
            rows=[resource(x) for x in c.execute('SELECT * FROM resources WHERE tenant_id=? AND kind=? ORDER BY created DESC LIMIT 5000',(tenant,kind))]; return rows
        r.can('owner','admin','sender'); require(kind!='integrations' or r.role in ('owner','admin'),'Administrator required',403)
        if method=='DELETE':
            require(ident,'Resource ID required'); require(c.execute('DELETE FROM resources WHERE id=? AND tenant_id=? AND kind=?',(ident,tenant,kind)).rowcount,'Resource not found',404); audit(c,tenant,user,kind+'.deleted',ident); return {'ok':True}
        require(method in ('POST','PUT'),'Method not allowed',405); data=b.get('data',b); require(isinstance(data,dict),'Object required')
        if kind in ('recipients','senders'): address(data)
        if kind=='lists': require(data.get('name'),'List name required')
        if kind=='templates': require(data.get('name') and data.get('body'),'Template name and content required')
        if kind=='banks':
            require(r.role in ('owner','admin'),'Administrator required',403)
            require(data.get('company') and data.get('bank_name') and str(data.get('last4','')).isdigit() and len(str(data['last4']))==4,'Company, bank name and last four digits required')
            require(data.get('country','US')=='US','Check mailing is for US companies'); require(not any(k in data for k in ('account_number','routing_number')),'Store a provider token and last four digits only')
            old=c.execute('SELECT data FROM resources WHERE id=? AND tenant_id=? AND kind=?',(ident,tenant,kind)).fetchone() if ident else None; data['status']='pending'
        if kind=='tickets': require(data.get('subject') and data.get('body'),'Subject and message required'); data['status']='open'
        if kind=='integrations':
            require(data.get('name') in ('Zapier','Clio','FileVine','HubSpot','QuickBooks Online','Xero','Google Docs'),'Unknown integration'); data={'name':data['name'],'status':'requested','note':str(data.get('note',''))[:500]}
        ident=ident or uid(); stamp=now()
        if method=='PUT': require(c.execute('UPDATE resources SET data=?,updated=? WHERE id=? AND tenant_id=? AND kind=?',(json.dumps(data),stamp,ident,tenant,kind)).rowcount,'Resource not found',404)
        else: c.execute('INSERT INTO resources VALUES(?,?,?,?,?,?)',(ident,tenant,kind,json.dumps(data),stamp,stamp))
        audit(c,tenant,user,kind+'.saved',ident); return {'id':ident,'data':data}
    if p=='/api/import' and method=='POST':
        r.can('owner','admin','sender'); rows=list(csv.DictReader(io.StringIO(str(b.get('csv',''))))); require(0<len(rows)<=1000,'CSV must contain 1–1000 rows')
        ident=uid(); name=str(b.get('name') or 'Imported list'); stamp=now(); c.execute('INSERT INTO resources VALUES(?,?,?,?,?,?)',(ident,tenant,'lists',json.dumps({'name':name}),stamp,stamp))
        for row in rows:
            d={k:str(row.get(k,'')).strip() for k in ('name','company','street','street2','city','state','postal_code','country')}; d['country']=d['country'] or 'US'; d['custom']={k:row[k] for k in list(row) if k and k.startswith('custom_')}; d['list_ids']=[ident]; address(d); c.execute('INSERT INTO resources VALUES(?,?,?,?,?,?)',(uid(),tenant,'recipients',json.dumps(d),stamp,stamp))
        audit(c,tenant,user,'list.imported',len(rows)); return {'id':ident,'count':len(rows)}
    if p=='/api/export':
        output=io.StringIO(); writer=csv.writer(output); fields=['name','company','street','street2','city','state','postal_code','country']; writer.writerow(fields)
        for row in c.execute("SELECT data FROM resources WHERE tenant_id=? AND kind='recipients'",(tenant,)):
            d=json.loads(row[0]); selected=r.query.get('list',[''])[0]
            if selected and selected not in d.get('list_ids',[]): continue
            writer.writerow([safe_csv(str(d.get(k,''))) for k in fields])
        return (output.getvalue().encode(),'text/csv; charset=utf-8')
    if p=='/api/quote' and method=='POST': return quote(c,tenant,b.get('kind','letter'),b)
    if p=='/api/mail':
        if method=='GET': return [resource(x) for x in c.execute('SELECT * FROM mail WHERE tenant_id=? ORDER BY created DESC LIMIT 1000',(tenant,))]
        r.can('owner','admin','sender'); require(method=='POST','Method not allowed',405); return create_mail(c,tenant,user,b.get('kind','letter'),b,r.env.get('HTTP_IDEMPOTENCY_KEY'))
    if p.startswith('/api/mail/'):
        parts=p.split('/'); ident=parts[3]; row=c.execute('SELECT * FROM mail WHERE id=? AND tenant_id=?',(ident,tenant)).fetchone(); require(row,'Mail not found',404)
        if method=='GET':
            if len(parts)>4 and parts[4]=='print':
                require(row['kind']=='letter' and not json.loads(row['data']).get('document_id'),'Use the uploaded PDF for this order')
                from .printing import letter_pdf
                return (letter_pdf(json.loads(row['data']),cover=True),'application/pdf')
            return resource(row)
        r.can('owner','admin','sender'); require(method=='POST','Method not allowed',405); action=parts[4] if len(parts)>4 else ''
        if action=='pay':
            require(row['status']=='unpaid','Only unpaid orders may be paid',409); quote(c,tenant,row['kind'],json.loads(row['data'])); money(c,tenant,-row['cost'],'Mail payment',ident); status='scheduled' if row['scheduled']>now() else 'queued'
        elif action=='cancel':
            require(row['status'] in ('unpaid','scheduled','queued'),'Order has entered fulfillment; cancellation is unavailable',409)
            if row['status']!='unpaid': money(c,tenant,row['cost'],'Mail cancellation refund',ident)
            status='cancelled'
        else: raise Problem('Unknown action',404)
        c.execute('UPDATE mail SET status=?,updated=? WHERE id=?',(status,now(),ident)); audit(c,tenant,user,'mail.'+action,ident); return {'status':status}
    if p=='/api/billing/checkout' and method=='POST':
        r.can('owner','admin')
        from .payments import checkout
        return checkout(c,tenant,user,b.get('amount_cents'))
    if p=='/api/ledger': return [dict(x) for x in c.execute('SELECT * FROM ledger WHERE tenant_id=? ORDER BY created DESC LIMIT 1000',(tenant,))]
    if p=='/api/team':
        r.can('owner','admin'); return [dict(x) for x in c.execute('SELECT u.id,u.email,u.name,u.active,m.role FROM users u JOIN members m ON u.id=m.user_id WHERE m.tenant_id=?',(tenant,))]
    if p=='/api/team/invite' and method=='POST':
        r.can('owner','admin'); em=email(b.get('email')); role=b.get('role','sender'); require(role in ('admin','sender','viewer'),'Invalid role'); require(r.role=='owner' or role!='admin','Only owners may invite administrators',403)
        t=c.execute('SELECT * FROM tenants WHERE id=?',(tenant,)).fetchone(); count=c.execute('SELECT count(*) FROM members WHERE tenant_id=?',(tenant,)).fetchone()[0]; require(count<PLANS[t['plan']]['users'],'Team limit reached; upgrade plan',409)
        token=secrets.token_urlsafe(32); c.execute('INSERT INTO invitations VALUES(?,?,?,?,?,?)',(uid(),tenant,em,role,digest(token),int(time.time())+604800)); audit(c,tenant,user,'team.invited',em); return {'invitation_token':token,'message':'Share this one-time invitation with the intended existing user.'}
    if p=='/api/team/accept' and method=='POST':
        inv=c.execute('SELECT * FROM invitations WHERE hash=? AND email=? AND expires>?',(digest(str(b.get('token',''))),r.user['email'],int(time.time()))).fetchone(); require(inv,'Invitation is invalid or expired')
        t=c.execute('SELECT plan FROM tenants WHERE id=?',(inv['tenant_id'],)).fetchone(); require(c.execute('SELECT count(*) FROM members WHERE tenant_id=?',(inv['tenant_id'],)).fetchone()[0]<PLANS[t['plan']]['users'],'Team limit reached',409); require(not c.execute('SELECT 1 FROM members WHERE tenant_id=? AND user_id=?',(inv['tenant_id'],user)).fetchone(),'Already a member',409); c.execute('INSERT INTO members VALUES(?,?,?)',(inv['tenant_id'],user,inv['role'])); c.execute('DELETE FROM invitations WHERE id=?',(inv['id'],)); return {'ok':True}
    if p.startswith('/api/team/') and method in ('PUT','DELETE'):
        r.can('owner'); target=p.split('/')[-1]; member=c.execute('SELECT role FROM members WHERE tenant_id=? AND user_id=?',(tenant,target)).fetchone(); require(member and member['role']!='owner','Cannot change the workspace owner',403)
        if method=='DELETE': c.execute('DELETE FROM members WHERE tenant_id=? AND user_id=?',(tenant,target)); c.execute('DELETE FROM api_tokens WHERE tenant_id=? AND user_id=?',(tenant,target)); c.execute('DELETE FROM sessions WHERE tenant_id=? AND user_id=?',(tenant,target))
        else:
            require(b.get('role') in ('admin','sender','viewer'),'Invalid role'); c.execute('UPDATE members SET role=? WHERE tenant_id=? AND user_id=?',(b['role'],tenant,target))
        audit(c,tenant,user,'team.changed',target); return {'ok':True}
    if p=='/api/tokens':
        r.can('owner','admin');
        if method=='GET': return [dict(x) for x in c.execute('SELECT id,name,created FROM api_tokens WHERE tenant_id=?',(tenant,))]
        require(method=='POST','Method not allowed',405); token='pm_'+secrets.token_urlsafe(40); ident=uid(); c.execute('INSERT INTO api_tokens VALUES(?,?,?,?,?,?)',(ident,tenant,user,str(b.get('name','API token'))[:100],digest(token),now()))
        return {'id':ident,'token':token}
    if p.startswith('/api/tokens/') and method=='DELETE':
        r.can('owner','admin'); c.execute('DELETE FROM api_tokens WHERE tenant_id=? AND id=?',(tenant,p.split('/')[-1])); return {'ok':True}
    if p=='/api/audit':
        r.can('owner','admin'); return [dict(x) for x in c.execute('SELECT * FROM audit WHERE tenant_id=? ORDER BY id DESC LIMIT 1000',(tenant,))]
    if p.startswith('/api/admin'):
        r.admin(); return admin(c,r)
    raise Problem('Endpoint not found',404)
def safe_csv(value): return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value

def admin(c,r):
    p=r.path; b=r.body; user=r.user['id']
    if p=='/api/admin/audit' and r.method=='GET': return [dict(x) for x in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 1000')]
    if p=='/api/admin/overview': return {'tenants':[dict(x) for x in c.execute('SELECT * FROM tenants ORDER BY created DESC')],'users':[dict(x) for x in c.execute('SELECT id,email,name,active,superadmin,created FROM users ORDER BY created DESC')],'mail':[resource(x) for x in c.execute('SELECT * FROM mail ORDER BY created DESC LIMIT 1000')],'banks':[resource(x) for x in c.execute("SELECT * FROM resources WHERE kind='banks'")],'tickets':[resource(x) for x in c.execute("SELECT * FROM resources WHERE kind='tickets'")],'readiness':{'smtp':bool(os.environ.get('SMTP_HOST')),'fulfillment':'manual','payments':'stripe' if __import__('app.payments',fromlist=['ready']).ready() else 'manual audited credits','bank_verification':'operator verified provider reference required'}}
    if p.startswith('/api/admin/print/') and r.method=='GET':
        ident=p.split('/')[-1]; row=c.execute('SELECT * FROM mail WHERE id=?',(ident,)).fetchone(); require(row and row['kind']=='letter','Written letter not found',404); require(not json.loads(row['data']).get('document_id'),'Use uploaded source PDF'); from .printing import letter_pdf; audit(c,row['tenant_id'],user,'admin.print_download',ident); return (letter_pdf(json.loads(row['data']),cover=True),'application/pdf')
    if p.startswith('/api/admin/document/') and r.method=='GET':
        ident=p.split('/')[-1]; row=c.execute('SELECT * FROM documents WHERE id=?',(ident,)).fetchone(); require(row,'Document not found',404); path=DATA/'documents'/ident; require(path.exists(),'Document preview expired',410); audit(c,row['tenant_id'],user,'admin.document_access',ident); return (path.read_bytes(),'application/pdf')
    require(r.method=='POST','Method not allowed',405)
    if p=='/api/admin/user-edit':
        target=c.execute('SELECT * FROM users WHERE id=?',(b.get('id'),)).fetchone(); require(target,'User not found',404)
        name=str(b.get('name','')).strip(); require(0<len(name)<=200,'Name must be 1–200 characters')
        em=email(b.get('email')); require(not c.execute('SELECT 1 FROM users WHERE email=? AND id!=?',(em,target['id'])).fetchone(),'Email already registered',409)
        c.execute('UPDATE users SET name=?,email=? WHERE id=?',(name,em,target['id']))
        if em!=target['email']: c.execute('DELETE FROM sessions WHERE user_id=?',(target['id'],))
        audit(c,None,user,'admin.user_edit',target['id']); return {'ok':True}
    if p=='/api/admin/user-role':
        target=c.execute('SELECT * FROM users WHERE id=?',(b.get('id'),)).fetchone(); require(target,'User not found',404)
        require(type(b.get('superadmin'))==bool,'Superadmin must be true or false')
        require(target['id']!=user,'Cannot change your own platform role',409)
        require(target['active'] or not b['superadmin'],'Activate the account before promotion',409)
        c.execute('UPDATE users SET superadmin=? WHERE id=?',(int(b['superadmin']),target['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(target['id'],))
        audit(c,None,user,'admin.user_role',target['id']+' '+str(b['superadmin'])); return {'ok':True}
    if p=='/api/admin/credit':
        amount=b.get('amount_cents'); require(type(amount)==int and 1<=amount<=10000000,'Credit must be 1–10,000,000 cents'); require(b.get('reason'),'Payment reference or credit reason required'); money(c,b.get('tenant_id'),amount,str(b['reason'])); audit(c,b.get('tenant_id'),user,'admin.credit',str(amount)+' '+str(b['reason'])); return {'ok':True}
    if p=='/api/admin/plan':
        require(b.get('plan') in PLANS,'Invalid plan'); count=c.execute('SELECT count(*) FROM members WHERE tenant_id=?',(b.get('tenant_id'),)).fetchone()[0]; require(count<=PLANS[b['plan']]['users'],'Remove extra team members before downgrading'); require(c.execute('UPDATE tenants SET plan=? WHERE id=?',(b['plan'],b.get('tenant_id'))).rowcount,'Workspace not found',404); audit(c,b.get('tenant_id'),user,'admin.plan',b['plan']); return {'ok':True}
    if p=='/api/admin/user':
        require(b.get('id')!=user,'Cannot suspend yourself'); require(type(b.get('active'))==bool,'Active must be true or false'); require(c.execute('UPDATE users SET active=? WHERE id=?',(int(b['active']),b.get('id'))).rowcount,'User not found',404); c.execute('DELETE FROM sessions WHERE user_id=?',(b['id'],)); audit(c,None,user,'admin.user_status',b['id']); return {'ok':True}
    if p=='/api/admin/bank':
        row=c.execute("SELECT * FROM resources WHERE id=? AND kind='banks'",(b.get('id'),)).fetchone(); require(row,'Bank not found',404); require(b.get('status') in ('approved','rejected'),'Invalid status'); require(b.get('verification_reference'),'Verification reference is required'); d=json.loads(row['data']); d.update(status=b['status'],verification_reference=str(b['verification_reference'])); c.execute('UPDATE resources SET data=?,updated=? WHERE id=?',(json.dumps(d),now(),row['id'])); audit(c,row['tenant_id'],user,'admin.bank_verification',row['id']); return {'ok':True}
    if p=='/api/admin/ticket':
        row=c.execute("SELECT * FROM resources WHERE id=? AND kind='tickets'",(b.get('id'),)).fetchone(); require(row,'Ticket not found',404); require(b.get('status') in ('open','resolved'),'Invalid status'); d=json.loads(row['data']); d.update(status=b['status'],reply=str(b.get('reply',''))); c.execute('UPDATE resources SET data=?,updated=? WHERE id=?',(json.dumps(d),now(),row['id'])); audit(c,row['tenant_id'],user,'admin.ticket',row['id']); return {'ok':True}
    if p=='/api/admin/fulfill':
        row=c.execute('SELECT * FROM mail WHERE id=?',(b.get('id'),)).fetchone(); require(row,'Mail not found',404)
        transitions={'queued':['preparing','failed'],'preparing':['on_the_way','failed'],'on_the_way':['tracking_available','delivered','failed'],'tracking_available':['delivered','failed']}; status=b.get('status'); require(status in transitions.get(row['status'],[]),'Invalid fulfillment transition',409)
        require(status not in ('on_the_way','tracking_available','delivered') or b.get('provider_id') or row['provider_id'],'Fulfillment reference required')
        require(status!='tracking_available' or b.get('tracking') or row['tracking'],'Tracking number required'); require(b.get('note'),'Operator evidence or status note required')
        c.execute('UPDATE mail SET status=?,provider_id=?,tracking=?,updated=? WHERE id=?',(status,b.get('provider_id') or row['provider_id'],b.get('tracking') or row['tracking'],now(),row['id'])); audit(c,row['tenant_id'],user,'admin.fulfillment',row['id']+' '+status+' '+str(b['note'])); return {'ok':True}
    if p=='/api/admin/refund':
        row=c.execute('SELECT * FROM mail WHERE id=?',(b.get('id'),)).fetchone(); require(row and row['status']=='failed','Only failed mail may be refunded',409); require(b.get('reason'),'Refund reason required'); money(c,row['tenant_id'],row['cost'],'Failed fulfillment refund: '+str(b['reason']),row['id']); c.execute("UPDATE mail SET status='refunded',updated=? WHERE id=?",(now(),row['id'])); audit(c,row['tenant_id'],user,'admin.refund',row['id']); return {'ok':True}
    raise Problem('Admin action not found',404)

def application(env,start_response):
    headers=[('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),('Referrer-Policy','same-origin'),('Cache-Control','no-store'),('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")]
    status=200; c=None
    try:
        if not env.get('PATH_INFO','/').startswith('/api/'):
            assets={'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css'),'/assets/postmaster-mark.png':('assets/postmaster-mark.png','image/png'),'/assets/postmaster-concept-portrait.png':('assets/postmaster-concept-portrait.png','image/png')}
            path=env.get('PATH_INFO','/')
            require(not path.startswith('/assets/') or path in assets,'Asset not found',404)
            filename,mime=assets.get(path,('index.html','text/html')); payload=(ROOT/filename).read_bytes()
            if path in assets:
                headers=[(k,v) for k,v in headers if k!='Cache-Control']+[('Cache-Control','public, max-age=3600')]
        else:
            r=Request(env); c=connect(); c.execute('BEGIN IMMEDIATE' if r.method!='GET' else 'BEGIN'); result=dispatch(c,r); c.commit(); headers.extend(r.headers)
            if isinstance(result,tuple): payload,mime=result
            else: payload=json.dumps(result).encode(); mime='application/json'
    except Problem as e:
        if c: c.rollback()
        status=e.status; payload=json.dumps({'error':e.message}).encode(); mime='application/json'
    except Exception:
        if c: c.rollback()
        traceback.print_exc(); status=500; payload=b'{"error":"Internal error; contact support"}'; mime='application/json'
    finally:
        if c: c.close()
    labels={200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',409:'Conflict',410:'Gone',413:'Payload Too Large',429:'Too Many Requests',500:'Internal Server Error',503:'Service Unavailable'}
    headers.extend([('Content-Type',mime),('Content-Length',str(len(payload)))]); start_response(str(status)+' '+labels.get(status,'Error'),headers); return [payload]
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['serve','init','admin','promote']); parser.add_argument('--email'); parser.add_argument('--port',type=int,default=8080); args=parser.parse_args(); init()
    if args.command=='promote':
        em=email(args.email)
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            u=c.execute('SELECT id,active,superadmin FROM users WHERE email=?',(em,)).fetchone()
            require(u,'Registered user not found; register the account first',404)
            require(u['active'],'Activate the account before promotion',409)
            if not u['superadmin']:
                c.execute('UPDATE users SET superadmin=1 WHERE id=?',(u['id'],))
                c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
                audit(c,None,u['id'],'admin.cli_promote',em)
            c.commit()
        print('Super administrator verified: '+em)
    if args.command=='admin':
        import getpass
        em=email(args.email); pw=password(getpass.getpass('Administrator password (12+ characters): '))
        with connect() as c:
            c.execute('BEGIN IMMEDIATE'); u=c.execute('SELECT id FROM users WHERE email=?',(em,)).fetchone()
            if u: c.execute('UPDATE users SET superadmin=1,password=? WHERE id=?',(pw,u['id']))
            else:
                user,tenant=uid(),uid(); c.execute('INSERT INTO users(id,email,name,password,superadmin,created) VALUES(?,?,?,?,1,?)',(user,em,'Administrator',pw,now())); c.execute('INSERT INTO tenants(id,name,plan,created) VALUES(?,?,?,?)',(tenant,'Administration','enterprise',now())); c.execute('INSERT INTO members VALUES(?,?,?)',(tenant,user,'owner'))
            c.commit()
        print('Administrator ready.')
    if args.command=='serve':
        with make_server('127.0.0.1',args.port,application) as httpd: print('Postmaster on http://127.0.0.1:'+str(args.port)); httpd.serve_forever()
if __name__=='__main__': main()
