/* =========================================================
   ConBOT — client

   POST /stream {prompt, model, history, timezone, language}
     -> SSE events: {type:"sources"|"delta"|"clarify"|"followups"|
                     "truncated"|"error"|"done"}

   History lives here, in memory, for this tab only. The server is
   stateless: every request replays the conversation.
========================================================= */

const API_BASE = 'https://llama-chatbot-qb2c.onrender.com';
const MODEL = 'text';
const TIMEOUT_MS = 120000;   // free dyno can cold-start
const WAKE_HINT_MS = 7000;
const MAX_TURNS = 16;        // messages replayed; server keeps the last 8
const MAX_CHARS = 3000;      // per question, and per replayed message
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;   // matches the server's 4 MB cap

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
let attachedImage = null;   // base64 data URL for the NEXT question only

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

      if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) {
        if (list) { out += '</' + list + '>'; list = null; }
        out += '<hr>';
        return;
      }

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
  closeImageGenView();   // showing a thread always means the generator is done
  if (dock.hidden) {
    stopRotator();                          // the welcome is over
    dockSlot.appendChild(composer);         // same node, new home
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
  startRotator();                           // welcome again on a fresh chat
}

/* =========================================================
   Rendering
========================================================= */

function addYou(text, imageUrl) {
  startThread();
  const turn = document.createElement('div');
  turn.className = 'turn you';
  if (imageUrl) {
    const img = document.createElement('img');
    img.className = 'you-image';
    img.src = imageUrl;                    // data URL, never remote
    img.alt = 'Attached image';
    turn.appendChild(img);
  }
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
      p.textContent = 'Still working on your answer — this can take a few extra seconds.';
      turn.appendChild(p);
      turn._waking = p;
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

/* Ask one thing back when guessing would produce a wrong answer. The
   options are the answer — there is no prose above them. */
function renderClarify(turn, body, event) {
  turn.dataset.clarify = event.question;

  const q = document.createElement('p');
  q.className = 'ask-back';
  q.textContent = event.question;
  body.appendChild(q);

  const wrap = document.createElement('div');
  wrap.className = 'options';
  event.options.forEach((option) => {
    const b = document.createElement('button');
    b.className = 'option';
    b.type = 'button';
    b.textContent = option;
    b.onclick = () => {
    if (pending) return;
      wrap.remove();
      input.value = option;
      send.disabled = false;
      ask();
    };
    wrap.appendChild(b);
  });
  body.appendChild(wrap);
  toBottom();
}

/* Follow-ups are gaps this answer opened. Ignoring them costs nothing —
   they sit below the answer and never interrupt it. */
function renderFollowups(turn, questions) {
  if (!questions || !questions.length) return;

  const wrap = document.createElement('div');
  wrap.className = 'next';
  questions.forEach((q) => {
    const b = document.createElement('button');
    b.className = 'next-q';
    b.type = 'button';
    b.textContent = q;
    b.onclick = () => {
    if (pending) return;
      input.value = q;
      send.disabled = false;
      ask();
    };
    wrap.appendChild(b);
  });
  turn.appendChild(wrap);
  toBottom();
}

/* A long answer can hit the token cap mid-sentence. Say so plainly and let
   the reader pick it up — history makes "carry on" mean something now. */
function addContinue(turn) {
  const wrap = document.createElement('div');
  wrap.className = 'cut';

  const note = document.createElement('span');
  note.textContent = 'That answer was cut short.';

  const more = document.createElement('button');
  more.className = 'act';
  more.type = 'button';
  more.textContent = 'Continue';
  more.onclick = () => {
    if (pending) return;
    wrap.remove();
    input.value = 'Continue from where you stopped.';
    send.disabled = false;
    ask();
  };

  wrap.appendChild(note);
  wrap.appendChild(more);
  turn.appendChild(wrap);
  toBottom();
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

/* The server rejects oversized bodies and trims history anyway, so send
   only what it will use. Long answers are clipped here, never dropped. */
function outgoingHistory() {
  return history.slice(-MAX_TURNS).map((m) => ({
    role: m.role,
    content: m.content.length > MAX_CHARS ? m.content.slice(0, MAX_CHARS) : m.content,
  }));
}

/* FastAPI's validation errors put a list in `detail`; only show strings. */
function errorText(detail, status) {
  if (typeof detail === 'string' && detail) return detail;
  if (status === 422) return 'That message could not be sent. Try a shorter question.';
  if (status === 429) return 'Too many questions right now. Please wait a moment.';
  return 'The server returned ' + status + '. Try again shortly.';
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

function sendWith(prompt) {
  input.value = prompt;
  grow();
  return ask();
}

async function ask() {
  if (pending) { pending.abort(); return; }

  const text = input.value.trim();
  const sentImage = attachedImage;        // this question's image, if any
  if (!text && !sentImage) return;
  if (!text && sentImage) {
    // A picture with no words: ask the model to describe it.
    return sendWith('What is in this image?');
  }
  if (text.length > MAX_CHARS) {
    input.value = text;
    grow();
    const turn = document.createElement('div');
    turn.className = 'turn bot';
    const body = document.createElement('div');
    body.className = 'text';
    turn.appendChild(body);
    startThread();
    thread.appendChild(turn);
    showNotice(body, 'That question is too long (' + text.length + ' characters). Please keep it under ' + MAX_CHARS + '.');
    return;
  }

  addYou(text, sentImage);
  clearImage();                           // consumed — never reused next turn
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
        image: sentImage,                 // null unless one was attached
        history: outgoingHistory(),
        timezone: where.timezone,
        language: where.language,
      }),
      signal: pending.signal,
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      body.innerHTML = '';
      showNotice(body, errorText(data.detail, res.status));
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
          if (!turn.dataset.started) {
            turn.dataset.started = '1';
            body.innerHTML = '';
            if (turn._waking) { turn._waking.remove(); turn._waking = null; }
          }
          answer += event.text;
          if (!frame) frame = requestAnimationFrame(paint);
        } else if (event.type === 'truncated') {
          turn.dataset.truncated = '1';
        } else if (event.type === 'clarify') {
          turn.dataset.started = '1';
          body.innerHTML = '';
          if (turn._waking) { turn._waking.remove(); turn._waking = null; }
          renderClarify(turn, body, event);
        } else if (event.type === 'followups') {
          turn.dataset.followups = JSON.stringify(event.questions);
        } else if (event.type === 'error') {
          if (!turn.dataset.started) body.innerHTML = '';
          showNotice(body, event.detail);
        }
      }
    }

    if (frame) cancelAnimationFrame(frame);

    if (turn.dataset.clarify) {
      // Keep the exchange, so the option the user picks next is answered
      // in the light of the question it clarifies.
      history.push({ role: 'user', content: text });
      history.push({ role: 'assistant', content: turn.dataset.clarify });
      return;
    }

    if (answer) {
      paint();
      history.push({ role: 'user', content: text });
      history.push({ role: 'assistant', content: answer });

      if (turn.dataset.sources) renderSources(turn, JSON.parse(turn.dataset.sources));
      addActions(turn, () => answer);
      if (turn.dataset.truncated) addContinue(turn);
      if (turn.dataset.followups) renderFollowups(turn, JSON.parse(turn.dataset.followups));
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
  if (!pending) send.disabled = !input.value.trim() && !attachedImage;
});

