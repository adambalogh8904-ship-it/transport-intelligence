#!/usr/bin/env python3
"""Best-effort public RSS collection; never invent or certify news."""
import datetime as dt, email.utils, hashlib, html, json, pathlib, re, urllib.request, xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCES=json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
COUNTRIES=['Ausztria','Belgium','Bulgária','Ciprus','Csehország','Dánia','Észtország','Finnország','Franciaország','Görögország','Hollandia','Horvátország','Írország','Lengyelország','Lettország','Litvánia','Luxemburg','Magyarország','Málta','Németország','Olaszország','Portugália','Románia','Spanyolország','Svédország','Szlovákia','Szlovénia','Oroszország','Fehéroroszország','Szerbia','Bosznia-Hercegovina','Montenegró','Albánia','Egyesült Királyság']
ALIASES={'Németország':['germany','deutschland'],'Ausztria':['austria','österreich'],'Románia':['romania','românia'],'Magyarország':['hungary','magyarország'],'Szerbia':['serbia','srbija'],'Fehéroroszország':['belarus','belarusz'],'Oroszország':['russia','oroszország'],'Lengyelország':['poland'],'Franciaország':['france'],'Egyesült Királyság':['uk','united kingdom','britain'],'Olaszország':['italy'],'Spanyolország':['spain'],'Szlovákia':['slovakia'],'Horvátország':['croatia'],'Csehország':['czech'],'Bulgária':['bulgaria'],'Bosznia-Hercegovina':['bosnia'],'Montenegró':['montenegro'],'Albánia':['albania'],'Hollandia':['netherlands'],'Belgium':['belgium'],'Szlovénia':['slovenia'],'Litvánia':['lithuania'],'Lettország':['latvia'],'Észtország':['estonia'],'Dánia':['denmark'],'Svédország':['sweden'],'Finnország':['finland'],'Görögország':['greece'],'Portugália':['portugal'],'Írország':['ireland'],'Luxemburg':['luxembourg'],'Ciprus':['cyprus'],'Málta':['malta']}
CATEGORIES={'Útdíj':['toll','útdíj','maut','vignette'],'Üzemanyag':['fuel','diesel','gázolaj','adblue'],'Útlezárás':['closure','road closed','útlezár','blockade'],'Vízum':['visa','vízum'],'Határ':['border','határ','customs','vám'],'Engedély':['permit','cemt','engedély'],'Jogszabály':['regulation','law','jogszabály','tachograph']}
def clean(t):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',t or ''))).strip()[:1200]
def classify(t,default):
 text=t.lower()
 for country, aliases in ALIASES.items():
  if any(re.search(r'(?<!\w)'+re.escape(a)+r'(?!\w)',text) for a in aliases):return country
 return default if default in COUNTRIES else 'EU'
def category(t):
 t=t.lower()
 return next((c for c,keys in CATEGORIES.items() if any(k in t for k in keys)),'Jogszabály')
def parse_date(s):
 try:return email.utils.parsedate_to_datetime(s).astimezone(dt.timezone.utc).isoformat()
 except Exception:return ''
def read_items(data):
 root=ET.fromstring(data)
 for item in root.findall('.//item'):
  yield {k:(item.findtext(k) or '') for k in ('title','link','description','pubDate')}
 for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
  link=entry.find('{http://www.w3.org/2005/Atom}link')
  def atom(k):return entry.findtext('{http://www.w3.org/2005/Atom}'+k) or ''
  yield {'title':atom('title'),'link':link.get('href','') if link is not None else '', 'description':atom('summary'),'pubDate':atom('updated')}
def main():
 old=json.loads((ROOT/'news.json').read_text(encoding='utf-8'))
 existing={x['id']:x for x in old.get('items',[]) if x.get('id')}
 successes=0
 for src in SOURCES:
  try:
   req=urllib.request.Request(src['url'],headers={'User-Agent':'TransportIntelligencePersonalRSS/0.2'})
   with urllib.request.urlopen(req,timeout=18) as r: payload=r.read(2_000_000)
   for item in read_items(payload):
    url=item['link'].strip();title=clean(item['title']);desc=clean(item['description'])
    if not title or not url.startswith('https://'):continue
    uid=hashlib.sha256(url.encode()).hexdigest()[:24]
    existing[uid]={'id':uid,'title':title,'summary':desc or 'Olvasd el a teljes hírt a hivatkozáson.','country':classify(title+' '+desc,src['country']),'category':category(title+' '+desc),'source':src['name']+' (híraggregátor, nem hivatalos megerősítés)','url':url,'published':parse_date(item['pubDate']),'urgent':False}
   successes+=1
  except Exception as exc:print('SOURCE ERROR',src['name'],str(exc)[:180])
 if successes==0:
  print('No sources succeeded; keeping existing news.json')
  return
 rows=sorted(existing.values(),key=lambda x:x.get('published',''),reverse=True)[:250]
 (ROOT/'news.json').write_text(json.dumps({'items':rows,'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'sources_ok':successes,'sources_total':len(SOURCES)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Saved',len(rows),'articles from',successes,'feeds')
if __name__=='__main__':main()
