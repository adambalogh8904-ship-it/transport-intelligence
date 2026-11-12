#!/usr/bin/env python3
"""Collect public RSS results; these are unverified leads, not official alerts."""
import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.request
import urllib.parse
import time
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
COUNTRIES = ['Ausztria','Belgium','Bulgária','Ciprus','Csehország','Dánia','Észtország','Finnország','Franciaország','Görögország','Hollandia','Horvátország','Írország','Lengyelország','Lettország','Litvánia','Luxemburg','Magyarország','Málta','Németország','Olaszország','Portugália','Románia','Spanyolország','Svédország','Szlovákia','Szlovénia','Oroszország','Fehéroroszország','Szerbia','Bosznia-Hercegovina','Montenegró','Albánia','Egyesült Királyság']
ALIASES = {
 'Ausztria':['austria','österreich'], 'Belgium':['belgium','belgique'], 'Bulgária':['bulgaria'], 'Ciprus':['cyprus'],
 'Csehország':['czechia','czech republic'], 'Dánia':['denmark'], 'Észtország':['estonia'], 'Finnország':['finland'],
 'Franciaország':['france'], 'Görögország':['greece'], 'Hollandia':['netherlands'], 'Horvátország':['croatia'],
 'Írország':['ireland'], 'Lengyelország':['poland'], 'Lettország':['latvia'], 'Litvánia':['lithuania'],
 'Luxemburg':['luxembourg'], 'Magyarország':['hungary'], 'Málta':['malta'], 'Németország':['germany','deutschland'],
 'Olaszország':['italy'], 'Portugália':['portugal'], 'Románia':['romania','românia'], 'Spanyolország':['spain'],
 'Svédország':['sweden'], 'Szlovákia':['slovakia'], 'Szlovénia':['slovenia'], 'Oroszország':['russia'],
 'Fehéroroszország':['belarus'], 'Szerbia':['serbia','srbija'], 'Bosznia-Hercegovina':['bosnia'],
 'Montenegró':['montenegro'], 'Albánia':['albania'], 'Egyesült Királyság':['united kingdom','britain','british']
}
CATEGORIES = {
 'Útdíj':['toll','útdíj','maut','vignette','eurovignette','road charge'],
 'Üzemanyag':['fuel','diesel','gázolaj','adblue','petrol','üzemanyag'],
 'Útlezárás':['closure','road closed','útlezár','blockade','motorway closed','autópálya lezár'],
 'Vízum':['visa','vízum','entry permit'],
 'Határ':['border','határ','customs','vám','border crossing'],
 'Engedély':['permit','cemt','engedély','ecmt'],
 'Jogszabály':['regulation','legislation','law','jogszabály','tachograph','mobility package']
}

def clean(value):
 return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()[:1200]

def classify(text, default):
 """Country-specific feed takes precedence; otherwise accept one unambiguous mention."""
 if default in COUNTRIES:
  return default
 found = [country for country, names in ALIASES.items() if any(re.search(r'(?<!\w)' + re.escape(n) + r'(?!\w)', text.lower()) for n in names + [country.lower()])]
 return found[0] if len(found) == 1 else 'EU'

def category(text):
 lower = text.lower()
 for label, words in CATEGORIES.items():
  if any(re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', lower) for word in words):
   return label
 return 'Egyéb'

def parse_date(value):
 try:
  return email.utils.parsedate_to_datetime(value).astimezone(dt.timezone.utc).isoformat()
 except (TypeError, ValueError, IndexError):
  try:
   parsed = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
   return parsed.astimezone(dt.timezone.utc).isoformat() if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc).isoformat()
  except (TypeError, ValueError, AttributeError):
   return ''

def read_items(payload):
 root = ET.fromstring(payload)
 for item in root.findall('.//item'):
  yield {key: item.findtext(key) or '' for key in ('title','link','description','pubDate')}
 ns = '{http://www.w3.org/2005/Atom}'
 for entry in root.findall('.//' + ns + 'entry'):
  link = entry.find(ns + 'link')
  def atom(key): return entry.findtext(ns + key) or ''
  yield {'title':atom('title'),'link':link.get('href','') if link is not None else '', 'description':atom('summary') or atom('content'),'pubDate':atom('published') or atom('updated')}

