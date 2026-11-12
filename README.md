# Job Agent

Finds matching job postings every day, writes a tailored application package for any link you give it, and fills the application form in your browser. The last click (Submit) is always yours.

Site: https://anilkus.github.io/job-agent/

## How it works

| Part | Where | What it does |
|---|---|---|
| `scripts/fetch_jobs.py` | GitHub Actions, daily 08:17 TR | Pulls Arbeitnow, Remotive and RSS feeds, scores each listing against `profile/profile.json`, writes `docs/data/jobs.json` |
| `docs/index.html` | GitHub Pages | Lists matches, takes a job link, shows finished packages with copy buttons |
| `scripts/prepare_application.py` | GitHub Actions, on issue | Reads the posting, asks Claude for fit analysis, cover letter and form answers in your voice, cleans dashes and AI phrasing |
| `userscript/job-autofill.user.js` | Your browser (Tampermonkey) | On an application form, fills fields from the package, marks what is left. Never submits |

Flow: paste a link on the site → it opens a pre-filled issue `apply: <link>` → submit it → about 1-2 minutes later the issue gets a fit summary and closes → open the posting, click **Formu doldur**, check, attach CV, submit.

## Kurulum (bir kerelik)

1. **Repo:** Bu klasörü `anilkus/job-agent` olarak GitHub'a yükle (public, Pages ücretsiz planda public repo ister).
2. **API anahtarı:** Settings → Secrets and variables → Actions → *New repository secret* → `ANTHROPIC_API_KEY`.
   İsteğe bağlı: *Variables* sekmesinde `CLAUDE_MODEL` (varsayılan `claude-sonnet-5-5`).
3. **Pages:** Settings → Pages → Source: *Deploy from a branch*, Branch: `main`, klasör: `/docs`.
4. **Actions izni:** Settings → Actions → General → Workflow permissions → *Read and write permissions*.
5. **İlk tarama:** Actions → *Fetch jobs* → *Run workflow*.
6. **Userscript:** Tarayıcına Tampermonkey kur, `userscript/job-autofill.user.js` dosyasının *Raw* linkini aç, *Install* de.
   Tampermonkey menüsünden **Job Agent: kişisel bilgileri düzenle** ile e-posta, telefon, şehir, maaş beklentisi,
   çalışma izni gibi bilgileri gir. Bunlar sadece tarayıcında durur, repoya hiç girmez.
7. **CV:** `profile/cv.md` dosyasını güncel CV metninle değiştir. Model sadece burada yazanı kullanır.

## Ayarlar

- `profile/profile.json`: hedef roller, anahtar kelimeler, tercih edilen ülkeler, yazım tarzı kuralları.
- `profile/sources.json`: kaynaklar, RSS listesi, `min_score` eşiği.
- Sayfası JavaScript ile yüklenen ilanlarda (Workday vb.) sitedeki kutuya ilan metnini de yapıştır, issue'da `---` altına gider.

## Bilmen gerekenler

- Repo public olduğu için hazırlanan paketler (cover letter'lar) de herkese açık URL'de durur. İletişim bilgilerin repoda yok.
- Sadece repo sahibinin açtığı `apply:` issue'ları çalışır, başkası senin API kredini harcayamaz.
- LinkedIn Easy Apply gibi platform içi formlarda otomasyon kullanım şartlarına aykırı olabilir. Userscript sadece alanları doldurur, gönderme ve dosya yükleme sende.
