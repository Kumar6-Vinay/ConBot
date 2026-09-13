/* =========================================================
   ConBOT — client
   Backend contract: POST /ask {prompt, model} -> {answer, web_used, sources}
   The backend is single-turn, so nothing here pretends to carry context.
========================================================= */

const API_URL = 'https://llama-chatbot-qb2c.onrender.com/ask';
const MODEL = 'qwen3:14b';
const TIMEOUT_MS = 120000;   // server may cold-start on a free dyno
const WAKE_HINT_MS = 7000;   // tell the user why it is slow

const $ = (id) => document.getElementById(id);

const bar = $('bar');
const hero = $('hero');
const thread = $('thread');
const input = $('input');
const send = $('send');

let pending = null; // AbortController while a request is in flight

/* =========================================================
   Markdown — escape first, then format. Never raw innerHTML.
========================================================= */

function esc(s) {
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function inline(s) {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

function markdown(raw) {
  const src = esc(raw.trim());
  const blocks = src.split(/```/);
  let out = '';

  blocks.forEach((block, i) => {
    // odd indexes are fenced code
    if (i % 2 === 1) {
      const body = block.replace(/^[a-zA-Z0-9+-]*\n/, '');
      out += `<pre><code>${body.replace(/\n$/, '')}</code></pre>`;
      return;
    }

    let list = null;
    block.split('\n').forEach((line) => {
      const t = line.trim();

      if (!t) { if (list) { out += `</${list}>`; list = null; } return; }

      const bullet = t.match(/^[-*]\s+(.*)/);
      const number = t.match(/^\d+[.)]\s+(.*)/);
      const head = t.match(/^#{1,6}\s+(.*)/);

      if (bullet || number) {
        const want = bullet ? 'ul' : 'ol';
        if (list !== want) { if (list) out += `</${list}>`; out += `<${want}>`; list = want; }
        out += `<li>${inline((bullet || number)[1])}</li>`;
        return;
      }

      if (list) { out += `</${list}>`; list = null; }
      out += head ? `<h3>${inline(head[1])}</h3>` : `<p>${inline(t)}</p>`;
    });

    if (list) out += `</${list}>`;
  });

  return out;
}

/* =========================================================
   Rendering
========================================================= */

function startThread() {
  if (!hero.classList.contains('gone')) hero.classList.add('gone');
}

function addYou(text) {
  startThread();
  const turn = document.createElement('div');
  turn.className = 'turn you';
  const body = document.createElement('div');
  body.className = 'text';
  body.textContent = text;            // user text is never parsed
  turn.appendChild(body);
  thread.appendChild(turn);
  toBottom();
}

function addThinking() {
  const turn = document.createElement('div');
  turn.className = 'turn bot';
  turn.innerHTML = '<div class="dots"><i></i><i></i><i></i></div>';
  thread.appendChild(turn);
  toBottom();

  const hint = setTimeout(() => {
    const p = document.createElement('p');
    p.className = 'waking';
    p.textContent = 'Waking the server up — first question of the day takes a moment.';
    turn.appendChild(p);
    toBottom();
  }, WAKE_HINT_MS);

  return { turn, hint };
}

function fillAnswer(turn, answer, sources) {
  turn.innerHTML = '';

  const body = document.createElement('div');
  body.className = 'text';
  body.innerHTML = markdown(answer);   // escaped above
  turn.appendChild(body);

  if (sources && sources.length) {
    const wrap = document.createElement('div');
    wrap.className = 'sources';
    sources.forEach((s) => {
      const a = document.createElement('a');
      a.className = 'source';
      a.textContent = s.title || s.url;
      a.href = /^https?:\/\//.test(s.url) ? s.url : `https://${s.url}`;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      wrap.appendChild(a);
    });
    turn.appendChild(wrap);
  }

  const acts = document.createElement('div');
  acts.className = 'acts';
  const copy = document.createElement('button');
  copy.className = 'act';
  copy.type = 'button';
  copy.textContent = 'Copy';
  copy.onclick = () => {
    navigator.clipboard.writeText(answer).then(() => {
      copy.textContent = 'Copied';
      setTimeout(() => { copy.textContent = 'Copy'; }, 1600);
    });
  };
  acts.appendChild(copy);
  turn.appendChild(acts);

  toBottom();
}

function fillNotice(turn, message) {
  turn.innerHTML = '';
  const p = document.createElement('div');
  p.className = 'text notice';
  p.textContent = message;
  turn.appendChild(p);
  toBottom();
}

function toBottom() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
}

/* =========================================================
   Sending
========================================================= */

async function ask() {
  if (pending) { pending.abort(); return; }

  const text = input.value.trim();
  if (!text) return;

  addYou(text);
  input.value = '';
  grow();
  lock(true);

  const { turn, hint } = addThinking();

  pending = new AbortController();
  const timer = setTimeout(() => pending && pending.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: text, model: MODEL }),
      signal: pending.signal,
    });

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      fillNotice(turn, detail.detail || `The server returned ${res.status}. Try again in a moment.`);
    } else {
      const data = await res.json();
      fillAnswer(turn, data.answer || '', data.sources);
    }
  } catch (err) {
    fillNotice(
      turn,
      err.name === 'AbortError'
        ? 'Stopped.'
        : 'Could not reach ConBOT. Check your connection and try again.'
    );
  } finally {
    clearTimeout(timer);
    clearTimeout(hint);
    pending = null;
    lock(false);
    input.focus();
  }
}

function lock(busy) {
  send.disabled = busy ? false : !input.value.trim();
  send.setAttribute('aria-label', busy ? 'Stop' : 'Send');
  send.classList.toggle('stop', busy);
  send.innerHTML = busy
    ? '<svg viewBox="0 0 24 24" width="20" height="20"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>'
    : '<svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
}

/* =========================================================
   Composer behaviour
========================================================= */

function grow() {
  input.style.height = 'auto';
  input.style.height = `${input.scrollHeight}px`;
}

input.addEventListener('input', () => {
  grow();
  if (!pending) send.disabled = !input.value.trim();
});

input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); }
});

send.addEventListener('click', ask);

document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    input.value = chip.textContent;
    grow();
    send.disabled = false;
    ask();
  });
});

/* =========================================================
   Chrome
========================================================= */

$('newChat').addEventListener('click', () => {
  if (pending) pending.abort();
  thread.innerHTML = '';
  hero.classList.remove('gone');
  input.value = '';
  grow();
  send.disabled = true;
  window.scrollTo({ top: 0 });
});

const saved = localStorage.getItem('conbot-theme');
if (saved) document.body.classList.add(saved);

$('themeToggle').addEventListener('click', () => {
  const dark = getComputedStyle(document.body).backgroundColor === 'rgb(0, 0, 0)';
  document.body.classList.remove('dark', 'light');
  document.body.classList.add(dark ? 'light' : 'dark');
  localStorage.setItem('conbot-theme', dark ? 'light' : 'dark');
});

window.addEventListener('scroll', () => {
  bar.classList.toggle('scrolled', window.scrollY > 4);
}, { passive: true });

input.focus();
