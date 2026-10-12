from __future__ import annotations
import hashlib, html, json, os, re, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
os.umask(0o077)

def now(): return datetime.now(timezone.utc)
def stamp(): return now().isoformat()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def config(name): return json.loads((ROOT/'config'/f'{name}.json').read_text())
def data_dir():
    p=Path(os.environ.get('JOBPILOT_DATA',str(ROOT/'data'))).resolve(); p.mkdir(parents=True,exist_ok=True); return p
@contextmanager
def db():
    c=sqlite3.connect(data_dir()/'jobpilot.sqlite3',timeout=30)
    c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
    try:
        yield c; c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()
def init():
    with db() as c: c.executescript((ROOT/'app/schema.sql').read_text())
def audit(c,event,jid=None,details=''):
    c.execute('INSERT INTO audit(event,job_id,details,created) VALUES(?,?,?,?)',(event,jid,details,stamp()))
def text(v): return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',str(v or '')))).strip()
def url(v):
    p=urlsplit(v)
    if p.scheme!='https' or not p.hostname or p.username or p.password: raise ValueError('An HTTPS job URL without credentials is required')
    return urlunsplit(('https',p.netloc.lower(),p.path.rstrip('/') or '/',urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith(('utm_','ref')) and k not in ['source','fbclid','gclid'])),''))
def date(v):
    if v is None or v=='': return None
    try:
        if isinstance(v,(int,float)): return datetime.fromtimestamp(v/1000 if v>1e11 else v,timezone.utc)
        d=datetime.fromisoformat(str(v).replace('Z','+00:00')); return d.replace(tzinfo=d.tzinfo or timezone.utc)
    except (ValueError,OverflowError,OSError): return None
ALIASES={'React':['react','react.js','reactjs'], 'Next.js':['next.js','nextjs','next js'], 'REST APIs':['rest api','restful','rest apis'], 'Tailwind CSS':['tailwind','tailwind css'], 'Django REST Framework':['django rest framework','drf']}
ALL_SKILLS=['React','Next.js','TypeScript','JavaScript','Tailwind CSS','Python','Django','Django REST Framework','REST APIs','PostgreSQL','Supabase','Firebase','React Native','Expo','Java','Ruby','Go','Rust','C++','Angular','Vue','PHP','Kotlin','Swift','C#','AWS']
def skills_in(s):
    s=s.lower()
    return [k for k in ALL_SKILLS if any(re.search(r'(?<!\w)'+re.escape(a)+r'(?!\w)',s) for a in ALIASES.get(k,[k.lower()]))]

