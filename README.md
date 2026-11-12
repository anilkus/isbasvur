# Job Agent

Finds matching job postings every day, writes a tailored application package for any link you give it, and fills the application form in your browser. The last click (Submit) is always yours.

Site: https://anilkus.github.io/isbasvur/

## How it works

| Part | Where | What it does |
|---|---|---|
| `scripts/fetch_jobs.py` | GitHub Actions, daily 08:17 TR | Pulls Arbeitnow, Remotive and RSS feeds, scores each listing against `profile/profile.json`, writes `docs/data/jobs.json` |
| `docs/index.html` | GitHub Pages | Lists matches, takes a job link, shows finished packages with copy buttons |
| `scripts/prepare_application.py` | GitHub Actions, on issue | Reads the posting, asks Claude for fit analysis, cover letter and form answers in your voice, cleans dashes and AI phrasing |
| `userscript/job-autofill.user.js` | Your browser (Tampermonkey) | On an application form, fills fields from the package, marks what is left. Never submits |

Flow: give the link to Claude in chat → Claude writes and pushes the package (and a Gmail draft is created if the posting wants email) → open the posting, click **Formu doldur**, check, attach CV, submit.

## Kurulum (bir kerelik)

1. **Repo:** Bu klasörü `anilkus/isbasvur` olarak GitHub'a yükle (public, Pages ücretsiz planda public repo ister).
2. **Paketler (API gerekmez):** İlan linkini Claude sohbetine `isbasvur: <link>` diye ver. Claude paketi yazar,
   `scripts/save_package.py` ile kaydedip push eder. İstersen ileride `ANTHROPIC_API_KEY` secret'ı ekleyip
   `apply: <link>` issue'larıyla tam otomatik moda geçebilirsin.
3. **Pages:** Settings → Pages → Source: *Deploy from a branch*, Branch: `main`, klasör: `/docs`.
4. **Actions izni:** Settings → Actions → General → Workflow permissions → *Read and write permissions*.
5. **İlk tarama:** Actions → *Fetch jobs* → *Run workflow*.
6. **Userscript:** Tarayıcına Tampermonkey kur, `userscript/job-autofill.user.js` dosyasının *Raw* linkini aç, *Install* de.
   Tampermonkey menüsünden **Job Agent: kişisel bilgileri düzenle** ile e-posta, telefon, şehir, maaş beklentisi,
   çalışma izni gibi bilgileri gir. Bunlar sadece tarayıcında durur, repoya hiç girmez.
7. **CV:** `profile/cv.md` dosyasını güncel CV metninle değiştir. Model sadece burada yazanı kullanır.

### Mail ile başvuru (Gmail taslağı)

İlan "başvurunu şu adrese gönder" diyorsa paket hazırlanınca Gmail'de ekleriyle birlikte bir **taslak** oluşur. Hiçbir şey otomatik gönderilmez.
Başka ilanlar için de sitedeki pakette **Gmail taslağı oluştur** butonu var.

1. Gmail hesabında 2 adımlı doğrulama açık olsun, sonra https://myaccount.google.com/apppasswords adresinden bir uygulama şifresi al.
2. Repo secret'ları ekle:
   - `GMAIL_ADDRESS`: kişisel Gmail adresin
   - `GMAIL_APP_PASSWORD`: aldığın 16 haneli uygulama şifresi
   - `DOCS_PASSPHRASE`: belgeleri şifrelemek için uzun bir parola
   - `CONTACT_LINE` (isteğe bağlı): mail ekindeki cover letter başlığına yazılacak satır, örn. `mail@gmail.com · +90 5xx xxx xx xx`
3. Belgeleri şifreleyip ekle (repoda sadece `.gpg` dosyaları durur):
   ```bash
   export DOCS_PASSPHRASE='secret ile aynı parola'
   ./scripts/encrypt_docs.sh cv ~/Belgeler/CV.pdf
   ./scripts/encrypt_docs.sh transcript ~/Belgeler/Transkript.pdf
   git add private && git commit -m "docs" && git push
   ```
   Anahtar adları ve ekte görünecek dosya adları `profile/documents.json` içinde.

### Formlara dosya yükleme

Tampermonkey menüsü → **Job Agent: belgeleri yönet** ile CV, transkript vb. dosyaları bir kez seç. Sadece tarayıcında saklanır.
"Formu doldur" dediğinde CV/Resume alanına CV'yi, Cover letter alanına o ilana özel PDF'i, diğer alanlara eşleşen belgeyi yükler.
Yükleyemediği alanları turuncu işaretler.

## Ayarlar

- `profile/profile.json`: hedef roller, anahtar kelimeler, tercih edilen ülkeler, yazım tarzı kuralları.
- `profile/sources.json`: kaynaklar, RSS listesi, `min_score` eşiği.
- Sayfası JavaScript ile yüklenen ilanlarda (Workday vb.) sitedeki kutuya ilan metnini de yapıştır, issue'da `---` altına gider.

## Bilmen gerekenler

- Repo public olduğu için hazırlanan paketler (cover letter'lar) de herkese açık URL'de durur. İletişim bilgilerin repoda yok.
- Sadece repo sahibinin açtığı `apply:` issue'ları çalışır, başkası senin API kredini harcayamaz.
- LinkedIn Easy Apply gibi platform içi formlarda otomasyon kullanım şartlarına aykırı olabilir. Userscript sadece alanları doldurur, gönderme ve dosya yükleme sende.
