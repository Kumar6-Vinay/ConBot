/* =========================================================
   ConBOT — client

   POST /stream {prompt, model, history, timezone, language}
     -> SSE events: {type:"sources"|"delta"|"error"|"done"}

   History lives here, in memory, for this tab only. The server is
   stateless: every request replays the conversation.
========================================================= */

const API_BASE = 'https://llama-chatbot-qb2c.onrender.com';
const MODEL = 'qwen3:14b';
const TIMEOUT_MS = 120000;   // free dyno can cold-start
const WAKE_HINT_MS = 7000;
const MAX_TURNS = 20;        // trimmed again server-side

const $ = (id) => document.getElementById(id);

const bar = $('bar');
const hero = $('hero');
const thread = $('thread');
const dock = $('dock');
const dockSlot = $('dockSlot');
const composer = $('heroComposer');
const input = $('input');
const send = $('send');

let history = [];
let pending = null;
let stuckToBottom = true;

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
    if (i % 2 === 1) {                      // fenced code
      const body = block.replace(/^[a-zA-Z0-9+-]*\n/, '');
      out += '<pre><code>' + body.replace(/\n$/, '') + '</code></pre>';
      return;
    }

    let list = null;
    block.split('\n').forEach((line) => {
      const t = line.trim();
      if (!t) { if (list) { out += '</' + list + '>'; list = null; } return; }

      const bullet = t.match(/^[-*]\s+(.*)/);
      const number = t.match(/^\d+[.)]\s+(.*)/);
      const head = t.match(/^#{1,6}\s+(.*)/);

      if (bullet || number) {
        const want = bullet ? 'ul' : 'ol';
        if (list !== want) { if (list) out += '</' + list + '>'; out += '<' + want + '>'; list = want; }
        out += '<li>' + inline((bullet || number)[1]) + '</li>';
        return;
      }

      if (list) { out += '</' + list + '>'; list = null; }
      out += head ? '<h3>' + inline(head[1]) + '</h3>' : '<p>' + inline(t) + '</p>';
    });

    if (list) out += '</' + list + '>';
  });

  return out;
}

/* =========================================================
   Opening state -> conversation
   The composer is one element that moves, so the change reads as the
   page rearranging rather than two different inputs swapping.
========================================================= */

function startThread() {
  if (dock.hidden) {
    dockSlot.appendChild(composer);       // same node, new home
    dock.hidden = false;
    hero.classList.add('gone');
    document.body.classList.add('chatting');
  }
}

function resetToHero() {
  hero.querySelector('.hero-inner').insertBefore(composer, $('chips'));
  dock.hidden = true;
  hero.classList.remove('gone');
  document.body.classList.remove('chatting');
}

/* =========================================================
   Rendering
========================================================= */

function addYou(text) {
  startThread();
  const turn = document.createElement('div');
  turn.className = 'turn you';
  const body = document.createElement('div');
  body.className = 'text';
  body.textContent = text;                // user text is never parsed
  turn.appendChild(body);
  thread.appendChild(turn);
  toBottom();
}

function addAnswerShell() {
  const turn = document.createElement('div');
  turn.className = 'turn bot';

  const body = document.createElement('div');
  body.className = 'text';
  body.innerHTML = '<div class="dots"><i></i><i></i><i></i></div>';
  turn.appendChild(body);

  thread.appendChild(turn);
  toBottom();

  const hint = setTimeout(() => {
    if (!turn.dataset.started) {
      const p = document.createElement('p');
      p.className = 'waking';
      p.textContent = 'Waking the server up — the first question of the day takes a moment.';
      turn.appendChild(p);
      toBottom();
    }
  }, WAKE_HINT_MS);

  return { turn, body, hint };
}

function renderSources(turn, sources) {
  if (!sources || !sources.length) return;
  const wrap = document.createElement('div');
  wrap.className = 'sources';
  sources.forEach((s) => {
    const a = document.createElement('a');
    a.className = 'source';
    a.textContent = s.title || s.url;
    a.href = /^https?:\/\//.test(s.url) ? s.url : 'https://' + s.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    wrap.appendChild(a);
  });
  turn.appendChild(wrap);
}

/* Share beats copy on a phone: the next thing people do with a useful
   answer is forward it. Falls back to the clipboard on desktop. */
function addActions(turn, getText) {
  const acts = document.createElement('div');
  acts.className = 'acts';

  const share = document.createElement('button');
  share.className = 'act';
  share.type = 'button';
  share.textContent = navigator.share ? 'Share' : 'Copy';
  share.onclick = async () => {
    const text = getText();
    if (navigator.share) {
      try { await navigator.share({ text: text }); } catch (e) { /* dismissed */ }
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      share.textContent = 'Copied';
      setTimeout(() => { share.textContent = 'Copy'; }, 1600);
    } catch (e) {
      share.textContent = 'Select and copy';
    }
  };

  acts.appendChild(share);
  turn.appendChild(acts);
}

