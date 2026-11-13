#!/usr/bin/env python3
"""Best-effort road-freight RSS collector. RSS leads are not verified alerts."""
import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
COUNTRIES = ['Ausztria','Belgium','Bulgária','Ciprus','Csehország','Dánia','Észtország','Finnország','Franciaország','Görögország','Hollandia','Horvátország','Írország','Lengyelország','Lettország','Litvánia','Luxemburg','Magyarország','Málta','Németország','Olaszország','Portugália','Románia','Spanyolország','Svédország','Szlovákia','Szlovénia','Oroszország','Fehéroroszország','Szerbia','Bosznia-Hercegovina','Montenegró','Albánia','Egyesült Királyság']
ALIASES = {
 'Ausztria':['austria','austrian','österreich'], 'Belgium':['belgium','belgian','belgique'],
 'Bulgária':['bulgaria','bulgarian'], 'Ciprus':['cyprus','cypriot'],
 'Csehország':['czechia','czech republic','czech'], 'Dánia':['denmark','danish'],
 'Észtország':['estonia','estonian'], 'Finnország':['finland','finnish'],
 'Franciaország':['france','french'], 'Görögország':['greece','greek'],
 'Hollandia':['netherlands','dutch'], 'Horvátország':['croatia','croatian'],
 'Írország':['ireland','irish'], 'Lengyelország':['poland','polish'],
 'Lettország':['latvia','latvian'], 'Litvánia':['lithuania','lithuanian'],
 'Luxemburg':['luxembourg'], 'Magyarország':['hungary','hungarian','magyarország'],
 'Málta':['malta','maltese'], 'Németország':['germany','german','deutschland'],
 'Olaszország':['italy','italian'], 'Portugália':['portugal','portuguese'],
 'Románia':['romania','romanian','românia'], 'Spanyolország':['spain','spanish'],
 'Svédország':['sweden','swedish'], 'Szlovákia':['slovakia','slovak'],
 'Szlovénia':['slovenia','slovenian'], 'Oroszország':['russia','russian'],
 'Fehéroroszország':['belarus','belarusian'], 'Szerbia':['serbia','serbian','srbija'],
 'Bosznia-Hercegovina':['bosnia','bosnian'], 'Montenegró':['montenegro'],
 'Albánia':['albania','albanian'], 'Egyesült Királyság':['united kingdom','britain','british','uk']
}
CATEGORIES = {
 'Útdíj':['toll','útdíj','maut','vignette','eurovignette','road charge'],
 'Üzemanyag':['fuel','diesel','gázolaj','adblue','üzemanyag'],
 'Útlezárás':['closure','road closed','útlezár','blockade','motorway closed','roadworks','kamionstop','truck ban'],
 'Vízum':['visa','vízum','entry permit'],
 'Határ':['border','határ','customs','vám','border crossing'],
 'Engedély':['permit','cemt','engedély','ecmt'],
 'Jogszabály':['regulation','legislation','law','jogszabály','tachograph','mobility package','driving time','rest period']
}
FREIGHT = ['truck','trucking','lorry','hgv','heavy goods','road freight','road haulage','road transport',
 'kamion','teherautó','közúti fuvar','fuvarozó','tachograph','tachográf','cabotage',
 'truck driver','lorry driver','kamionsofőr','tehergépkocsi','árufuvarozás','freight transport',
 'goods vehicle','commercial vehicle','transport operator','haulier','haulage']
OPERATIONAL = ['toll','útdíj','maut','vignette','eurovignette','adblue','diesel',
 'road closure','road closed','útlezár','border crossing','határátkelő',
 'ecmt','cemt','truck ban','kamionstop','weight restriction','customs','vám',
 'driving time','rest period','tachograph','tachográf']
EXCLUDE = ['railway','rail freight','rail logistics','passenger train','aviation','air cargo','airport',
 'passenger car','electric cars','car review','car racing']
CRIME = ['arrested','stole','stealing','theft','robbery','murder','police chase','drug smuggling']

def clean(value):
 return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()[:1200]

def has(text, phrases):
 return any(re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text, flags=re.I) for word in phrases)

def classify(title, description, default):
 # Prefer locations in the headline, not incidental nationality in a description.
 for text in (title, description):
  found = [c for c, names in ALIASES.items() if has(text, names + [c])]
  if len(found) == 1:
   return found[0]
  if len(found) > 1:
   return 'EU'  # Ambiguous multi-country story; don't guess.
 return default if default in COUNTRIES else 'EU'

def category(text):
 for label, words in CATEGORIES.items():
  if has(text, words):
   return label
 return 'Egyéb'

def relevant(title, desc):
 text = (title + ' ' + desc).lower()
 freight = has(text, FREIGHT)
 operational = has(text, OPERATIONAL)
 if has(text, EXCLUDE) and not (freight and operational):
  return False
 if has(text, CRIME) and not operational:
  return False
 # Require an actual freight link, or an operational issue with a road/freight context.
 return freight or (operational and has(text, ['road','motorway','highway','freight','transport','truck','lorry','kamion','teherautó','fuvar']))