def score(j, rules=None, profile=None, clock=None):
    r=rules or config('rules'); p=profile or config('profile'); clock=clock or now()
    content=text(j.get('description')); combined=j['title']+' '+content
    found=j.get('required_skills') or skills_in(combined); matching=[s for s in found if s.lower() in [x.lower() for x in p['skills']]]
    parts=[]; concerns=[]; rejects=[]
    def add(name,weight,fraction,evidence):
        parts.append({'name':name,'weight':weight,'earned':round(weight*fraction,2) if fraction is not None else None,'evidence':evidence})
    add('Skills',24,len(matching)/len(found) if found else None,', '.join(matching) if matching else 'No matching skill evidence')
    yrs=j.get('minimum_years')
    if yrs is None:
        m=re.search(r'(\d+)\+?\s+years?\s+(?:of\s+)?(?:professional\s+)?experience',combined,re.I)
        yrs=int(m.group(1)) if m else None
    add('Experience',6,min(1,p['years_experience']/max(1,yrs)) if yrs is not None else None,f'{yrs} years required; profile: {p["years_experience"]}' if yrs is not None else 'Not specified')
    senior_review=r.get('senior_roles_require_review',True) and bool(re.search(r'\b(senior|sr\.?|staff|principal|lead|director|head of)\b',j['title'],re.I)) and (yrs is None or yrs>p['years_experience'])
    if senior_review: concerns.append('Senior/lead title needs manual experience review')
    if yrs and yrs>p['years_experience']+1: concerns.append('Experience requirement exceeds profile')
    eligibility=j.get('eligibility','unknown')
    location=j.get('location','')
    if eligibility=='unknown':
        if re.search(r'\b(no|excluding|except)\s+nepal\b',combined,re.I): eligibility='ineligible'
        elif location.strip().lower() in ['worldwide','anywhere','global','nepal','lalitpur, nepal','kathmandu, nepal']: eligibility='eligible'
        elif re.search(r'\b(us|usa|united states|uk|united kingdom|europe|eu|canada|australia)[ -]only\b',location+' '+combined,re.I): eligibility='ineligible'
    if re.search(r'\b(?:excluding|except|not open to|no applicants from)\s+nepal\b',combined,re.I): eligibility='ineligible'
    if re.search(r'\b(?:must (?:be based|reside|live)|residents?) (?:in|of) (?:the )?(?:united states|usa|uk|united kingdom|canada|australia)\b',combined,re.I): eligibility='ineligible'
    if j.get('authorization_unavailable') is True: eligibility='ineligible'
    if eligibility=='ineligible': rejects.append('Location/work authorization excludes applicant')
    if eligibility=='unknown': concerns.append('Nepal eligibility requires confirmation')
    if j.get('timezone_restrictions'): concerns.append('Employer timezone/working hours require manual review')
    add('Eligibility',20,1 if eligibility=='eligible' else 0 if eligibility=='ineligible' else None,location or eligibility)
    posted=date(j.get('posted_at')); age=(clock-posted).total_seconds()/3600 if posted else None
    if age is not None and age<0: age=None; concerns.append('Future posting date: freshness unknown')
    add('Freshness',15,(1 if age<=24 else .7 if age<=72 else .4 if age<=168 else .1) if age is not None else None,j.get('posted_at') or 'Posting date unknown')
    if age is not None and age>r['max_age_days']*24:
        (rejects if r['hard_age_limit'] else concerns).append('Older than preferred maximum')
    expires=date(j.get('expires_at'))
    if expires and expires<=clock: rejects.append('Listing expired')
    comp=j.get('compensation') or {}; amount=comp.get('minimum'); period=comp.get('period'); floor=r.get({'hourly':'hourly_usd_floor','annual':'annual_usd_floor','fixed':'fixed_usd_floor'}.get(period,''))
    fraction=None
    if isinstance(amount,(float,int)) and comp.get('currency')=='USD' and floor:
        fraction=min(1,amount/floor)
        if amount<floor: concerns.append('Compensation below configured USD floor')
    unpaid=j.get('unpaid') is True or bool(re.search(r'\b(unpaid|uncompensated|pay to apply)\b',combined,re.I))
    if unpaid:
        fraction=0; (rejects if r['reject_unpaid'] else concerns).append('Unpaid work or application payment requested')
    add('Compensation',15,fraction,comp.get('text') or (f'{amount} {comp.get("currency")} / {period}' if amount is not None else 'Unknown'))
    verified=j.get('payment_verified'); credible=j.get('credibility_verified')
    cred=verified if j.get('source')=='upwork' else credible
    add('Credibility',10,float(cred) if cred is not None else None,j.get('credibility_evidence') or ('Payment verified' if verified is True else 'Unverified payment' if verified is False else 'No verified credibility evidence'))
    connects=j.get('connects'); proposals=j.get('proposals')
    add('Application cost',5,(1 if connects<=r['max_connects'] else .2) if connects is not None else None,str(connects)+' Connects' if connects is not None else 'Unknown')
    add('Competition',5,(1 if proposals<5 else .5 if proposals<20 else .1) if proposals is not None else None,str(proposals)+' proposals' if proposals is not None else 'Unknown')
    if connects is not None and connects>r['max_connects']: (rejects if r['hard_connect_limit'] else concerns).append('Connect cost exceeds preference')
    if not matching: rejects.append('No matching technical skills detected')
    if len(content)<100: concerns.append('Short/vague description: review scope')
    if re.search(r'\b(telegram only|deposit required|buy equipment|guaranteed income)\b',combined,re.I): concerns.append('Suspicious wording: verify employer independently')
    denominator=sum(x['weight'] for x in parts if x['earned'] is not None); earned=sum(x['earned'] or 0 for x in parts)
    total=round(100*earned/denominator,1) if denominator else 0
    category='High priority' if total>=85 else 'Worth reviewing' if total>=70 else 'Low priority' if total>=50 else 'Skip'
    shortlist=not senior_review and not rejects and total>=r['minimum_score'] and denominator>=r['minimum_completeness'] and (eligibility=='eligible' or not r['require_confirmed_eligibility']) and not j.get('timezone_restrictions')
    return dict(total=total,earned=round(earned,2),completeness=denominator,parts=parts,concerns=concerns,rejections=rejects,category='Skip' if rejects else category,shortlisted=shortlist,eligibility=eligibility,age_hours=round(age,1) if age is not None else None,matching_skills=matching,missing=[x['name'] for x in parts if x['earned'] is None])

def ingest(j):
    canonical=url(j['url']); j['url']=canonical
    fingerprint=digest([re.sub(r'[^a-z0-9]+',' ',text(j['title']).lower()).strip(),re.sub(r'[^a-z0-9]+',' ',text(j.get('company')).lower()).strip()])
    h=digest(j)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM jobs WHERE canonical=?',(canonical,)).fetchone()
        if row:
            if row['content_hash']==h: return row['id'],'unchanged'
            c.execute('UPDATE jobs SET payload=?,content_hash=?,updated=? WHERE id=?',(json.dumps(j),h,stamp(),row['id']))
            c.execute('DELETE FROM documents WHERE job_id=?',(row['id'],)); c.execute('DELETE FROM approvals WHERE job_id=?',(row['id'],))
            audit(c,'listing_updated',row['id']); return row['id'],'updated'
        # Conservative exact normalized title+company duplicate collapse; no fuzzy auto merges.
        dup=c.execute('SELECT id FROM jobs WHERE fingerprint=?',(fingerprint,)).fetchone() if j.get('company') else None
        if dup:
            audit(c,'duplicate_listing',dup['id'],canonical); return dup['id'],'duplicate'
        jid=digest(canonical)[:20]
        c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(jid,canonical,fingerprint,json.dumps(j),h,stamp(),stamp(),'new'))
        audit(c,'job_discovered',jid,j.get('source','manual')); return jid,'created'

def job(jid):
    with db() as c: row=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
    if not row: raise ValueError('Job not found')
    out=dict(row); out['job']=json.loads(out.pop('payload')); out['score']=score(out['job'])
    return out

def all_jobs():
    with db() as c: ids=[r[0] for r in c.execute('SELECT id FROM jobs ORDER BY discovered DESC')]
    return [job(i) for i in ids]
