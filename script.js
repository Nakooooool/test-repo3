/* ═══════════════════════════════════════
   Glimpse-web  |  script.js
   ═══════════════════════════════════════ */

const API = '';           // empty = same origin (Flask serves both)
let activeCat   = 'general';
let bookmarks   = [];
let focusedArt  = null;   // article currently open in modal
let searchTimer = null;

/* ── DOM references ─────────────────── */
const grid        = document.getElementById('grid');
const emptyEl     = document.getElementById('empty');
const tabsEl      = document.getElementById('tabs');
const tabInk      = document.getElementById('tabInk');
const searchToggle= document.getElementById('searchToggle');
const searchInput = document.getElementById('searchInput');
const themeBtn    = document.getElementById('themeBtn');
const themeIcon   = document.getElementById('themeIcon');
const toastEl     = document.getElementById('toast');
const goTopBtn    = document.getElementById('goTop');
const overlay     = document.getElementById('overlay');
const modalX      = document.getElementById('modalX');
const modalImg    = document.getElementById('modalImg');
const modalSrc    = document.getElementById('modalSrc');
const modalDate   = document.getElementById('modalDate');
const modalTitle  = document.getElementById('modalTitle');
const modalDesc   = document.getElementById('modalDesc');
const modalLink   = document.getElementById('modalLink');
const modalSave   = document.getElementById('modalSave');

/* ── Bootstrap ──────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  applyStoredTheme();
  fetchBookmarks().then(() => fetchNews('general'));
  positionInk(document.querySelector('.tab.active'));
});

/* ── News fetch ─────────────────────── */
async function fetchNews(cat) {
  activeCat = cat;
  showSkeletons();
  try {
    const endpoint = cat === 'saved'
      ? `${API}/api/bookmarks`
      : `${API}/api/news?category=${cat}`;
    const res  = await fetch(endpoint);
    const data = await res.json();
    renderCards(data.articles || []);
  } catch {
    showToast('⚠ Could not load stories');
    grid.innerHTML = '';
    emptyEl.hidden = false;
  }
}

async function runSearch(q) {
  if (!q.trim()) { fetchNews(activeCat); return; }
  showSkeletons();
  try {
    const res  = await fetch(`${API}/api/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderCards(data.articles || []);
  } catch {
    showToast('⚠ Search failed — try again');
  }
}

/* ── Render cards ───────────────────── */
function renderCards(articles) {
  grid.innerHTML = '';
  emptyEl.hidden = true;
  if (!articles.length) { emptyEl.hidden = false; return; }
  articles.forEach((art, i) => grid.appendChild(makeCard(art, i)));
}

function makeCard(art, i) {
  const saved = isSaved(art.id);
  const date  = fmtDate(art.publishedAt);
  const card  = document.createElement('div');
  card.className = 'card';
  card.style.animationDelay = `${i * 0.07}s`;

  card.innerHTML = `
    <div class="card-img-wrap">
      ${art.image
        ? `<img class="card-img" src="${art.image}" alt="" loading="lazy"
               onerror="this.parentElement.innerHTML='<div class=card-no-img>◈</div>'">`
        : `<div class="card-no-img">◈</div>`}
      <button class="card-bm ${saved ? 'on' : ''}"
              data-id="${esc(art.id)}" aria-label="Bookmark">
        ${saved ? '♥' : '♡'}
      </button>
    </div>
    <div class="card-body">
      <div class="card-meta">
        <span class="card-src">${esc(art.source)}</span>
        ${date ? `<span class="card-dot"></span><span class="card-date">${date}</span>` : ''}
      </div>
      <h3 class="card-title">${esc(art.title)}</h3>
      <p  class="card-desc">${esc(art.description || '')}</p>
    </div>`;

  /* Bookmark button — stop event bubbling */
  card.querySelector('.card-bm').addEventListener('click', e => {
    e.stopPropagation();
    toggleBookmark(art, e.currentTarget);
  });

  /* Open modal */
  card.addEventListener('click', () => openModal(art));
  return card;
}

/* ── Skeletons ──────────────────────── */
function showSkeletons(n = 9) {
  grid.innerHTML = '';
  emptyEl.hidden = true;
  for (let i = 0; i < n; i++) {
    const s = document.createElement('div');
    s.className = 'card skeleton';
    s.innerHTML = `
      <div class="card-img-wrap"></div>
      <div class="card-body">
        <div class="skel-ln s"></div>
        <div class="skel-ln t"></div>
        <div class="skel-ln"></div>
        <div class="skel-ln s"></div>
      </div>`;
    grid.appendChild(s);
  }
}

/* ── Bookmarks ──────────────────────── */
async function fetchBookmarks() {
  try {
    const res  = await fetch(`${API}/api/bookmarks`);
    const data = await res.json();
    bookmarks  = data.articles || [];
  } catch { bookmarks = []; }
}

function isSaved(id) {
  return bookmarks.some(b => b.id === id);
}

async function toggleBookmark(art, btn) {
  /* Pulse animation */
  btn.classList.add('pop');
  setTimeout(() => btn.classList.remove('pop'), 350);

  if (isSaved(art.id)) {
    /* Remove */
    try {
      await fetch(`${API}/api/bookmarks/${encodeURIComponent(art.id)}`, { method: 'DELETE' });
      bookmarks = bookmarks.filter(b => b.id !== art.id);
      btn.classList.remove('on'); btn.textContent = '♡';
      showToast('🗑 Removed from Glimpse');
      syncModalSaveBtn(art.id, false);
      if (activeCat === 'saved') fetchNews('saved');
    } catch { showToast('⚠ Could not remove'); }
  } else {
    /* Save */
    try {
      const res  = await fetch(`${API}/api/bookmarks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(art),
      });
      const data = await res.json();
      bookmarks  = data.articles || [];
      btn.classList.add('on'); btn.textContent = '♥';
      showToast('♥ Saved to Glimpse!');
      syncModalSaveBtn(art.id, true);
    } catch { showToast('⚠ Could not save'); }
  }
}

