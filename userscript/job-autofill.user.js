// ==UserScript==
// @name         Job Agent Autofill
// @namespace    https://github.com/anilkus/job-agent
// @version      1.0.0
// @description  Fills job application forms from your Job Agent packages. Never submits, the last click is yours.
// @author       Anıl Kuş
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @connect      anilkus.github.io
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const SITE = "https://anilkus.github.io/job-agent/";

  // Personal details live only in your browser (Tampermonkey storage), never in the public repo.
  const DEFAULTS = {
    first_name: "Anıl", last_name: "Kuş", email: "", phone: "",
    city: "", country: "Turkey",
    linkedin: "https://www.linkedin.com/in/anil-kus/", github: "https://github.com/anilkus",
    website: "https://anilkus.github.io/", orcid: "0000-0002-5964-3727",
    scholar: "https://scholar.google.com/citations?user=YUCnGLkAAAAJ&hl=tr",
    salary: "", notice_period: "", work_authorization: "", sponsorship: "",
    relocation: "Yes", start_date: "", heard_from: "LinkedIn",
    degree: "PhD candidate (MSc in Computer Engineering)", university: "Mersin University",
  };
  const me = () => Object.assign({}, DEFAULTS, GM_getValue("me", {}));

  GM_registerMenuCommand("Job Agent: kişisel bilgileri düzenle", () => {
    const cur = me();
    const edited = prompt("Kişisel bilgiler (JSON). Sadece bu tarayıcıda saklanır.", JSON.stringify(cur, null, 1));
    if (!edited) return;
    try { GM_setValue("me", JSON.parse(edited)); alert("Kaydedildi."); } catch { alert("JSON hatalı, kaydedilmedi."); }
  });

  // ---------- helpers ----------
  const get = url => new Promise((ok, fail) => GM_xmlhttpRequest({
    method: "GET", url: url + "?t=" + Date.now(),
    onload: r => { try { ok(JSON.parse(r.responseText)); } catch (e) { fail(e); } }, onerror: fail,
  }));

  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) &&
    getComputedStyle(el).visibility !== "hidden";

  function labelOf(el) {
    const bits = [];
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) bits.push(l.innerText || l.textContent); }
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) bits.push(n.innerText || n.textContent); });
    bits.push(el.getAttribute("aria-label"), el.placeholder, el.name, el.id, el.getAttribute("autocomplete"));
    const wrap = el.closest("label");
    if (wrap) bits.push(wrap.innerText || wrap.textContent);
    if (bits.filter(Boolean).join("").length < 4) {
      // Fall back to text just above the field in its container.
      let p = el.parentElement;
      for (let i = 0; i < 3 && p; i++, p = p.parentElement) {
        const t = (p.innerText || p.textContent || "").trim();
        if (t && t.length < 300) { bits.push(t); break; }
      }
    }
    return bits.filter(Boolean).join(" | ").toLowerCase().replace(/\s+/g, " ");
  }

  function setValue(el, value) {
    if (el.tagName === "SELECT") {
      const v = String(value).toLowerCase();
      const opt = [...el.options].find(o => o.text.toLowerCase() === v) ||
                  [...el.options].find(o => v && o.text.toLowerCase().includes(v));
      if (!opt) return false;
      el.value = opt.value;
    } else {
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value); // React/Vue friendly
    }
    ["input", "change", "blur"].forEach(t => el.dispatchEvent(new Event(t, { bubbles: true })));
    return true;
  }

  const mark = (el, color) => { el.style.outline = `2px solid ${color}`; el.style.outlineOffset = "1px"; };

  const words = s => new Set((s || "").toLowerCase().match(/[a-zçğıöşü]{4,}/g) || []);
  function bestQuestion(label, questions) {
    const L = words(label); let best = null, bestScore = 0;
    for (const q of questions) {
      const Q = words(q.question); let hit = 0; Q.forEach(w => L.has(w) && hit++);
      const s = Q.size ? hit / Q.size : 0;
      if (s > bestScore) { best = q; bestScore = s; }
    }
    return bestScore >= 0.45 ? best.answer : null;
  }

  // ---------- field rules: first match wins ----------
  function rules(p, pkg) {
    const a = pkg.answers || {};
    const full = `${p.first_name} ${p.last_name}`;
    return [
      [/first.?name|given.?name|vorname|\bad[ıi]\b|prénom|nombre/, p.first_name],
      [/last.?name|family.?name|surname|nachname|soyad|apellido/, p.last_name],
      [/full.?name|^name\b|your name|\bname\b(?!.*(company|school|university|reference|manager))/, full],
      [/e-?mail/, p.email],
      [/phone|mobile|telefon|tel\b/, p.phone],
      [/linkedin/, p.linkedin],
      [/github/, p.github],
      [/orcid/, p.orcid],
      [/scholar/, p.scholar],
      [/website|portfolio|homepage|personal.?(site|url)|other.?(link|url)/, p.website],
      [/\bcity\b|stadt|şehir|current location|where are you (based|located)/, p.city],
      [/country|land\b|ülke/, p.country],
      [/salary|compensation|gehalt|ücret|pay expectation/, p.salary],
      [/notice.?period|kündigungsfrist|earliest start|start date|available from|verfügbar/, p.notice_period || p.start_date],
      [/sponsor/, p.sponsorship],
      [/work.?(permit|authori[sz])|right to work|arbeitserlaubnis|visa/, p.work_authorization],
      [/relocat/, p.relocation],
      [/how did you (hear|find)|where did you (hear|find)|source/, p.heard_from],
      [/highest degree|degree|abschluss/, p.degree],
      [/university|school|hochschule/, p.university],
      [/cover.?letter|motivation|anschreiben|letter of interest|statement of interest/, pkg.cover_letter],
      [/why.*(this|the) (role|position|job)|why are you interested|interest in (this|the)/, a.why_this_role || pkg.short_pitch],
      [/why.*(us|company|organi[sz]ation|join|work (at|for|with))/, a.why_this_organisation],
      [/research (interest|statement|agenda)/, a.research_interests],
      [/experience|background|qualif/, a.relevant_experience],
      [/additional|anything else|other information|comments/, a.additional_information],
      [/summary|about you|introduce|tell us about yourself|profile/, pkg.short_pitch],
    ];
  }

  function fill(pkg) {
    const p = me();
    const R = rules(p, pkg);
    const fields = [...document.querySelectorAll("input, textarea, select")].filter(el =>
      visible(el) && !el.disabled && !el.readOnly &&
      !["hidden", "submit", "button", "checkbox", "radio", "password", "search", "image", "reset"].includes(el.type));

    let filled = 0, todo = 0, files = 0;
    for (const el of fields) {
      if (el.type === "file") { mark(el, "#d98b00"); files++; continue; }
      if (el.value && el.value.trim() && el.tagName !== "SELECT") continue; // keep what is already there
      const label = labelOf(el);
      let value = null;
      if (el.tagName === "TEXTAREA") value = bestQuestion(label, pkg.custom_questions || []);
      if (!value) for (const [re, v] of R) { if (re.test(label)) { value = v; break; } }
      if (el.type === "email") value = p.email;
      if (el.type === "tel") value = p.phone;
      if (el.type === "url" && !value) value = p.linkedin;
      // Long answers only go into textareas, not one-line inputs like "years of experience".
      if (value && el.tagName === "INPUT" && String(value).length > 200) value = null;

      if (value && setValue(el, value)) { mark(el, "#2f9e6e"); filled++; }
      else if (el.required || el.getAttribute("aria-required") === "true") { mark(el, "#d98b00"); todo++; }
    }
    return { filled, todo, files };
  }

  // ---------- panel ----------
  function panel(pkgList) {
    const box = document.createElement("div");
    box.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#1f5c4a;color:#fff;" +
      "font:13px/1.4 system-ui,sans-serif;border-radius:10px;padding:10px 12px;box-shadow:0 6px 24px rgba(0,0,0,.25);max-width:320px";
    const here = location.href.split(/[?#]/)[0];
    const match = pkgList.find(x => x.url && here.startsWith(x.url.split(/[?#]/)[0])) ||
                  pkgList.find(x => x.url && new URL(x.url).hostname === location.hostname);
    box.innerHTML = `
      <div style="font-weight:600;margin-bottom:6px">Job Agent</div>
      <select style="width:100%;margin-bottom:8px;color:#111;border-radius:6px;padding:4px">
        ${pkgList.map(x => `<option value="${x.id}" ${match && match.id === x.id ? "selected" : ""}>
          ${(x.company || "").slice(0, 22)} · ${(x.title || "").slice(0, 30)}</option>`).join("")}
      </select>
      <div style="display:flex;gap:6px">
        <button data-act="fill" style="flex:1;padding:6px;border:0;border-radius:6px;cursor:pointer">Formu doldur</button>
        <button data-act="x" style="padding:6px 10px;border:0;border-radius:6px;cursor:pointer">×</button>
      </div>
      <div data-msg style="margin-top:8px;opacity:.9"></div>`;
    box.querySelector('[data-act="x"]').onclick = () => box.remove();
    box.querySelector('[data-act="fill"]').onclick = async () => {
      const msg = box.querySelector("[data-msg]");
      const p = me();
      if (!p.email) { msg.textContent = "Önce Tampermonkey menüsünden e-posta ve telefonu gir."; return; }
      msg.textContent = "Yükleniyor...";
      try {
        const pkg = await get(`${SITE}data/applications/${box.querySelector("select").value}.json`);
        const r = fill(pkg);
        msg.innerHTML = `${r.filled} alan dolduruldu (yeşil).` +
          (r.todo ? `<br>${r.todo} zorunlu alan sende (turuncu).` : "") +
          (r.files ? `<br>CV/dosya yüklemesini sen yap.` : "") +
          `<br><b>Her şeyi kontrol et, sonra Gönder'e bas.</b>`;
      } catch (e) { msg.textContent = "Paket alınamadı: " + e; }
    };
    document.body.appendChild(box);
  }

  // Show the panel only on pages that look like an application form.
  function looksLikeForm() {
    const inputs = [...document.querySelectorAll("input, textarea")].filter(visible);
    return inputs.length >= 3 && inputs.some(i => i.type === "email" || /mail/i.test(i.name + i.id));
  }

  let shown = false;
  async function maybeShow() {
    if (shown || !looksLikeForm()) return;
    shown = true;
    try {
      const list = await get(`${SITE}data/applications/index.json`);
      if (list.length) panel(list);
    } catch { /* site not reachable, stay quiet */ }
  }
  maybeShow();
  // Single-page apps render forms late.
  const obs = new MutationObserver(() => maybeShow());
  obs.observe(document.documentElement, { childList: true, subtree: true });
  setTimeout(() => obs.disconnect(), 60000);
})();
