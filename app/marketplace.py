"""Operator-managed services catalog and atomic wallet purchases."""
from .core import *
def catalog(c,admin=False):
    return [dict(x) for x in c.execute('SELECT * FROM marketplace_products'+('' if admin else ' WHERE active=1')+' ORDER BY created DESC')]
def orders(c,tenant=None):
    return [dict(x) for x in c.execute('SELECT * FROM marketplace_orders'+(' WHERE tenant_id=?' if tenant else '')+' ORDER BY created DESC LIMIT 1000',(tenant,) if tenant else ())]
def save(c,user,b):
    name=str(b.get('name','')).strip();description=str(b.get('description','')).strip();category=str(b.get('category','Services')).strip();price=b.get('price_cents');active=b.get('active')
    require(0<len(name)<=150 and len(description)<=4000 and 0<len(category)<=80,'Invalid product details')
    require(type(price)==int and 1<=price<=1000000,'Price must be 1–1,000,000 cents');require(type(active)==bool,'Active must be true or false')
    ident=b.get('id') or uid();stamp=now()
    if b.get('id'):
        require(c.execute('UPDATE marketplace_products SET name=?,description=?,category=?,price=?,active=?,updated=? WHERE id=?',(name,description,category,price,int(active),stamp,ident)).rowcount,'Product not found',404)
    else:c.execute('INSERT INTO marketplace_products VALUES(?,?,?,?,?,?,?,?)',(ident,name,description,category,price,int(active),stamp,stamp))
    audit(c,None,user,'marketplace.product_saved',ident);return {'id':ident}
def purchase(c,tenant,user,b):
    key=b.get('request_key');qty=b.get('quantity');require(isinstance(key,str) and 8<=len(key)<=100,'Purchase request key required')
    require(type(qty)==int and 1<=qty<=100,'Quantity must be 1–100')
    old=c.execute('SELECT * FROM marketplace_orders WHERE tenant_id=? AND request_key=?',(tenant,key)).fetchone()
    if old:
        require(old['product_id']==b.get('product_id') and old['quantity']==qty,'Request key already used for another purchase',409);return dict(old)
    product=c.execute('SELECT * FROM marketplace_products WHERE id=? AND active=1',(b.get('product_id'),)).fetchone();require(product,'Product unavailable',404)
    require(type(b.get('unit_price_cents'))==int and b['unit_price_cents']==product['price'],'Price changed; refresh and review',409)
    total=product['price']*qty;ident=uid();stamp=now();money(c,tenant,-total,'Marketplace purchase: '+product['name'])
    c.execute('INSERT INTO marketplace_orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ident,tenant,user,product['id'],product['name'],qty,total,'paid','',key,stamp,stamp))
    audit(c,tenant,user,'marketplace.purchased',ident);return dict(c.execute('SELECT * FROM marketplace_orders WHERE id=?',(ident,)).fetchone())
def update_order(c,user,b):
    row=c.execute('SELECT * FROM marketplace_orders WHERE id=?',(b.get('id'),)).fetchone();require(row,'Order not found',404)
    status=b.get('status');note=str(b.get('note','')).strip();require(0<len(note)<=2000,'Operator note required')
    if row['status']==status:return {'ok':True}
    require(status in {'paid':('processing','refunded'),'processing':('completed','refunded')}.get(row['status'],()),'Invalid order transition',409)
    if status=='refunded':money(c,row['tenant_id'],row['total'],'Marketplace refund: '+row['id'])
    c.execute('UPDATE marketplace_orders SET status=?,note=?,updated=? WHERE id=?',(status,note,now(),row['id']));audit(c,row['tenant_id'],user,'marketplace.'+status,row['id']);return {'ok':True}