input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!pending) ask();                  // Enter sends; only the button stops
  }
});

send.addEventListener('click', ask);

document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    if (pending) return;
    input.value = chip.textContent.trim();
    grow();
    send.disabled = false;
    ask();
  });
});

/* =========================================================
   Chrome
========================================================= */

function newChat() {
  if (pending) pending.abort();
  history = [];
  thread.innerHTML = '';
  clearImage();
  input.value = '';
  closeImageGenView();
  resetToHero();
  grow();
  send.disabled = true;
  window.scrollTo({ top: 0 });
  closeSidebar();
  input.focus();
}

$('newChat').addEventListener('click', newChat);

const saved = localStorage.getItem('conbot-theme');
if (saved) document.body.classList.add(saved);

function toggleTheme() {
  const dark = getComputedStyle(document.body).backgroundColor === 'rgb(0, 0, 0)';
  document.body.classList.remove('dark', 'light');
  document.body.classList.add(dark ? 'light' : 'dark');
  localStorage.setItem('conbot-theme', dark ? 'light' : 'dark');
}

$('themeToggle').addEventListener('click', toggleTheme);

/* Let the reader scroll up mid-answer without being yanked back down. */
window.addEventListener('scroll', () => {
  bar.classList.toggle('scrolled', window.scrollY > 4);
  const room = document.body.scrollHeight - window.scrollY - window.innerHeight;
  stuckToBottom = room < 120;
}, { passive: true });

