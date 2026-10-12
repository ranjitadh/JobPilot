import os, json
import httpx
from .core import db, stamp, audit, all_jobs

def notify():
    if os.getenv('TELEGRAM_ENABLED','false').lower()!='true': return {'sent':0,'disabled':True}
    token=os.getenv('TELEGRAM_BOT_TOKEN'); chat=os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat: raise ValueError('Telegram credentials missing')
    sent=0
    for item in all_jobs():
        s=item['score']; j=item['job']; jid=item['id']
        if not s['shortlisted'] or s['total']<85 or item['status'] not in ['new','saved','prepared']: continue
        with db() as c:
            # At-most-once attempts. A timeout has uncertain delivery: never blindly retry.
            inserted=c.execute("INSERT OR IGNORE INTO alerts VALUES(?,'attempting',?)",(jid,stamp())).rowcount
        if not inserted: continue
        comp=j.get('compensation') or {}; budget=comp.get('text') or (f"{comp.get('minimum')} {comp.get('currency')} / {comp.get('period')}" if comp.get('minimum') is not None else 'Unknown')
        message=f"{j['title']} — {j.get('company','Unknown')}\n{s['total']}/100 • {s['completeness']}% evidence\nAge: {str(s['age_hours'])+' hours' if s['age_hours'] is not None else 'Unknown'}\nCompensation: {budget}\nConnects: {j.get('connects','Unknown')}\nMatch: {', '.join(s['matching_skills'])}\nConcerns: {'; '.join(s['concerns']) or 'None detected; verify listing'}\n{j['url']}"
        try:
            response=httpx.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat,'text':message[:4000],'disable_web_page_preview':True},timeout=15,follow_redirects=False)
            response.raise_for_status()
            if response.json().get('ok') is not True: raise ValueError('Not confirmed')
            state='sent'; sent+=1
        except Exception: state='delivery_uncertain_or_failed'
        with db() as c:
            c.execute('UPDATE alerts SET state=? WHERE job_id=?',(state,jid)); audit(c,'telegram_'+state,jid)
    return {'sent':sent,'note':'Uncertain attempts are not automatically resent; inspect audit log.'}
