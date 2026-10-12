import sys
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from app import core,applications as ap
from app.core import score,ingest,db,job,digest
from app.main import app,TOKEN
from app.feeds import normalize_himalayas,fetch
@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('JOBPILOT_DATA',str(tmp_path));monkeypatch.setenv('LLM_ENABLED','false');monkeypatch.setenv('TELEGRAM_ENABLED','false');core.init()
@pytest.fixture
def listing():
    return dict(title='React and Next.js Developer',company='Fixture Company',url='https://example.org/jobs/1',source='upwork',description='Build React and Next.js frontend applications with TypeScript. Integrate REST APIs and test responsive web interfaces with our team. Requires 2 years of experience.',location='Worldwide',posted_at=core.stamp(),connects=8,proposals=3,payment_verified=True,compensation={'minimum':20,'currency':'USD','period':'hourly'})
@pytest.fixture
def client():
    with TestClient(app,headers={'Authorization':'Bearer '+TOKEN}) as c:yield c

def test_missing_is_unknown():
    s=score({'title':'React Developer','description':'Build React interfaces'});assert s['completeness']==24 and s['total']==100 and not s['shortlisted'];assert len(s['missing'])==7

def test_normalized_score_and_rejection(listing):
    s=score(listing);assert s['total']==100 and s['completeness']==100 and s['shortlisted']
    listing['location']='US only';assert score(listing)['rejections'] and not score(listing)['shortlisted']

def test_connect_preference_not_hard(listing):
    listing['connects']=16;assert not score(listing)['rejections'];r=core.config('rules');r['hard_connect_limit']=True;assert score(listing,r)['rejections']

def test_unpaid_expired_future_currency(listing):
    listing['unpaid']=True;assert not score(listing)['shortlisted'];listing.pop('unpaid')
    listing['expires_at']=(core.now()-timedelta(days=1)).isoformat();assert not score(listing)['shortlisted'];listing.pop('expires_at')
    listing['posted_at']=(core.now()+timedelta(days=2)).isoformat();assert score(listing)['age_hours'] is None
    listing['compensation']['currency']='NPR';assert 'Compensation' in score(listing)['missing']

def test_dedup_and_update(listing):
    a,_=ingest(listing);listing['url']+='?utm_source=test';assert ingest(listing)==(a,'unchanged')
    listing['description']+=' Additional task.';assert ingest(listing)==(a,'updated')
    listing['url']='https://another.example/job';assert ingest(listing)==(a,'duplicate')

def test_himalayas_formats():
    base={'title':'React','applicationLink':'https://himalayas.app/jobs/x','locationRestrictions':[{'alpha2':'NP','name':'Nepal'}],'pubDate':1760000000000}
    j=normalize_himalayas(base);assert j['eligibility']=='eligible' and '2025' in j['posted_at']
    base['locationRestrictions']=[];assert normalize_himalayas(base)['eligibility']=='eligible'
    del base['locationRestrictions'];assert normalize_himalayas(base)['eligibility']=='unknown'
    base['locationRestrictions']=[{'alpha2':'US'}];assert normalize_himalayas(base)['eligibility']=='ineligible'

def test_cache_unknown_screening(listing):
    listing['screening_questions']=['Expected salary?'];jid,_=ingest(listing);a=ap.prepare(jid);assert a==ap.prepare(jid);assert a['screening_answers'][0]['answer'] is None
    assert 'approximately 4 years' in a['cover_letter']
    with db() as c:assert c.execute('SELECT COUNT(*) FROM usage').fetchone()[0]==0

def test_skip_prevents_generation(listing):
    listing['eligibility']='ineligible';jid,_=ingest(listing)
    with pytest.raises(ValueError):ap.prepare(jid)

def reviewed(listing):
    jid,_=ingest(listing);ap.prepare(jid);ap.save_review(jid,{});return jid

def test_approval_and_receipt(listing):
    jid=reviewed(listing);s=ap.snapshot(jid);assert not s['missing']
    with pytest.raises(ValueError):ap.approve(jid,'stale')
    a=ap.approve(jid,digest(s));assert a['submitted'] is False
    with pytest.raises(ValueError):ap.receipt(jid,a['approval_id'],'')
    assert ap.receipt(jid,a['approval_id'],'Application received — fixture receipt ABC123')['status']=='applied'
    with pytest.raises(ValueError):ap.receipt(jid,a['approval_id'],'Application received — duplicate')
    with pytest.raises(ValueError):ap.prepare(jid)

def test_edit_and_listing_invalidation(listing):
    jid=reviewed(listing);a=ap.approve(jid,digest(ap.snapshot(jid)));ap.save_review(jid,{'cover_letter':'Updated truthful cover letter.'})
    with pytest.raises(ValueError):ap.receipt(jid,a['approval_id'],'Application received — example')
    listing['description']+=' Changed requirements';ingest(listing)
    with pytest.raises(ValueError):ap.documents(jid)