/* =========================================================
   B — Living headline
   "Ask __." where the trailing phrase rotates, teaching range across
   the audience (general -> practical -> everyday -> the differentiator).
   It is a welcome: it stops the moment a conversation starts, pauses
   when the tab is hidden, and honours reduced-motion.
========================================================= */

const PHRASES = ['anything.', 'about tax.', 'for a home remedy.', 'in your language.'];
const PHRASE_HOLD_MS = 2600;

const rotator = $('rotator');
const reduceMotion = window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

let phraseIndex = 0;
let rotatorTimer = null;
let rotatorLive = false;

function showNextPhrase() {
  phraseIndex = (phraseIndex + 1) % PHRASES.length;
  const next = PHRASES[phraseIndex];

  if (reduceMotion) {
    rotator.textContent = next;
    return;
  }

  rotator.classList.remove('swap-in');
  rotator.classList.add('swap-out');

  const onOut = () => {
    rotator.removeEventListener('animationend', onOut);
    rotator.textContent = next;
    rotator.classList.remove('swap-out');
    rotator.classList.add('swap-in');
  };
  rotator.addEventListener('animationend', onOut);
}

function scheduleRotator() {
  clearTimeout(rotatorTimer);
  rotatorTimer = setTimeout(() => {
    if (rotatorLive && !document.hidden) showNextPhrase();
    scheduleRotator();
  }, PHRASE_HOLD_MS);
}

function startRotator() {
  if (!rotator || rotatorLive) return;
  rotatorLive = true;
  phraseIndex = 0;
  rotator.textContent = PHRASES[0];
  if (!reduceMotion) scheduleRotator();
}

function stopRotator() {
  rotatorLive = false;
  clearTimeout(rotatorTimer);
}

// Typing is intent — the welcome bows out on the first real keystroke.
// (Not on focus: the page autofocuses the input on load, which would
// otherwise kill the rotation before it ever started.)
input.addEventListener('input', stopRotator, { once: true });

startRotator();
input.focus();

/* =========================================================
   Mic — voice input via the Web Speech API
   Frontend-only: speech becomes text in the input box, then sends as a
   normal question. No backend change, no audio leaves the device beyond
   the browser's own recognition.

   Handled carefully:
   - Only shown when recognition actually exists (no dead button).
   - Interim results preview live; the final result is committed.
   - Language follows the user's locale so Hindi/Hinglish transcribe.
   - Permission denial, no-speech, and errors each recover cleanly.
   - Starting a send or losing support always leaves the mic idle.
========================================================= */

(function setupMic() {
  const mic = $('mic');
  if (!mic) return;

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;                       // unsupported: leave the mic hidden

  mic.hidden = false;                    // supported: reveal it

  const recog = new SR();
  recog.continuous = false;
  recog.interimResults = true;
  recog.lang = navigator.language || 'en-IN';

  let listening = false;
  let committed = '';                    // text already in the box before speaking

  function start() {
    committed = input.value ? input.value.trimEnd() + ' ' : '';
    try {
      recog.start();
    } catch (e) {
      // start() throws if called while already starting; ignore.
    }
  }

  function stop() {
    try { recog.stop(); } catch (e) { /* not running */ }
  }

  mic.addEventListener('click', () => {
    if (listening) { stop(); return; }
    start();
  });

  recog.onstart = () => {
    listening = true;
    mic.classList.add('listening');
    mic.setAttribute('aria-label', 'Stop listening');
    stopRotator();                       // treat speaking as intent, like typing
  };

  recog.onresult = (event) => {
    let interim = '';
    let final = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const chunk = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += chunk;
      else interim += chunk;
    }
    input.value = committed + final + interim;
    if (final) committed += final;
    grow();
    send.disabled = !input.value.trim();
  };

  recog.onerror = (event) => {
    // not-allowed = permission denied; no-speech = silence. Both just reset.
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      mic.setAttribute('aria-label', 'Microphone blocked — allow access in your browser');
    }
  };

  recog.onend = () => {
    listening = false;
    mic.classList.remove('listening');
    mic.setAttribute('aria-label', 'Speak your question');
    input.focus();
  };

  // If the user sends while still listening, stop first so the recogniser
  // does not keep running against an empty box.
  send.addEventListener('click', () => { if (listening) stop(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && listening) stop();
  });
})();

/* =========================================================
   Image attach — read a file to a data URL for the next question

   The image is held in memory only, sent with one question, then cleared.
   It is never stored in history and never replayed. Size and type are
   checked here so the server rejects far fewer requests.
========================================================= */

