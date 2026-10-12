"""Only fixed, documented read-only API hosts. No arbitrary URL fetching."""
import json, re, time
import httpx
from .core import db, stamp, audit, ingest, config, text, date

def fetch(key, endpoint, interval):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM feeds WHERE key=?',(key,)).fetchone()
        if row and row['next_fetch']>time.time(): return None
        c.execute('INSERT INTO feeds(key,next_fetch) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET next_fetch=excluded.next_fetch',(key,time.time()+interval))
    headers={'User-Agent':'RanjitJobPilot/1.0 (personal job discovery)','Accept':'application/json'}
    if row:
        if row['etag']: headers['If-None-Match']=row['etag']
        if row['modified']: headers['If-Modified-Since']=row['modified']
    try:
        # HTTP redirects deliberately disabled; auth/anti-bot responses are not bypassed.
        with httpx.Client(timeout=25,follow_redirects=False) as client:
            response=None
            for attempt in range(3):
                response=client.get(endpoint,headers=headers)
                if response.status_code!=429 and response.status_code<500: break
                if response.status_code==429:
                    retry=response.headers.get('Retry-After','3600')
                    seconds=int(retry) if retry.isdigit() else 3600
                    with db() as c: c.execute('UPDATE feeds SET next_fetch=MAX(next_fetch,?) WHERE key=?',(time.time()+seconds,key))
                    response.raise_for_status()
                if attempt<2: time.sleep(2**attempt)
            if response.status_code==304: return None
            response.raise_for_status()
            if len(response.content)>12_000_000: raise ValueError('Feed size exceeds limit')
            data=response.json()
        with db() as c:
            c.execute('UPDATE feeds SET etag=?,modified=?,payload=?,failures=0,error=NULL WHERE key=?',(response.headers.get('etag'),response.headers.get('last-modified'),json.dumps(data),key))
        return data
    except Exception as exc:
        # Do not log response bodies, headers, or credentials.
        with db() as c:
            c.execute('UPDATE feeds SET failures=failures+1,error=? WHERE key=?',(type(exc).__name__,key)); audit(c,'feed_failed',details=key+': '+type(exc).__name__)
        raise ValueError(f'{key}: fetch failed ({type(exc).__name__}); cooldown retained') from None

def iso(v):
    d=date(v); return d.isoformat() if d else None

def normalize_himalayas(v):
    restrictions=v.get('locationRestrictions')
    countries=[(x.get('alpha2') or x.get('name','')) if isinstance(x,dict) else x for x in restrictions or []]
    eligible='unknown' if restrictions is None else 'eligible' if not countries or any(x.lower() in ['np','nepal'] for x in countries) else 'ineligible'
    return {'title':v['title'],'company':v.get('companyName',''),'source':'himalayas','url':v['applicationLink'], 'description':text(v.get('description') or v.get('excerpt')),
      'posted_at':iso(v.get('pubDate')),'expires_at':iso(v.get('expiryDate')),'location':', '.join(countries) if countries else 'Worldwide' if restrictions is not None else '', 'eligibility':eligible,
      'timezone_restrictions':v.get('timezoneRestrictions',[]),'compensation':{'minimum':v.get('minSalary'),'maximum':v.get('maxSalary'),'currency':v.get('currency'),'period':v.get('salaryPeriod','annual')},'source_note':'Himalayas public API; refreshed daily. Source: https://himalayas.app'}

def normalize_remotive(v):
    return {'title':v['title'],'company':v.get('company_name',''),'source':'remotive','url':v['url'],'description':text(v.get('description')),'posted_at':iso(v.get('publication_date')),'location':v.get('candidate_required_location',''),'compensation':{'text':v.get('salary')},'source_note':'Remotive public API; listings delayed 24h. Source: https://remotive.com'}

def discover():
    r=config('rules'); summary={'created':0,'updated':0,'unchanged':0,'duplicate':0,'errors':[],'prepared':0}
    def consume(items,convert):
        for item in items:
            try:
                _,state=ingest(convert(item)); summary[state]+=1
            except (ValueError,KeyError,TypeError): summary['errors'].append('One malformed listing skipped')
    for source in r['enabled_sources']:
        try:
            if source=='himalayas':
                for page in range(1,min(10,r.get('himalayas_pages',3))+1):
                    d=fetch(f'himalayas:{page}',f'https://himalayas.app/jobs/api/search?country=NP&sort=recent&page={page}',86400)
                    if d is None: continue
                    consume(d.get('jobs',[]),normalize_himalayas)
                    if not d.get('jobs'): break
            elif source=='remotive':
                d=fetch('remotive','https://remotive.com/api/remote-jobs?category=software-dev',21600)
                if d: consume(d.get('jobs',[]),normalize_remotive)
            elif source=='greenhouse':
                for board in r['greenhouse_boards']:
                    if not re.fullmatch('[a-zA-Z0-9_-]{1,100}',board): continue
                    d=fetch('greenhouse:'+board,f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true',21600)
                    if d: consume(d.get('jobs',[]),lambda v:{'title':v['title'],'company':board,'source':'greenhouse','url':v['absolute_url'],'description':text(v.get('content')),'location':v.get('location',{}).get('name',''),'posted_at':None,'source_note':'Greenhouse Job Board API; updated_at is NOT a posting date.'})
        except ValueError as e: summary['errors'].append(str(e))
    if r.get('auto_prepare'):
        from .applications import prepare
        from .core import all_jobs
        for j in sorted(all_jobs(),key=lambda x:x['score']['total'],reverse=True):
            if summary['prepared']>=r.get('auto_prepare_limit',5): break
            if j['score']['shortlisted'] and j['status'] in ['new','saved','prepared']:
                try: prepare(j['id']); summary['prepared']+=1
                except ValueError as e: summary['errors'].append(str(e))
    return summary