def test_auth_csrf_validation(client,listing):
    assert client.get('/api/jobs',headers={'Authorization':'invalid'}).status_code==401
    assert client.post('/api/jobs',json=listing,headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/jobs',json=dict(listing,url='javascript:alert(1)')).status_code==400
    assert client.post('/api/jobs',json=dict(listing,connects=-1)).status_code==422
    assert client.get('/api/resumes/.env').status_code==404
    assert client.get('/',headers={'Host':'evil.example'}).status_code==403

def test_api_end_to_end(client,listing):
    r=client.post('/api/jobs',json=listing);assert r.status_code==200;jid=r.json()['id']
    assert client.get('/api/jobs?q=React').json()['total']==1
    assert client.post(f'/api/jobs/{jid}/status',json={'status':'applied'}).status_code==400
    assert client.post(f'/api/jobs/{jid}/prepare',json={}).status_code==200
    assert client.get(f'/api/jobs/{jid}/cover-letter').status_code==200
    assert client.post(f'/api/jobs/{jid}/review',json={}).status_code==200
    packet=client.get(f'/api/jobs/{jid}/packet').json()
    assert client.post(f'/api/jobs/{jid}/approve',json={'snapshot_hash':packet['hash']}).status_code==400
    a=client.post(f'/api/jobs/{jid}/approve',json={'snapshot_hash':packet['hash'],'explicit_approval':True}).json()
    assert client.post(f'/api/jobs/{jid}/receipt',json={'approval_id':a['approval_id'],'evidence':'Employer confirms application received ID 123'}).status_code==200
    assert client.get('/api/stats').json()['applied_today']==1

def test_feed_cooldown_etag(monkeypatch):
    calls=[]
    class Reply:
        status_code=200;headers={'etag':'etag-1'};content=b'{}'
        def raise_for_status(self):pass
        def json(self):return {'jobs':[]}
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,*args,**kw):calls.append(kw);return Reply()
    monkeypatch.setattr('app.feeds.httpx.Client',Client)
    assert fetch('test','https://example.org',100)=={'jobs':[]};assert fetch('test','https://example.org',100) is None;assert len(calls)==1
    with db() as c:c.execute('UPDATE feeds SET next_fetch=0')
    fetch('test','https://example.org',100);assert calls[1]['headers']['If-None-Match']=='etag-1'

def test_atomic_budget_failed_reservation(monkeypatch,listing):
    for k,v in dict(LLM_ENABLED='true',LLM_BASE_URL='https://example.org/v1',LLM_MODEL='fixture',LLM_API_KEY='fake',LLM_INPUT_USD_PER_MILLION='1',LLM_OUTPUT_USD_PER_MILLION='1',AI_DAILY_REQUESTS='1',AI_DAILY_USD='1').items():monkeypatch.setenv(k,v)
    calls=[]
    def fail(*a,**k):calls.append(1);raise RuntimeError('No network test')
    monkeypatch.setattr('app.applications.httpx.post',fail);jid,_=ingest(listing);j=job(jid);d=ap.template(j)
    def attempt(_):
        try:ap.ai_polish(d,j)
        except ValueError:pass
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(attempt,[1,2]))
    assert len(calls)==1
    with db() as c:
        r=c.execute('SELECT * FROM usage').fetchone();assert r['state']=='failed_charge_unknown' and r['estimated'] is None and r['reserved']>0

def test_telegram_dedup(monkeypatch,listing):
    from app.notifications import notify
    for k,v in dict(TELEGRAM_ENABLED='true',TELEGRAM_BOT_TOKEN='fake',TELEGRAM_CHAT_ID='123').items():monkeypatch.setenv(k,v)
    ingest(listing);calls=[]
    class Reply:
        def raise_for_status(self):pass
        def json(self):return {'ok':True}
    def send(*a,**k):calls.append(1);return Reply()
    monkeypatch.setattr('app.notifications.httpx.post',send);assert notify()['sent']==1;assert notify()['sent']==0;assert len(calls)==1

def test_field_mapping():
    sys.path.insert(0,str(core.ROOT/'scripts'));from form_assist import map_fields
    fields=[{'index':0,'label':'Email address *','type':'email','required':True},{'index':1,'label':'Salary expectation','type':'text','required':True},{'index':2,'label':'Submit','type':'submit'}]
    mapped,missing=map_fields(fields,core.config('profile'));assert mapped[0]['value']=='ranzeet60@gmail.com';assert len(missing)==1

def test_senior_title_not_auto_prepared(listing):
    listing['title']='Senior React Developer';listing['description']='Build React interfaces, REST API integrations and well-tested TypeScript applications for our product team.'
    assert not score(listing)['shortlisted'];assert 'Senior/lead title needs manual experience review' in score(listing)['concerns']

def test_receipt_cannot_be_reopened(client,listing):
    jid=reviewed(listing);a=ap.approve(jid,digest(ap.snapshot(jid)));ap.receipt(jid,a['approval_id'],'Application received — fixture receipt 123')
    assert client.post(f'/api/jobs/{jid}/status',json={'status':'saved'}).status_code==400

def test_cv_change_invalidates_packet(monkeypatch,listing):
    jid=reviewed(listing);original=ap.cache_key;monkeypatch.setattr(ap,'cache_key',lambda j:'changed')
    assert 'Profile, rules or CV changed: refresh draft and review' in ap.snapshot(jid)['missing']
    with pytest.raises(ValueError):ap.save_review(jid,{})

def test_explicit_nepal_exclusion_overrides_worldwide(listing):
    listing['eligibility']='eligible';listing['description']+=' Available worldwide except Nepal.'
    assert score(listing)['eligibility']=='ineligible'
