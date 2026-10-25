"""Release scheduled orders; expire document previews. Never invent postal events."""
from datetime import datetime,timezone,timedelta
from .core import *
def run():
    init()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        count=c.execute("UPDATE mail SET status='queued',updated=? WHERE status='scheduled' AND scheduled<=?",(now(),now())).rowcount
        c.execute('DELETE FROM sessions WHERE expires<?',(int(time.time()),)); c.execute('DELETE FROM resets WHERE expires<?',(int(time.time()),)); c.execute('DELETE FROM invitations WHERE expires<?',(int(time.time()),))
        for d in c.execute('SELECT d.*,t.retention FROM documents d JOIN tenants t ON t.id=d.tenant_id'):
            if datetime.fromisoformat(d['created'])+timedelta(days=d['retention'])<datetime.now(timezone.utc):
                active=c.execute("SELECT 1 FROM mail WHERE tenant_id=? AND status NOT IN ('delivered','cancelled','failed','refunded') AND json_extract(data,'$.document_id')=?",(d['tenant_id'],d['id'])).fetchone()
                if not active: (DATA/'documents'/d['id']).unlink(missing_ok=True)
        c.commit()
        print(json.dumps({'released':count,'time':now()}))
if __name__=='__main__': run()
