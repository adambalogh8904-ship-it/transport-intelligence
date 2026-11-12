#!/usr/bin/env python3
"""Transport Intelligence: best-effort RSS collection and Hungarian summaries.

Optional packages: beautifulsoup4, deep-translator.
No article or translation is treated as independently verified.
"""
import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
COUNTRIES = ['Ausztria','Belgium','Bulgária','Ciprus','Csehország','Dánia','Észtország','Finnország','Franciaország','Görögország','Hollandia','Horvátország','Írország','Lengyelország','Lettország','Litvánia','Luxemburg','Magyarország','Málta','Németország','Olaszország','Portugália','Románia','Spanyolország','Svédország','Szlovákia','Szlovénia','Oroszország','Fehéroroszország','Szerbia','Bosznia-Hercegovina','Montenegró','Albánia','Egyesült Királyság']
ALIASES = {'Németország':['germany','deutschland'],'Ausztria':['austria','österreich'],'Románia':['romania','românia'],'Magyarország':['hungary','magyarország'],'Szerbia':['serbia','srbija'],'Fehéroroszország':['belarus','belarusz'],'Oroszország':['russia','oroszország'],'Lengyelország':['poland'],'Franciaország':['france'],'Egyesült Királyság':['united kingdom','britain'],'Olaszország':['italy'],'Spanyolország':['spain'],'Szlovákia':['slovakia'],'Horvátország':['croatia'],'Csehország':['czech'],'Bulgária':['bulgaria'],'Bosznia-Hercegovina':['bosnia'],'Montenegró':['montenegro'],'Albánia':['albania'],'Hollandia':['netherlands'],'Belgium':['belgium'],'Szlovénia':['slovenia'],'Litvánia':['lithuania'],'Lettország':['latvia'],'Észtország':['estonia'],'Dánia':['denmark'],'Svédország':['sweden'],'Finnország':['finland'],'Görögország':['greece'],'Portugália':['portugal'],'Írország':['ireland'],'Luxemburg':['luxembourg'],'Ciprus':['cyprus'],'Málta':['malta']}
CATEGORIES = {'Útdíj':['toll','útdíj','maut','vignette','road charge'],'Üzemanyag':['fuel','diesel','gázolaj','adblue'],'Útlezárás':['closure','road closed','útlezár','blockade','driving ban','truck ban'],'Vízum':['visa','vízum'],'Határ':['border','határ','customs','vám'],'Engedély':['permit','cemt','engedély'],'Jogszabály':['regulation','law','jogszabály','tachograph']}
RELEVANT = ['truck','trucking','lorry','hgv','freight','haulage','road transport','heavy goods','commercial vehicle','kamion','teherautó','fuvaroz','tachograph','útdíj','toll','driving ban','truck ban','border crossing','customs','cemt','adblue','diesel','logistics','transport']
HEADERS = {'User-Agent':'Mozilla/5.0 (compatible; TransportIntelligencePersonalRSS/0.3)'}

def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()

def classify(text, default):
    # Prefer the source's country: a foreign country mentioned in the headline
    # does not necessarily mean the story belongs to that country.
    if default in COUNTRIES:
        return default
    text = text.lower()
    for country, aliases in ALIASES.items():
        if any(re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', text) for a in aliases):
            return country
    return 'EU'

def category(text):
    text = text.lower()
    return next((name for name, keys in CATEGORIES.items() if any(key in text for key in keys)), 'Egyéb')

def parse_date(value):
    try:
        return email.utils.parsedate_to_datetime(value).astimezone(dt.timezone.utc).isoformat()
    except Exception:
        try:
            return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(dt.timezone.utc).isoformat()
        except Exception:
            return ''

def read_items(data):
    root = ET.fromstring(data)
    for item in root.findall('.//item'):
        yield {key: (item.findtext(key) or '') for key in ('title','link','description','pubDate')}
    atom_ns = '{http://www.w3.org/2005/Atom}'
    for entry in root.findall('.//' + atom_ns + 'entry'):
        link = entry.find(atom_ns + 'link')
        def field(key):
            return entry.findtext(atom_ns + key) or ''
        yield {'title':field('title'), 'link':link.get('href','') if link is not None else '', 'description':field('summary') or field('content'), 'pubDate':field('updated') or field('published')}

def fetch_article(url):
    # Google News redirect links may not resolve to the publisher; skip if so.
    if 'news.google.com' in url:
        return ''
    try:
        from bs4 import BeautifulSoup
        request = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=9) as response:
            if 'html' not in response.headers.get('Content-Type','').lower():
                return ''
            raw = response.read(350_000)
        soup = BeautifulSoup(raw, 'html.parser')
        for tag in soup(['script','style','nav','footer','header','aside','form']):
            tag.decompose()
        article = soup.find('article') or soup.find('main')
        if article is None:
            return ''
        paragraphs = [clean(p.get_text(' ', strip=True)) for p in article.find_all('p')]
        return ' '.join(p for p in paragraphs if len(p) >= 55)[:3000]
    except Exception:
        return ''