# V0.4: prioritise road freight topics; do not mistake general rail/air news for trucking.
ROAD = ('truck','trucking','lorry','hgv','heavy goods','road freight','road haulage','road transport',
        'kamion','teherautó','közúti fuvar','fuvarozó','tachograph','tachográf','adr','cabotage',
        'driver','sofőr','autópálya','motorway','highway','border crossing','határátkelő')
ROAD_SPECIFIC = ('toll','útdíj','maut','vignette','eurovignette','adblue','diesel',
                 'road closure','road closed','útlezár','border crossing','tachograph','tachográf',
                 'ecmt','cemt','road freight','road haulage','hgv','truck','trucking','lorry','kamion','teherautó')
OTHER_TRANSPORT = ('railway','rail freight','rail logistics','train service','aviation','air cargo','airport','passenger train')

def relevant(text):
 t = text.lower()
 if any(x in t for x in OTHER_TRANSPORT) and not any(x in t for x in ROAD_SPECIFIC):
  return False
 return any(x in t for x in ROAD + ROAD_SPECIFIC) or (category(t) != 'Egyéb' and any(x in t for x in ('transport','road','freight','logistics','szállítás','fuvar')))

def translate(text):
 """Optional best-effort public translation; never change factual content when it fails."""
 if not text or len(text) > 450:
  return None
 try:
  q = urllib.parse.urlencode({'q':text,'langpair':'en|hu'})
  req = urllib.request.Request('https://api.mymemory.translated.net/get?'+q,
       headers={'User-Agent':'TransportIntelligencePersonalRSS/0.4'})
  with urllib.request.urlopen(req, timeout=7) as response:
   data = json.loads(response.read(150000))
  result = clean(data.get('responseData',{}).get('translatedText',''))
  if data.get('responseStatus') == 200 and result and 'MYMEMORY WARNING' not in result.upper():
   return result
 except Exception as exc:
  print('Translation unavailable:',str(exc)[:80])
 return None

def main():
 path = ROOT / 'news.json'
 try:
  old = json.loads(path.read_text(encoding='utf-8'))
 except (FileNotFoundError, ValueError):
  old = {'items':[]}
 existing = {item['id']:item for item in old.get('items',[]) if item.get('id') and relevant(item.get('title','')+' '+item.get('summary',''))}
 successes = 0
 failures = []
 new_count = 0
 for src in SOURCES:
  try:
   req = urllib.request.Request(src['url'], headers={'User-Agent':'TransportIntelligencePersonalRSS/0.3'})
   with urllib.request.urlopen(req,timeout=15) as response:
    payload = response.read(2_000_000)
   for item in read_items(payload):
    url = item['link'].strip()
    title, desc = clean(item['title']), clean(item['description'])
    if not title or not url.startswith('https://') or not relevant(title+' '+desc):
     continue
    uid = hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]
    if uid not in existing:
     new_count += 1
    existing[uid] = {'id':uid,'title':title,'summary':desc or 'Olvasd el a teljes hírt a hivatkozáson.',
      'country':classify(title+' '+desc,src.get('country','EU')),
      'category':category(title+' '+desc),'source':src['name']+' (RSS-találat, nem ellenőrzött)',
      'url':url,'published':parse_date(item['pubDate']),'urgent':False}
   successes += 1
  except Exception as exc:
   failures.append(src.get('name','unknown'))
   print('SOURCE ERROR',src.get('name','unknown'),str(exc)[:160])
 if successes == 0:
  print('No feeds succeeded; preserving existing news.json')
  return
 rows = sorted(existing.values(), key=lambda item:item.get('published',''),reverse=True)[:300]
 # Free public translation is rate-limited. Only translate recent entries and reuse cached results.
 # No translation is invented: when unavailable, preserve the original title/summary.
 translated = 0
 for row in rows[:25]:
  cached = next((x for x in old.get('items',[]) if x.get('id') == row['id']), None)
  if cached and cached.get('title_hu'):
   row['title_hu'] = cached['title_hu']
   if cached.get('summary_hu'): row['summary_hu'] = cached['summary_hu']
   continue
  result = translate(row['title'])
  if result:
   row['title_hu'] = result
   translated += 1
  if translated >= 12: break
 output = {'items':rows,'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
           'sources_ok':successes,'sources_total':len(SOURCES),'sources_failed':failures,'translation_note':'Automatikus, nem ellenőrzött fordítás; az eredeti cím is megmarad.'}
 path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Saved',len(rows),'articles;',new_count,'new;',successes,'/',len(SOURCES),'feeds succeeded')

if __name__ == '__main__':
 main()
