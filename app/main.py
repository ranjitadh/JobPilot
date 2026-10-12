from contextlib import asynccontextmanager
from datetime import timedelta
import json, os, secrets, threading
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from .core import ROOT, init, db, job, all_jobs, ingest, config, digest, now, date, audit
from .applications import prepare, documents, save_review, snapshot, approve, receipt
from .feeds import discover
from .notifications import notify

@asynccontextmanager
async def lifespan(app):
    init(); yield
app=FastAPI(title='JobPilot • Ranjit',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
TOKEN=os.getenv('APP_TOKEN') or secrets.token_urlsafe(32)
LOCK=threading.Lock()
@app.middleware('http')
async def secure(request:Request,call_next):
    host=request.headers.get('host','').split(':')[0]
    if host not in ['127.0.0.1','localhost','testserver']: return JSONResponse({'detail':'Localhost only. Use an SSH tunnel.'},status_code=403)
    if request.url.path.startswith('/api'):
        if not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+TOKEN): return JSONResponse({'detail':'Access token required'},status_code=401)
        origin=request.headers.get('origin')
        if origin and origin not in ['http://127.0.0.1:8000','http://localhost:8000']: return JSONResponse({'detail':'Cross-origin request blocked'},status_code=403)
        if int(request.headers.get('content-length','0'))>6_000_000: return JSONResponse({'detail':'Request too large'},status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'; response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response
@app.exception_handler(ValueError)
async def bad_request(request,exc): return JSONResponse({'detail':str(exc)},status_code=400)
@app.get('/')
def home(): return FileResponse(ROOT/'app/static/index.html')
app.mount('/static',StaticFiles(directory=ROOT/'app/static'),name='static')

class Compensation(BaseModel):
    minimum:float|None=Field(default=None,ge=0)
    maximum:float|None=Field(default=None,ge=0)
    currency:str|None=None
    period:Literal['hourly','annual','monthly','fixed']|None=None
    text:str|None=Field(default=None,max_length=300)
class Listing(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=2,max_length=250)
    company:str=Field(default='',max_length=200)
    url:str=Field(max_length=2000)
    source:Literal['manual','upwork','linkedin','wellfound','yc','remoteok','wwr','himalayas','remotive','greenhouse']='manual'
    description:str=Field(default='',max_length=60000)
    location:str=Field(default='',max_length=300)
    eligibility:Literal['unknown','eligible','ineligible']='unknown'
    posted_at:str|None=None
    expires_at:str|None=None
    minimum_years:int|None=Field(default=None,ge=0,le=60)
    compensation:Compensation|None=None
    connects:int|None=Field(default=None,ge=0,le=1000)
    proposals:int|None=Field(default=None,ge=0)
    payment_verified:bool|None=None
    credibility_verified:bool|None=None
    credibility_evidence:str|None=Field(default=None,max_length=1000)
    authorization_unavailable:bool|None=None
    unpaid:bool|None=None
    required_skills:list[str]=Field(default_factory=list,max_length=50)
    screening_questions:list[str]=Field(default_factory=list,max_length=50)
    timezone_restrictions:list[str]=Field(default_factory=list,max_length=30)

@app.get('/api/jobs')
def jobs(q:str='',status:str='',source:str='',sort:str='score',page:int=1,priority:bool=False):
    if len(q)>200 or page<1: raise ValueError('Invalid search')
    items=all_jobs(); items=[x for x in items if q.lower() in (x['job']['title']+' '+x['job'].get('company','')+' '+x['job'].get('description','')).lower() and (not status or x['status']==status) and (not source or x['job'].get('source')==source) and (not priority or x['score']['shortlisted'] and x['score']['total']>=85)]
    if sort=='freshness': items.sort(key=lambda x:date(x['job'].get('posted_at')) or date('1970-01-01'),reverse=True)
    elif sort=='completeness': items.sort(key=lambda x:x['score']['completeness'],reverse=True)
    else: items.sort(key=lambda x:x['score']['total'],reverse=True)
    return {'items':items[(page-1)*20:page*20],'total':len(items),'page':page,'page_size':20}
@app.post('/api/jobs')
def import_job(body:Listing):
    data=body.model_dump(exclude_none=True)
    if data.get('credibility_verified') is not None and not data.get('credibility_evidence'): raise ValueError('Credibility verification requires evidence')
    for field in ['posted_at','expires_at']:
        if data.get(field) and date(data[field]) is None: raise ValueError('Invalid date')
    jid,state=ingest(data); return {'id':jid,'state':state}
@app.get('/api/jobs/{jid}')
def detail(jid:str):
    result=job(jid)
    try: result['documents']=documents(jid)
    except ValueError: result['documents']=None
    with db() as c:
        row=c.execute('SELECT * FROM receipts WHERE job_id=?',(jid,)).fetchone(); result['receipt']=dict(row) if row else None
    return result
@app.post('/api/jobs/{jid}/status')
def status(jid:str,body:dict):
    current=job(jid); target=body.get('status')
    if target not in ['saved','rejected','interviewing']: raise ValueError('Use receipt workflow for Applied')
    with db() as c:
        if target=='saved' and c.execute('SELECT 1 FROM receipts WHERE job_id=?',(jid,)).fetchone(): raise ValueError('Already applied; keep the receipt and use interviewing or rejected')
    if target=='interviewing':
        with db() as c:
            if not c.execute('SELECT 1 FROM receipts WHERE job_id=?',(jid,)).fetchone(): raise ValueError('Record the application receipt first')
    with db() as c:
        c.execute('UPDATE jobs SET status=? WHERE id=?',(target,jid)); c.execute('DELETE FROM approvals WHERE job_id=?',(jid,)); audit(c,'status_changed',jid,target)
    return {'status':target}
@app.post('/api/jobs/{jid}/prepare')
def generate(jid:str,body:dict):
    if not LOCK.acquire(False): raise ValueError('Another discovery or generation is running')
    try: return prepare(jid,body.get('use_ai') is True)
    finally: LOCK.release()
@app.post('/api/jobs/{jid}/review')
def review(jid:str,body:dict): return save_review(jid,body)
@app.get('/api/jobs/{jid}/packet')
def packet(jid:str):
    s=snapshot(jid); return {'snapshot':s,'hash':digest(s)}
@app.post('/api/jobs/{jid}/approve')
def approval(jid:str,body:dict):
    if body.get('explicit_approval') is not True: raise ValueError('Specific explicit approval required')
    return approve(jid,body.get('snapshot_hash'))
@app.post('/api/jobs/{jid}/receipt')
def record(jid:str,body:dict): return receipt(jid,body.get('approval_id',''),body.get('evidence',''))
@app.get('/api/jobs/{jid}/cover-letter')
def cover(jid:str):
    return Response(documents(jid)['payload']['cover_letter'],media_type='text/plain',headers={'Content-Disposition':'attachment; filename="cover-letter.txt"'})
@app.get('/api/resumes/{name}')
def resume(name:str):
    if name not in [x['file'] for x in config('profile')['resumes']]: raise HTTPException(404)
    p=ROOT/'resumes'/name
    if not p.is_file(): raise HTTPException(404)
    return FileResponse(p,filename=name)
@app.post('/api/resumes/{name}')
def upload_resume(name:str,file:UploadFile=File(...)):
    if name not in [x['file'] for x in config('profile')['resumes']]: raise ValueError('Choose a configured CV name')
    content=file.file.read(5_000_001)
    if len(content)>5_000_000 or not content.startswith(b'%PDF-'): raise ValueError('Upload a PDF under 5 MB')
    path=ROOT/'resumes'/name; path.parent.mkdir(exist_ok=True); path.write_bytes(content)
    with db() as c:
        c.execute('DELETE FROM approvals'); c.execute('UPDATE documents SET reviewed=0'); audit(c,'resume_replaced',details=name)
    return {'saved':name}
@app.post('/api/discover')
def run_discovery():
    if not LOCK.acquire(False): raise ValueError('Discovery/generation already running')
    try: return discover()
    finally: LOCK.release()
@app.post('/api/notify')
def notifications(): return notify()
@app.get('/api/config')
def settings():
    return {'profile':config('profile'),'rules':config('rules'),'ai_enabled':os.getenv('LLM_ENABLED','false')=='true','telegram_enabled':os.getenv('TELEGRAM_ENABLED','false')=='true'}
@app.get('/api/stats')
def stats():
    rows=all_jobs(); local=now().astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kathmandu')); day=local.date().isoformat()
    with db() as c:
        receipts=[dict(r) for r in c.execute('SELECT * FROM receipts')]; usage=[dict(r) for r in c.execute('SELECT * FROM usage ORDER BY id DESC')]; feed=[dict(r) for r in c.execute('SELECT key,next_fetch,failures,error FROM feeds')]
        events=[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 50')]
    return {'total':len(rows),'high_priority':sum(x['score']['shortlisted'] and x['score']['total']>=85 and x['status'] not in ['applied','interviewing','rejected'] for x in rows),'applied_today':sum(date(x['applied_at']).astimezone(local.tzinfo).date()==local.date() for x in receipts),'applied_week':sum(date(x['applied_at'])>=now()-timedelta(days=7) for x in receipts),'ai_today_usd':round(sum(x['estimated'] if x['estimated'] is not None else x['reserved'] for x in usage if x['day']==day),6),'daily_cap':float(os.getenv('AI_DAILY_USD','.2')),'potential_connects_avoided':sum(x['job'].get('connects') or 0 for x in rows if x['status']=='rejected' and x['job'].get('source')=='upwork'),'usage':usage,'feeds':feed,'audit':events,'note':'Connects metric is potential spend avoided on explicitly rejected jobs, not verified savings.'}