function syncModalSaveBtn(id, saved) {
  if (!focusedArt || focusedArt.id !== id) return;
  modalSave.textContent = saved ? '♥ Saved' : '♡ Save';
  modalSave.classList.toggle('on', saved);
}

/* ── Modal ──────────────────────────── */
function openModal(art) {
  focusedArt = art;
  const saved = isSaved(art.id);

  if (art.image) { modalImg.src = art.image; modalImg.style.display = 'block'; }
  else           { modalImg.style.display = 'none'; }

  modalSrc.textContent   = art.source  || '';
  modalDate.textContent  = fmtDate(art.publishedAt, true);
  modalTitle.textContent = art.title   || '';
  modalDesc.textContent  = art.description || art.content || 'No description available.';
  modalLink.href         = art.url     || '#';
  modalSave.textContent  = saved ? '♥ Saved' : '♡ Save';
  modalSave.classList.toggle('on', saved);

  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  overlay.classList.remove('open');
  document.body.style.overflow = '';
  focusedArt = null;
}

modalX.addEventListener('click', closeModal);
overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

modalSave.addEventListener('click', () => {
  if (!focusedArt) return;
  const btn = grid.querySelector(`.card-bm[data-id="${CSS.escape(focusedArt.id)}"]`);
  toggleBookmark(focusedArt, btn || modalSave);
});

/* ── Tabs ───────────────────────────── */
tabsEl.addEventListener('click', e => {
  const tab = e.target.closest('.tab');
  if (!tab) return;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  positionInk(tab);
  fetchNews(tab.dataset.cat);
  /* Clear search */
  searchInput.value = '';
  searchInput.classList.remove('open');
});

function positionInk(tab) {
  if (!tab) return;
  const tRect = tab.getBoundingClientRect();
  const pRect = tabsEl.getBoundingClientRect();
  tabInk.style.left  = (tRect.left - pRect.left + tabsEl.scrollLeft) + 'px';
  tabInk.style.width = tRect.width + 'px';
}

window.addEventListener('resize', () => positionInk(document.querySelector('.tab.active')));

/* ── Search ─────────────────────────── */
searchToggle.addEventListener('click', () => {
  const opening = searchInput.classList.toggle('open');
  if (opening) { setTimeout(() => searchInput.focus(), 60); }
  else { searchInput.value = ''; fetchNews(activeCat); }
});

searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(searchInput.value), 500); /* 500ms debounce */
});

searchInput.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    searchInput.classList.remove('open');
    searchInput.value = '';
    fetchNews(activeCat);
  }
});

/* ── Dark / light mode ──────────────── */
function applyStoredTheme() {
  const dark = localStorage.getItem('glimpse-dark') === '1';
  if (dark) { document.body.classList.add('dark'); themeIcon.textContent = '☾'; }
}

themeBtn.addEventListener('click', () => {
  themeBtn.classList.add('spinning');
  setTimeout(() => themeBtn.classList.remove('spinning'), 450);
  const isDark = document.body.classList.toggle('dark');
  themeIcon.textContent = isDark ? '☾' : '☀';
  localStorage.setItem('glimpse-dark', isDark ? '1' : '0');
});

/* ── Toast ──────────────────────────── */
let toastTimer;
function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2500);
}

/* ── Scroll-to-top ──────────────────── */
window.addEventListener('scroll', () => {
  goTopBtn.classList.toggle('on', window.scrollY > 300);
});
goTopBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

/* ── Utility ────────────────────────── */
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

function fmtDate(iso, long = false) {
  if (!iso) return '';
  const d = new Date(iso);
  return long
    ? d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