def parse_date(value):
 try:
  return email.utils.parsedate_to_datetime(value).astimezone(dt.timezone.utc).isoformat()
 except (TypeError, ValueError, IndexError):
  try:
   value = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
   return (value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat()
  except (TypeError, ValueError, AttributeError):
   return ''

def read_items(payload):
 root = ET.fromstring(payload)
 for item in root.findall('.//item'):
  yield {key: item.findtext(key) or '' for key in ('title','link','description','pubDate')}
 ns = '{http://www.w3.org/2005/Atom}'
 for entry in root.findall('.//' + ns + 'entry'):
  link = entry.find(ns+'link')
  def atom(key): return entry.findtext(ns+key) or ''
  yield {'title':atom('title'),'link':link.get('href','') if link is not None else '',
         'description':atom('summary') or atom('content'),'pubDate':atom('published') or atom('updated')}

def translate(text):
 """Free public API: limited and not guaranteed. Never invent missing content."""
 if not text or len(text) > 450:
  return None
 try:
  params = urllib.parse.urlencode({'q':text,'langpair':'en|hu'})
  req = urllib.request.Request('https://api.mymemory.translated.net/get?' + params,
    headers={'User-Agent':'TransportIntelligencePersonalRSS/0.5'})
  with urllib.request.urlopen(req, timeout=9) as response:
   data = json.loads(response.read(150000))
  result = clean(data.get('responseData',{}).get('translatedText',''))
  if str(data.get('responseStatus')) == '200' and result and 'MYMEMORY WARNING' not in result.upper():
   return result
 except Exception as exc:
  print('TRANSLATION ERROR', str(exc)[:120])
 return None

def main():
 path = ROOT/'news.json'
 try:
  old = json.loads(path.read_text(encoding='utf-8'))
 except (FileNotFoundError, ValueError):
  old = {'items':[]}
 old_by_id = {x['id']:x for x in old.get('items',[]) if x.get('id')}
 existing = {}
 # Don't retain outdated incorrectly categorized rows unless rediscovered from RSS.
 successes, new_count, failures = 0, 0, []
 for src in SOURCES:
  try:
   req = urllib.request.Request(src['url'], headers={'User-Agent':'TransportIntelligencePersonalRSS/0.5'})
   with urllib.request.urlopen(req, timeout=15) as response:
    payload = response.read(2_000_000)
   for item in read_items(payload):
    url, title, desc = item['link'].strip(), clean(item['title']), clean(item['description'])
    if not title or not url.startswith('https://') or not relevant(title,desc):
     continue
    uid = hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]
    if uid not in old_by_id and uid not in existing:
     new_count += 1
    cached = old_by_id.get(uid,{})
    row = {'id':uid,'title':title,'summary':desc or 'Az RSS-forrás nem tartalmaz részletes összefoglalót.',
      'country':classify(title,desc,src.get('country','EU')),
      'category':category(title+' '+desc),'source':src['name']+' (RSS-találat, nem ellenőrzött)',
      'url':url,'published':parse_date(item['pubDate']),'urgent':False}
    for field in ('title_hu','summary_hu'):
     if cached.get(field): row[field] = cached[field]
    existing[uid] = row
   successes += 1
  except Exception as exc:
   failures.append(src.get('name','unknown'))
   print('SOURCE ERROR',src.get('name','unknown'),str(exc)[:160])
 if successes == 0:
  print('No feeds succeeded; preserving existing news.json')
  return
 # Preserve cached articles when a source is temporarily unavailable, but re-filter them.
 for uid, cached in old_by_id.items():
  if uid not in existing and relevant(cached.get('title',''),cached.get('summary','')):
   existing[uid] = cached
 rows = sorted(existing.values(),key=lambda x:x.get('published',''),reverse=True)[:300]
 translated_titles, translated_summaries, attempted = 0, 0, 0
 for row in rows:
  if attempted >= 12:
   break
  if not row.get('title_hu'):
   attempted += 1
   result = translate(row['title'])
   if result:
    row['title_hu'] = result
    translated_titles += 1
   time.sleep(0.15)
  # Translate only real descriptive text; never fabricate 3–5 sentences.
  desc = row.get('summary','')
  if row.get('title_hu') and not row.get('summary_hu') and len(desc) >= 90 and len(desc) <= 450 and attempted < 12:
   attempted += 1
   result = translate(desc)
   if result:
    row['summary_hu'] = result
    translated_summaries += 1
   time.sleep(0.15)
 output = {'items':rows,'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
           'sources_ok':successes,'sources_total':len(SOURCES),'sources_failed':failures,
           'translation_note':'Gépi fordítás; nem ellenőrzött RSS-találatok.'}
 path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Saved',len(rows),'articles;',new_count,'new;',successes,'/',len(SOURCES),'feeds succeeded')
 print('TRANSLATION:',translated_titles,'titles;',translated_summaries,'summaries;',attempted,'requests')

if __name__ == '__main__':
 main()