function showNotice(body, message) {
  const p = document.createElement('p');
  p.className = 'notice';
  p.textContent = message;
  body.appendChild(p);
  toBottom();
}

function toBottom() {
  if (!stuckToBottom) return;
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'auto' });
}

/* =========================================================
   Where the user is — device settings only, no permission prompt
========================================================= */

function locale() {
  let timezone = null;
  try {
    timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch (e) { timezone = null; }
  return { timezone: timezone, language: navigator.language || null };
}

/* =========================================================
   Asking
========================================================= */

async function ask() {
  if (pending) { pending.abort(); return; }

  const text = input.value.trim();
  if (!text) return;

  addYou(text);
  input.value = '';
  grow();
  lock(true);
  stuckToBottom = true;

  const shell = addAnswerShell();
  const turn = shell.turn;
  const body = shell.body;
  const where = locale();

  pending = new AbortController();
  const timer = setTimeout(() => { if (pending) pending.abort(); }, TIMEOUT_MS);

  let answer = '';
  let frame = null;

  const paint = () => {
    frame = null;
    body.innerHTML = markdown(answer);
    toBottom();
  };

  try {
    const res = await fetch(API_BASE + '/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: text,
        model: MODEL,
        history: history.slice(-MAX_TURNS),
        timezone: where.timezone,
        language: where.language,
      }),
      signal: pending.signal,
    });

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      body.innerHTML = '';
      showNotice(body, detail.detail || 'The server returned ' + res.status + '. Try again shortly.');
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const step = await reader.read();
      if (step.done) break;

      buffer += decoder.decode(step.value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();                 // keep the partial line

      for (const line of lines) {
        if (line.indexOf('data: ') !== 0) continue;

        let event;
        try { event = JSON.parse(line.slice(6)); } catch (e) { continue; }

        if (event.type === 'sources') {
          turn.dataset.sources = JSON.stringify(event.sources);
        } else if (event.type === 'delta') {
          if (!turn.dataset.started) { turn.dataset.started = '1'; body.innerHTML = ''; }
          answer += event.text;
          if (!frame) frame = requestAnimationFrame(paint);
        } else if (event.type === 'error') {
          if (!turn.dataset.started) body.innerHTML = '';
          showNotice(body, event.detail);
        }
      }
    }

    if (frame) cancelAnimationFrame(frame);
    if (answer) {
      paint();
      history.push({ role: 'user', content: text });
      history.push({ role: 'assistant', content: answer });

      if (turn.dataset.sources) renderSources(turn, JSON.parse(turn.dataset.sources));
      addActions(turn, () => answer);
    }

  } catch (err) {
    if (frame) cancelAnimationFrame(frame);
    if (err.name === 'AbortError') {
      if (answer) { paint(); } else { body.innerHTML = ''; }
      showNotice(body, 'Stopped.');
    } else {
      if (!turn.dataset.started) body.innerHTML = '';
      showNotice(body, 'Could not reach ConBOT. Check your connection and try again.');
    }
  } finally {
    clearTimeout(timer);
    clearTimeout(shell.hint);
    pending = null;
    lock(false);
    input.focus();
  }
}

function lock(busy) {
  send.disabled = busy ? false : !input.value.trim();
  send.setAttribute('aria-label', busy ? 'Stop' : 'Send');
  send.innerHTML = busy
    ? '<svg viewBox="0 0 24 24" width="20" height="20"><rect x="7" y="7" width="10" height="10" rx="2.5" fill="currentColor" stroke="none"/></svg>'
    : '<svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
}

/* =========================================================
   Composer
========================================================= */

function grow() {
  input.style.height = 'auto';
  input.style.height = input.scrollHeight + 'px';
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
  history = [];
  thread.innerHTML = '';
  input.value = '';
  resetToHero();
  grow();
  send.disabled = true;
  window.scrollTo({ top: 0 });
  input.focus();
});

const saved = localStorage.getItem('conbot-theme');
if (saved) document.body.classList.add(saved);

$('themeToggle').addEventListener('click', () => {
  const dark = getComputedStyle(document.body).backgroundColor === 'rgb(0, 0, 0)';
  document.body.classList.remove('dark', 'light');
  document.body.classList.add(dark ? 'light' : 'dark');
  localStorage.setItem('conbot-theme', dark ? 'light' : 'dark');
});

/* Let the reader scroll up mid-answer without being yanked back down. */
window.addEventListener('scroll', () => {
  bar.classList.toggle('scrolled', window.scrollY > 4);
  const room = document.body.scrollHeight - window.scrollY - window.innerHeight;
  stuckToBottom = room < 120;
}, { passive: true });

input.focus();
