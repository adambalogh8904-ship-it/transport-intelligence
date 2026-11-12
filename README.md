# Transport Intelligence – iPhone PWA v0.1

## Mi működik?
- Magyar nyelvű, mobilra optimalizált felület, 34 ország, 7 kategória.
- Keresés, ország- és kategóriaszűrés, sürgős hírek, mentés, országbeállítások.
- Helyi mentés a böngészőben, PWA manifest és offline app-shell.
- Opcionális HTTPS JSON hírfolyam beállítása a Beállításokban.

## Fontos
Alapállapotban **kizárólag 3, egyértelműen DEMO-ként jelölt tesztbejegyzés** látható. Nincs még beüzemelt adatgyűjtés, éles forrás vagy push értesítés. Az élő API-nak CORS-t engedélyeznie kell az alkalmazás domainjére.

## Közzététel telefonról, ingyen
1. GitHub-fiókban hozz létre egy nyilvános repót, pl. `transport-intelligence`.
2. Töltsd fel a mappa négy fájlját a repo gyökerébe (`index.html`, `manifest.webmanifest`, `sw.js`, `icon.svg`). iPhone Safariból a GitHub webes felülete használható, szükség esetén „Asztali webhely kérése”.
3. Settings → Pages → Build and deployment → Deploy from a branch → `main` / root → Save.
4. A közzétett HTTPS URL-t iPhone-on Safariban nyisd meg, majd Megosztás → Hozzáadás a Főképernyőhöz.
5. Ha a GitHub Pages nem engedélyezett az adott fiókban, alternatíva a Cloudflare Pages ingyenes statikus hosztolása.

## Élő API formátum
A Beállításokban add meg egy saját HTTPS végpont URL-jét. Példa válasz:
```json
{"items":[{"id":"sample-001","country":"Szerbia","category":"Határ","title":"Példa címsor","summary":"Példa összefoglaló","source":"Hivatalos forrás neve","url":"https://example.org/notice","published":"2026-11-12","urgent":false}]}
```
A mintában szereplő URL nem valódi hírforrás. Élesben ellenőrzött forrás és megbízható frissítés szükséges.

## Korlátok
- A GitHub Pages nyilvános statikus oldal; nem alkalmas privát API-kulcsok tárolására.
- Az iOS főképernyős telepítés és offline működés HTTPS közzététel után érhető el.
- A webalkalmazás még nem natív iOS app, és nem tud a háttérben önállóan híreket gyűjteni.
- Ingyenes szolgáltatások kvótái és feltételei változhatnak.
