import argparse,json,secrets
from .core import init,db,ingest,stamp,ROOT,audit
from .feeds import discover
from .notifications import notify
p=argparse.ArgumentParser(); p.add_argument('command',choices=['init','discover','notify','import','history','token']); p.add_argument('file',nargs='?'); a=p.parse_args()
if a.command=='token': print(secrets.token_urlsafe(32)); raise SystemExit
init()
if a.command=='discover': print(json.dumps(discover(),indent=2))
elif a.command=='notify': print(json.dumps(notify(),indent=2))
elif a.command=='import':
    from .main import Listing
    for j in json.loads(open(a.file).read()): print(ingest(Listing(**j).model_dump(exclude_none=True)))
elif a.command=='history':
    for title,company,url,receipt in [
       ('Generic Application','Periwin Solutions','https://www.periwin.com/careers/generic-application','Prior application log: confirmation email received 2026-10-07, no-reply@periwin.com; Thank You for Your Application'),
       ('React Frontend Developer','Envision Tech','https://envisiontechpvt.com/career/','Prior application log: confirmation email received 2026-10-07, envisiontechpvt@gmail.com; Application Received — EnvisionTech')]:
        jid,_=ingest({'title':title,'company':company,'url':url,'source':'manual','description':'Historical application imported from Nepal_Application_Review.md; do not reapply.'})
        with db() as c:
            c.execute('INSERT OR IGNORE INTO receipts VALUES(?,?,?,?)',(jid,receipt,'2026-10-07T06:23:28+00:00' if company=='Periwin Solutions' else '2026-10-07T06:46:07+00:00','imported prior verified log; not reverified in this app'))
            c.execute("UPDATE jobs SET status='applied' WHERE id=?",(jid,)); audit(c,'prior_application_imported',jid)
    print('Two prior applications imported. No applications sent.')
else: print('Database initialized.')