def source_summary(description, article):
    """Extract sentences from available source text; do not invent facts."""
    content = article if len(article) >= 250 else description
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean(content)) if len(s.strip()) >= 35]
    # Require sufficient material for a 3-sentence summary.
    if len(sentences) < 3:
        return ''
    return ' '.join(sentences[:5])[:1800]

def translate(text, translator):
    if not text or translator is None:
        return ''
    try:
        translated = translator.translate(text[:1800])
        return clean(translated) if translated else ''
    except Exception as exc:
        print('TRANSLATION ERROR:', str(exc)[:140])
        return ''

def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeError) as exc:
        print('JSON READ ERROR:', path.name, str(exc)[:140])
        return fallback

def main():
    sources = load_json(ROOT / 'sources.json', [])
    if not isinstance(sources, list) or not sources:
        raise SystemExit('sources.json must be a non-empty JSON array; refusing to overwrite news.json')
    old = load_json(ROOT / 'news.json', {'items':[]})
    existing = {item['id']:item for item in old.get('items',[]) if isinstance(item,dict) and item.get('id')}
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target='hu')
    except Exception as exc:
        print('Translation unavailable:', str(exc)[:140])
        translator = None
    successes = 0
    new_count = 0
    for src in sources:
        try:
            request = urllib.request.Request(src['url'], headers=HEADERS)
            with urllib.request.urlopen(request, timeout=18) as response:
                payload = response.read(2_000_000)
            for item in read_items(payload):
                url = item['link'].strip()
                title = clean(item['title'])[:350]
                description = clean(item['description'])[:1800]
                if not title or not url.startswith('https://'):
                    continue
                # Only transport-related stories; do not filter out all general legal updates.
                combined = (title + ' ' + description).lower()
                if not any(term in combined for term in RELEVANT):
                    continue
                uid = hashlib.sha256(url.encode()).hexdigest()[:24]
                if uid in existing:
                    continue
                article = fetch_article(url)
                extract = source_summary(description, article)
                title_hu = translate(title, translator)
                summary_hu = translate(extract, translator) if extract else ''
                row = {'id':uid,'title':title_hu or title,
                       'summary':summary_hu or 'A teljes cikk alapján nem áll rendelkezésre megbízható, 3–5 mondatos magyar összefoglaló. Az eredeti forrás megnyitható.',
                       'original_title':title,'country':classify(title+' '+description,src.get('country','EU')),
                       'category':category(title+' '+description),
                       'source':src.get('name','RSS')+' (RSS-találat, nem ellenőrzött)',
                       'url':url,'published':parse_date(item['pubDate']), 'urgent':False,
                       'translation_status':'translated' if title_hu and summary_hu else 'partial' if title_hu else 'unavailable',
                       'summary_status':'source_extract' if summary_hu else 'insufficient_source_text'}
                existing[uid] = row
                new_count += 1
                time.sleep(0.15)
            successes += 1
        except Exception as exc:
            print('SOURCE ERROR', src.get('name','unknown'), str(exc)[:180])
    if successes == 0:
        print('No feeds succeeded; keeping existing news.json')
        return
    rows = sorted(existing.values(), key=lambda x:x.get('published',''), reverse=True)[:250]
    result = {'items':rows,'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
              'sources_ok':successes,'sources_total':len(sources)}
    (ROOT/'news.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved',len(rows),'articles;',new_count,'new;',successes,'feeds succeeded')

if __name__ == '__main__':
    main()