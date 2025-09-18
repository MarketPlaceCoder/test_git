// If you serve the frontend on GitHub Pages under /test_git/ and run the backend locally,
// keep localhost during development. Later, change to your cloud backend URL.
const API = (location.origin.includes("localhost:8080") ? "http://localhost:8000" : "http://localhost:8000");

const $ = (sel) => document.querySelector(sel);
const statusEl = $("#status");
const verdictEl = $("#verdict");
const modulesEl = $("#modules");
const jsonOut = $("#jsonOut");

async function run() {
  const ticker = $("#ticker").value.trim().toUpperCase();
  if(!ticker) return;

  statusEl.textContent = "Running… (fetching only free, public data)";
  verdictEl.innerHTML = "";
  modulesEl.innerHTML = "";
  jsonOut.textContent = "";

  try {
    const res = await fetch(`${API}/api/research?ticker=${encodeURIComponent(ticker)}`);
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const overall = data.overall || {};
    verdictEl.innerHTML = `
      <h2>Final Verdict</h2>
      <div class="kv">
        <div>As of</div><div>${new Date(data.as_of).toLocaleString()}</div>
        <div>Ticker</div><div>${data.ticker}</div>
        <div>Overall Score</div><div class="score">${overall.score ?? "?"}</div>
        <div>Rating</div><div class="rating badge">${overall.rating ?? "?"}</div>
        <div>Weights</div><div>Financial 65% · Exogenous 15% · Behavioral 20%</div>
      </div>
    `;

    const m1 = data.module_1_facts || {};
    const m2 = data.module_2_financial_score || {};
    const m3 = data.module_3_exogenous_score || {};
    const m4 = data.module_4_behavioral_score || {};

    modulesEl.append(childCard("Module 1 — Facts", renderFacts(m1)));
    modulesEl.append(childCard("Module 2 — Financial", renderScore(m2.score, m2.detail)));
    modulesEl.append(childCard("Module 3 — Exogenous", renderScore(m3.score_rescaled_0to100, m3.detail)));
    modulesEl.append(childCard("Module 4 — Behavioral", renderScore(m4.score, m4.detail)));

    jsonOut.textContent = JSON.stringify(data, null, 2);
    statusEl.textContent = "Done.";
  } catch (e) {
    console.error(e);
    statusEl.textContent = `Error: ${e.message}`;
  }
}

function childCard(title, innerHTML){
  const el = document.createElement("section");
  el.className = "card";
  el.innerHTML = `<h2>${title}</h2>${innerHTML}`;
  return el;
}

function renderFacts(m1){
  const company = m1.company_info || {};
  const corp = (m1.corporate_actions || []).map(x => `<li>${x.item} — ${srcList(x.sources)}</li>`).join("") || "<li>No parsed items</li>";
  const leads = m1.leadership ? `<li>${m1.leadership.change} — ${srcList(m1.leadership.sources)}</li>` : "";
  const divs = m1.dividends ? `<li>Dividends: ${m1.dividends.status} — ${srcList(m1.dividends.sources)}</li>` : "";
  const edgar = linkOrRestricted(m1.edgar_filings);
  const news = (m1.news_headlines || []).slice(0,8).map(n => `<li><a href="${n.link}" target="_blank" rel="noopener">${n.title}</a></li>`).join("");

  return `
    <div class="kv">
      <div>Company</div><div>${company.longName || company.shortName || "—"}</div>
      <div>Sector/Industry</div><div>${company.sector || "—"} / ${company.industry || "—"}</div>
      <div>Exchange</div><div>${company.exchange || "—"}</div>
      <div>Date Window</div><div>${(m1.window||{}).from} → ${(m1.window||{}).to}</div>
    </div>
    <h3>Corporate Actions</h3>
    <ul>${corp}</ul>
    <h3>Leadership</h3>
    <ul>${leads || "<li>—</li>"}</ul>
    <h3>Dividends / Splits</h3>
    <ul>${divs || "<li>—</li>"}</ul>
    <h3>Regulatory Filings</h3>
    <p>${edgar}</p>
    <h3>Top Headlines</h3>
    <ul>${news}</ul>
  `;
}

function linkOrRestricted(x){
  if(!x) return "—";
  if(x["restricted; visit link"]) {
    const u = x["restricted; visit link"];
    return `restricted; visit link: <a href="${u}" target="_blank" rel="noopener">${u}</a>`;
    }
  if(x.url) {
    return `<a href="${x.url}" target="_blank" rel="noopener">${x.url}</a>`;
  }
  return "See source page";
}

function srcList(arr){
  if(!arr || !arr.length) return "";
  return arr.map(u => `<a href="${u}" target="_blank" rel="noopener">source</a>`).join(" · ");
}

function renderScore(score, detail){
  const meta = detail ? `<pre>${escapeHtml(JSON.stringify(detail, null, 2))}</pre>` : "";
  return `<div class="score">${score ?? "—"}</div>${meta}`;
}

function escapeHtml(s){ return s.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m])); }

// Install prompt
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const btn = document.getElementById('installBtn');
  btn.hidden = false;
  btn.onclick = async () => {
    btn.hidden = true;
    if(deferredPrompt){
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
    }
  };
});

document.getElementById("runBtn").addEventListener("click", run);
document.getElementById("downloadJson").addEventListener("click", ()=>{
  const blob = new Blob([jsonOut.textContent || "{}"], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `research_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
});

window.addEventListener("load", ()=>{
  if('serviceWorker' in navigator){
    navigator.serviceWorker.register('./service-worker.js');
  }
});

