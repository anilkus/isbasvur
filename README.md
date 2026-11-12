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

## Otomatik başvuru (ücretsiz)

1. **Bulma ve hazırlama:** Her sabah tarama yapılır. Puanı yüksek 4 yeni ilan için paketler ücretsiz Groq API ile kendiliğinden yazılır.
   Başka bir ilan için sitede **Başvur** de, GitHub'da açılan isteği "Create" ile onayla.
2. **Onay:** Sitede pakete bak, **Onayla ve gönder** de, GitHub'da "Create" ile onayla.
3. **Gönderim:** Mail ile kabul eden ilanlarda (Gmail secret'ları yoksa) sitede **Gmail'de aç** ile maili kendin gönderirsin. Greenhouse, Lever, Ashby, Workable, Personio, SmartRecruiters,
   Recruitee, Teamtailor, JOIN ve BambooHR formları arka planda doldurulup gönderilir. Zorunlu bir alan doldurulamazsa,
   CAPTCHA, giriş ekranı ya da desteklenmeyen bir portal çıkarsa **göndermez**, "elle tamamla" diye bildirir.
   Sonuç issue'ya yorum olarak düşer, sitede de durum görünür.

Gerekli secret'lar (Settings → Secrets and variables → Actions):
- `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`: mail başvuruları için (uygulama şifresi, normal şifre değil)
- `APPLICANT_JSON`: formlardaki kişisel bilgiler, ör. `{"first_name":"Anıl","last_name":"Kuş","email":"...","phone":"...","city":"Yozgat","country":"Turkey","sponsorship":"Yes","work_authorization":"No, I do not currently have an EU work permit","relocation":"Yes"}`
- `DOCS_PASSPHRASE`: `private/*.gpg` belgelerinin parolası
- `LLM_API_KEY`: ücretsiz Groq anahtarı (https://console.groq.com/keys). İsteğe bağlı değişkenler: `LLM_MODEL` (varsayılan `openai/gpt-oss-120b`), `LLM_BASE_URL` (başka bir OpenAI uyumlu servis için)

Formlardaki zorunlu gizlilik/veri işleme onay kutuları, sen paketi onayladığında senin adına işaretlenir.

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

### Mail ile başvuru

Şifre paylaşmadan çalışır. Sitede paketi aç → **Gmail'de aç**: alıcı, konu ve metin dolu bir mail penceresi açılır.
Pencere açıkken sağ altta userscript'in **Ekleri ekle** butonu çıkar. CV, ilana özel cover letter PDF'i ve ilanın istediği
diğer belgeleri ekler. Kontrol edip Gönder'e sen basarsın.

(İsteğe bağlı tam otomatik taslak: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `DOCS_PASSPHRASE` secret'ları ve
`scripts/encrypt_docs.sh` ile şifreli belgeler eklenirse `email-drafts.yml` taslağı kendisi oluşturur. Secret yoksa bu adım atlanır.)

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