(function setupAttach() {
  const attach = $('attach');
  const file = $('file');
  if (!attach || !file) return;

  attach.addEventListener('click', () => { if (!pending) file.click(); });

  file.addEventListener('change', () => {
    const chosen = file.files && file.files[0];
    file.value = '';                       // allow re-picking the same file
    if (!chosen) return;

    if (!/^image\/(png|jpeg|webp|gif)$/.test(chosen.type)) {
      flashAttach('Please choose a PNG, JPEG, WebP or GIF.');
      return;
    }
    if (chosen.size > MAX_IMAGE_BYTES) {
      flashAttach('That image is over 4 MB. Please choose a smaller one.');
      return;
    }

    const reader = new FileReader();
    reader.onload = () => { attachedImage = reader.result; showImageChip(chosen.name); };
    reader.onerror = () => flashAttach('That image could not be read.');
    reader.readAsDataURL(chosen);
  });

  attach.addEventListener('keydown', (e) => {
    // Backspace/Delete on the attach button clears a staged image.
    if ((e.key === 'Backspace' || e.key === 'Delete') && attachedImage) {
      e.preventDefault();
      clearImage();
    }
  });
})();

/* A small chip above the composer showing the staged image, with a remove X. */
function showImageChip(name) {
  clearImageChip();
  const composerEl = document.querySelector('.composer');
  if (!composerEl) return;

  const chip = document.createElement('div');
  chip.className = 'img-chip';
  chip.id = 'imgChip';

  const thumb = document.createElement('img');
  thumb.src = attachedImage;
  thumb.alt = '';
  chip.appendChild(thumb);

  const label = document.createElement('span');
  label.className = 'img-chip-name';
  label.textContent = name || 'image';
  chip.appendChild(label);

  const x = document.createElement('button');
  x.type = 'button';
  x.className = 'img-chip-x';
  x.setAttribute('aria-label', 'Remove image');
  x.textContent = '\u00d7';
  x.onclick = clearImage;
  chip.appendChild(x);

  composerEl.parentNode.insertBefore(chip, composerEl);
  if (!pending) send.disabled = false;     // an image alone is now sendable
}

function clearImageChip() {
  const chip = $('imgChip');
  if (chip) chip.remove();
}

function clearImage() {
  attachedImage = null;
  clearImageChip();
  if (!pending) send.disabled = !input.value.trim();
}

/* Brief inline warning on the attach button, no alert() popups. */
function flashAttach(message) {
  const attach = $('attach');
  if (!attach) return;
  const prev = attach.getAttribute('aria-label');
  attach.classList.add('attach-error');
  attach.setAttribute('aria-label', message);
  setTimeout(() => {
    attach.classList.remove('attach-error');
    attach.setAttribute('aria-label', prev || 'Attach an image');
  }, 2600);
}


/* ===== Sidebar open/close (mobile drawer) ===== */

function openSidebar() {
  document.body.classList.add('side-open');
}

function closeSidebar() {
  document.body.classList.remove('side-open');
}

const sideScrim = $('sideScrim');
$('menuBtn').addEventListener('click', openSidebar);
$('sideClose').addEventListener('click', closeSidebar);
sideScrim.addEventListener('click', closeSidebar);
$('sideNew').addEventListener('click', newChat);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeSidebar();
});

/* =========================================================
   IMAGE GENERATION — a dedicated view, not a dialog.
   A sibling of .hero/.thread; body.imggen-active swaps to it, the same
   way .chatting swaps hero for thread. History lives in memory only,
   for this tab, this session — resets on reload, same spirit as `history`.
   Calls POST /generate-image {prompt, model} -> {url, ...}.
========================================================= */

const imggenView = $('imggenView');
const imggenBack = $('imggenBack');
const imgPrompt = $('imgPrompt');
const imgModel = $('imgModel');
const imgGenerate = $('imgGenerate');
const imggenFrame = $('imggenFrame');
const imggenPlaceholder = $('imggenPlaceholder');
const imgResult = $('imgResult');
const imggenActions = $('imggenActions');
const imggenRegenerate = $('imggenRegenerate');
const imggenDownload = $('imggenDownload');
const imggenHistory = $('imggenHistory');
const imggenHistoryRow = $('imggenHistoryRow');

let imggenSessionHistory = [];   // [{url, prompt, model}], most recent first

function openImageGenView() {
  closeSidebar();
  imggenView.hidden = false;             // belt-and-suspenders alongside the
  document.body.classList.add('imggen-active'); // class: same proven pattern
  setTimeout(() => imgPrompt.focus(), 0);        // as #dock's own .hidden toggle
}

