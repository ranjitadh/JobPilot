"""Optional user-operated Playwright helper. Never submits or clicks any button.
Run from project root: python scripts/form_assist.py JOB_ID --host example.com --permission-confirmed
Only use where the site's terms permit it. Login/CAPTCHA and sensitive fields stop filling.
"""
import argparse, json, os, sys
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core import init, ROOT, data_dir, stamp, digest, db, date, now, audit
from app.applications import snapshot

def map_fields(fields, profile):
    aliases={'name':['full name','name','your name'],'email':['email','email address'],'portfolio':['portfolio','portfolio url','website'],'github':['github','github url'],'linkedin':['linkedin','linkedin url'],'location':['location','city']}
    mapped=[]; missing=[]
    for f in fields:
        label=' '.join(f.get('label','').lower().strip().rstrip('*:').split()); kind=f.get('type','text')
        if kind in ['hidden','submit','button','reset']: continue
        key=next((k for k,vs in aliases.items() if label in vs),None)
        if kind in ['text','email','url','textarea'] and key:
            mapped.append({'index':f['index'],'label':label,'value':profile[key]})
        elif f.get('required') or kind in ['password','file','checkbox','radio','select']:
            missing.append({'label':label,'type':kind,'reason':'Manual completion required'})
    return mapped,missing

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('job_id'); parser.add_argument('--host',required=True); parser.add_argument('--permission-confirmed',action='store_true'); a=parser.parse_args()
    if not a.permission_confirmed: raise SystemExit('Confirm that this specific site permits form assistance first.')
    init(); s=snapshot(a.job_id)
    if s['missing']: raise SystemExit('Complete the packet review first: '+str(s['missing']))
    target=s['recipient']; host=urlsplit(target).hostname
    if host!=a.host: raise SystemExit('Exact allowed host must match packet destination')
    if any(host==d or host.endswith('.'+d) for d in ['linkedin.com','upwork.com','wellfound.com','google.com']): raise SystemExit('This host uses manual completion in this MVP.')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=False); context=browser.new_context()
        # Block all writes during inspection and filling, including autosave requests.
        context.route('**/*',lambda route: route.continue_() if route.request.method in ['GET','HEAD','OPTIONS'] else route.abort())
        page=context.new_page(); page.goto(target,wait_until='domcontentloaded',timeout=30000)
        if urlsplit(page.url).hostname!=host: raise SystemExit('Redirected host; review the destination manually. No fields filled.')
        # Fail closed around sign-in, CAPTCHA, payment, and sensitive identity fields.
        if page.locator('input[type=password],iframe[src*="captcha"],iframe[src*="challenge"],[class*="captcha"],[id*="captcha"]').count(): raise SystemExit('Login/CAPTCHA detected. Complete manually. No fields filled.')
        fields=page.locator('input,textarea,select').evaluate_all('''els=>els.map((e,index)=>({index,type:e.tagName==='SELECT'?'select':e.type,label:e.labels?.[0]?.innerText||e.getAttribute('aria-label')||e.name,required:e.required}))''')
        mapped,missing=map_fields(fields,s['profile_fields'])
        if any(any(word in f.get('label','').lower() for word in ['passport','social security','bank','credit card','national id','date of birth','gender','ethnicity','disability']) for f in fields): raise SystemExit('Sensitive fields detected. Manual completion required. No fields filled.')
        print(json.dumps({'employer':s['employer'],'title':s['title'],'destination':target,'will_fill':mapped,'manual_fields':missing,'cv':s['documents']['resume']['file']},indent=2))
        if input('Type FILL to place these values in this form (nothing is submitted): ')!='FILL': return
        controls=page.locator('input,textarea,select')
        for f in mapped: controls.nth(f['index']).fill(f['value'])
        for f in fields:
            label=f.get('label','').lower()
            if f['type']=='file' and ('resume' in label or 'cv'==label.strip()):
                controls.nth(f['index']).set_input_files(str(ROOT/'resumes'/s['documents']['resume']['file']))
            elif f['type']=='textarea' and 'cover letter' in label:
                controls.nth(f['index']).fill(s['documents']['cover_letter'])
        report={'job_id':a.job_id,'at':stamp(),'mapped_fields':[x['label'] for x in mapped],'manual_fields':missing,'status':'filled_only_not_submitted'}
        (data_dir()/f'form-progress-{a.job_id}.json').write_text(json.dumps(report,indent=2))
        with db() as c: audit(c,'form_filled_no_submission',a.job_id)
        print('Progress saved. Unknown fields need manual completion. Outbound writes remain blocked.')
        input('Review the visible form, then press Enter here to close. Submit manually in your normal browser after approving the packet. ')
        browser.close()
if __name__=='__main__': main()
