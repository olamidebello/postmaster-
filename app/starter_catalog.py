"""Suggested operator service prices, independent of postal/vendor rates."""
from .core import now,audit
PRODUCTS=(
 ('letter-formatting','Letter formatting','Document preparation',999,'Format one customer-supplied letter of up to 5 pages into a print-ready PDF. One revision. Operator-delivered service; printing and postage are separate.'),
 ('pdf-preflight','PDF print-readiness review','Document preparation',1499,'Review one PDF of up to 25 pages for margins, page size and visible layout issues; provide a correction checklist. Operator review only; no legal or compliance certification. Printing and postage are separate.'),
 ('letterhead-design','Custom letterhead layout','Design services',2999,'Create one letterhead layout using your supplied logo and contact details; deliver PDF artwork with one revision. Logo creation, printing and postage are separate.'),
 ('postcard-design','Two-sided postcard design','Design services',4999,'Design one two-sided postcard using customer-supplied text and images; deliver print-ready PDF artwork with one revision. Printing, address lists and postage are separate.'),
 ('csv-cleanup','Mailing-list cleanup — 500 rows','Mailing preparation',1999,'Clean one CSV of up to 500 rows: normalize supplied fields, remove exact duplicates and report missing fields. No purchased contacts, postal address validation or deliverability guarantee.'),
 ('merge-setup','Mail-merge template setup','Mailing preparation',2499,'Set up one reusable letter template with up to 5 merge fields and review a sample using your supplied records. No bulk mailing, printing or postage included.'),
 ('campaign-setup','Campaign setup — 1,000 recipients','Campaign services',7999,'Prepare one mailing campaign from a supplied document and up to 1,000 customer-provided recipient records, including a sample preview for approval. Printing, postage and list acquisition are separate; orders require operator fulfillment.'),
 ('api-onboarding','Developer API onboarding session','Setup services',9999,'One remote onboarding session of up to 60 minutes for the documented Postmaster API, with one sample request and token setup guidance. Custom integration development and third-party subscriptions are separate.'),
)
def seed(c,user=None):
    added=0;stamp=now()
    for slug,name,category,price,description in PRODUCTS:
        added+=c.execute('INSERT OR IGNORE INTO marketplace_products(id,name,description,category,price,active,created,updated) VALUES(?,?,?,?,?,1,?,?)',('starter-'+slug,name,description,category,price,stamp,stamp)).rowcount
    if added:audit(c,None,user,'marketplace.starter_seed',str(added)+' starter services added; suggested USD prices')
    return {'added':added,'preserved':len(PRODUCTS)-added}
def main():
    import json
    from .core import init,connect
    init()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');result=seed(c);c.commit()
    print(json.dumps(result))
if __name__=='__main__':main()