function closeImageGenView() {
  imggenView.hidden = true;
  document.body.classList.remove('imggen-active');
}

function showImageInFrame(url, prompt) {
  imggenFrame.classList.remove('loading');
  imggenFrame.innerHTML = '';
  const img = document.createElement('img');
  img.src = url;
  img.alt = prompt;
  imggenFrame.appendChild(img);
  imggenDownload.href = url;
  imggenActions.hidden = false;
  imgResult.hidden = true;
}

function resetFrameToPlaceholder() {
  imggenFrame.classList.remove('loading');
  imggenFrame.innerHTML = '';
  imggenFrame.appendChild(imggenPlaceholder);
}

function renderImggenHistory() {
  if (!imggenSessionHistory.length) {
    imggenHistory.hidden = true;
    return;
  }
  imggenHistory.hidden = false;
  imggenHistoryRow.innerHTML = '';
  imggenSessionHistory.forEach((entry, index) => {
    const thumb = document.createElement('button');
    thumb.type = 'button';
    thumb.className = 'imggen-thumb' + (index === 0 ? ' active' : '');
    thumb.style.backgroundImage = 'url(' + entry.url + ')';
    thumb.setAttribute('aria-label', entry.prompt);
    thumb.addEventListener('click', () => {
      imggenHistoryRow.querySelectorAll('.imggen-thumb').forEach((t) => t.classList.remove('active'));
      thumb.classList.add('active');
      showImageInFrame(entry.url, entry.prompt);
    });
    imggenHistoryRow.appendChild(thumb);
  });
}

async function runImageGeneration() {
  const prompt = imgPrompt.value.trim();
  if (!prompt || imgGenerate.disabled) return;

  imgGenerate.disabled = true;
  imggenActions.hidden = true;
  imgResult.hidden = true;
  imggenFrame.classList.add('loading');
  imggenFrame.innerHTML = '';
  imggenFrame.appendChild(imggenPlaceholder);

  try {
    const res = await fetch(API_BASE + '/generate-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt, model: imgModel.value }),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.detail || 'Image generation failed. Please try again.');
    }

    showImageInFrame(data.url, prompt);
    imggenSessionHistory.unshift({ url: data.url, prompt: prompt, model: data.model });
    renderImggenHistory();
  } catch (e) {
    resetFrameToPlaceholder();
    imgResult.hidden = false;
    imgResult.textContent = e.message || 'Something went wrong. Please try again.';
  } finally {
    imgGenerate.disabled = false;
  }
}

$('sideImageGen').addEventListener('click', openImageGenView);
imggenBack.addEventListener('click', closeImageGenView);
imgGenerate.addEventListener('click', runImageGeneration);
imggenRegenerate.addEventListener('click', runImageGeneration);
imgPrompt.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    runImageGeneration();
  }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.body.classList.contains('imggen-active')) closeImageGenView();
});

/* =========================================================
   Mic for the image generation view — same Web Speech API approach
   as the chat mic, pointed at #imgPrompt instead of #input.
========================================================= */

(function setupImageMic() {
  const mic = $('imgMic');
  if (!mic) return;

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;                       // unsupported: leave hidden

  mic.hidden = false;

  const recog = new SR();
  recog.continuous = false;
  recog.interimResults = true;
  recog.lang = navigator.language || 'en-IN';

  let listening = false;
  let committed = '';

  function start() {
    committed = imgPrompt.value ? imgPrompt.value.trimEnd() + ' ' : '';
    try { recog.start(); } catch (e) { /* already starting */ }
  }

  function stop() {
    try { recog.stop(); } catch (e) { /* not running */ }
  }

  mic.addEventListener('click', () => {
    if (listening) { stop(); return; }
    start();
  });

  recog.onstart = () => {
    listening = true;
    mic.classList.add('listening');
    mic.setAttribute('aria-label', 'Stop listening');
  };

  recog.onresult = (event) => {
    let interim = '';
    let final = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const chunk = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += chunk;
      else interim += chunk;
    }
    imgPrompt.value = committed + final + interim;
    if (final) committed += final;
  };

  recog.onerror = (event) => {
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      mic.setAttribute('aria-label', 'Microphone blocked — allow access in your browser');
    }
  };

  recog.onend = () => {
    listening = false;
    mic.classList.remove('listening');
    mic.setAttribute('aria-label', 'Speak your description');
    imgPrompt.focus();
  };
})();