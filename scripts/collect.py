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

def main():
 path = ROOT / 'news.json'
 try:
  old = json.loads(path.read_text(encoding='utf-8'))
 except (FileNotFoundError, ValueError):
  old = {'items':[]}
 existing = {item['id']:item for item in old.get('items',[]) if item.get('id')}
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
    if not title or not url.startswith('https://'):
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
 rows = sorted(existing.values(), key=lambda item:item.get('published',''),reverse=True)[:500]
 output = {'items':rows,'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
           'sources_ok':successes,'sources_total':len(SOURCES),'sources_failed':failures}
 path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Saved',len(rows),'articles;',new_count,'new;',successes,'/',len(SOURCES),'feeds succeeded')

if __name__ == '__main__':
 main()
