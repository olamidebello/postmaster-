"""Protected, atomic runtime provider configuration; never return secret values."""
import fcntl, json, os, tempfile
from .core import DATA, require
FIELDS={'SMTP_HOST','SMTP_PORT','SMTP_FROM','SMTP_USER','SMTP_PASSWORD','STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET'}
def saved():
    path=DATA/'provider-credentials.json'
    if not path.exists(): return {}
    return json.loads(path.read_text())
def get(key,default=''):
    return saved().get(key,os.environ.get(key,default))
def statuses():
    values=saved()
    return [{'key':k,'configured':bool(values.get(k,os.environ.get(k,''))),'source':'GUI' if k in values else 'environment'} for k in sorted(FIELDS)]
def update(key,value):
    require(key in FIELDS,'Unsupported provider setting')
    require(isinstance(value,str) and len(value)<=4096 and not any(x in value for x in ('\n','\r','\x00')),'Invalid setting value')
    if key=='SMTP_PORT' and value: require(value.isdigit() and 1<=int(value)<=65535,'Invalid SMTP port')
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=os.open(DATA/'provider-credentials.lock',os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(lock,'w') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        values=saved(); values[key]=value
        fd,name=tempfile.mkstemp(prefix='.provider-',dir=DATA)
        try:
            with os.fdopen(fd,'w') as out:
                json.dump(values,out);out.flush();os.fsync(out.fileno())
            os.replace(name,DATA/'provider-credentials.json')
        finally:
            if os.path.exists(name):os.unlink(name)
