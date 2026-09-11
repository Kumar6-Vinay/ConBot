const form = document.getElementById("chatForm");
const input = document.getElementById("promptInput");
const messages = document.getElementById("chatMessages");
const send = document.querySelector(".send");
const microphone = document.getElementById("microphone");
const title = document.getElementById("chatTitle");

const historyKey = "conbot-history-v2";
const themeKey = "conbot-theme";

const API =
  location.hostname === "localhost" ||
  location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "";

const MAX = 4000;
const TIMEOUT = 125000;


/* =========================================================
   Utility
========================================================= */

function escapeHtml(s) {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


function inline(s) {
  return escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
}


function markdown(s) {
  const out = [];
  let p = [];
  let list = null;

  const fp = () => {
    if (p.length) {
      out.push(
        "<p>" +
        inline(p.join("\n")).replaceAll("\n", "<br>") +
        "</p>"
      );

      p = [];
    }
  };

  const fl = () => {
    if (list) {
      out.push("</" + list + ">");
      list = null;
    }
  };

  for (const raw of s.replace(/\r\n/g, "\n").split("\n")) {

    const l = raw.trim();

    if (!l) {
      fp();
      fl();
      continue;
    }

    const h = l.match(/^#{1,3}\s+(.+)$/);

    if (h) {
      fp();
      fl();

      const n = h[0].match(/^#+/)[0].length + 1;

      out.push(
        `<h${n}>${inline(h[1])}</h${n}>`
      );

      continue;
    }

    const u = l.match(/^[-*]\s+(.+)$/);
    const o = l.match(/^\d+[.)]\s+(.+)$/);

    if (u || o) {
      fp();

      const t = u ? "ul" : "ol";

      if (list !== t) {
        fl();
        out.push("<" + t + ">");
        list = t;
      }

      out.push(
        "<li>" +
        inline((u || o)[1]) +
        "</li>"
      );

      continue;
    }

    fl();
    p.push(l);
  }

  fp();
  fl();

  return out.join("");
}


/* =========================================================
   Chat messages
========================================================= */

function add(text, sender) {

  document.getElementById("welcome")?.remove();

  const m = document.createElement("div");

  m.className = "message " + sender;

  if (sender === "user") {

    m.innerHTML = `
      <div class="message-content">
        <div class="message-text"></div>
      </div>
    `;

    m.querySelector(".message-text").textContent = text;

  } else {

    m.innerHTML = `
      <div class="avatar-ai">AI</div>

      <div class="message-content">

        <div class="message-name">
          ConBOT
        </div>

        <div class="message-text"></div>

        <div class="message-actions">

          <button
            class="message-action"
            data-action="copy"
            title="Copy">
            □
          </button>

          <button
            class="message-action"
            data-action="like"
            title="Helpful">
            ♡
          </button>

          <button
            class="message-action"
            data-action="dislike"
            title="Not helpful">
            ♧
          </button>

        </div>

      </div>
    `;

    m.querySelector(".message-text").innerHTML =
      markdown(text);
  }

  messages.appendChild(m);

  messages.scrollTop = messages.scrollHeight;
}


/* =========================================================
   Thinking state
========================================================= */

function thinking(on) {

  document.getElementById("typing")?.remove();

  if (!on) {
    return;
  }

  const m = document.createElement("div");

  m.id = "typing";
  m.className = "message assistant";

  m.innerHTML = `
    <div class="avatar-ai">AI</div>

    <div class="message-content">

      <div class="message-name">
        ConBOT
      </div>

      <div class="message-text typing">
        Thinking…
      </div>

    </div>
  `;

  messages.appendChild(m);

  messages.scrollTop = messages.scrollHeight;
}


/* =========================================================
   API
========================================================= */

async function ask(prompt) {

  const c = new AbortController();

  const t = setTimeout(
    () => c.abort(),
    TIMEOUT
  );

  try {

    const r = await fetch(
      API + "/ask",
      {
        method: "POST",

        headers: {
          "Content-Type": "application/json"
        },

        body: JSON.stringify({
          prompt
        }),

        signal: c.signal
      }
    );

    if (!r.ok) {
      throw new Error("HTTP " + r.status);
    }

    const d = await r.json();

    if (
      !d ||
      typeof d.answer !== "string" ||
      !d.answer.trim()
    ) {
      throw new Error("Invalid");
    }

    return d.answer;

  } catch (e) {

    if (e.name === "AbortError") {
      throw new Error(
        "ConBOT is taking longer than expected. Please try again."
      );
    }

    if (e.message.includes("429")) {
      throw new Error(
        "You're sending questions a little too quickly. Please wait a moment."
      );
    }

    if (
      e.message.includes("503") ||
      e.message.includes("504")
    ) {
      throw new Error(
        "ConBOT is temporarily unavailable. Please try again in a few minutes."
      );
    }

    if (e.message.includes("400")) {
      throw new Error(
        "We couldn't process that question. Please check it and try again."
      );
    }

    throw new Error(
      "We're having trouble connecting to ConBOT right now. Please try again in a moment."
    );

  } finally {

    clearTimeout(t);
  }
}


/* =========================================================
   History
========================================================= */

function getHistory() {

  try {
    return JSON.parse(
      localStorage.getItem(historyKey) || "[]"
    );
  } catch {
    return [];
  }
}


function renderHistory() {

  const a = getHistory();

  const today =
    document.getElementById("todayHistory");

  const yesterday =
    document.getElementById("yesterdayHistory");

  today.replaceChildren();
  yesterday.replaceChildren();

  if (!a.length) {

    const e = document.createElement("div");

    e.className = "history-empty";

    e.textContent =
      "Your conversations will appear here.";

    today.appendChild(e);

    return;
  }

  a.forEach(x => {

    const b = document.createElement("button");

    b.className = "history-item";

    b.textContent = x.title;

    b.onclick = () => {

      title.textContent = x.title;

      closeSidebar();
    };

    today.appendChild(b);

  });
}


/* =========================================================
   New chat
========================================================= */

function newChat() {

  if (isListening) {
    stopVoiceInput();
  }

  messages.innerHTML = `
    <div class="welcome" id="welcome">

      <div class="mark">
        ◈
      </div>

      <h1>
        Ask. Learn.
        <span>Understand.</span>
      </h1>

      <p>
        Your AI for everyday questions, learning, ideas and understanding.
      </p>

      <div class="suggestions">

        <button data-prompt="Explain GST simply">
          <b>▧</b>
          <span>Explain GST simply</span>
          <i>→</i>
        </button>

        <button data-prompt="Plan a 3-day Jaipur trip">
          <b>⌁</b>
          <span>Plan a 3-day Jaipur trip</span>
          <i>→</i>
        </button>

        <button data-prompt="What should I cook today?">
          <b>♜</b>
          <span>What should I cook?</span>
          <i>→</i>
        </button>

        <button data-prompt="Why is the price of gold changing?">
          <b>↗</b>
          <span>Why is gold price changing?</span>
          <i>→</i>
        </button>

      </div>

    </div>
  `;

  title.textContent = "New conversation";

  input.value = "";
  input.style.height = "auto";

  closeSidebar();

  input.focus();
}


/* =========================================================
   Sidebar
========================================================= */

function closeSidebar() {
  document.body.classList.remove("sidebar-open");
}


function openSidebar() {
  document.body.classList.add("sidebar-open");
}


/* =========================================================
   Voice input
========================================================= */

const SpeechRecognition =
  window.SpeechRecognition ||
  window.webkitSpeechRecognition;

let recognition = null;
let isListening = false;
let voiceBaseText = "";


/*
 * Update microphone appearance and accessibility state.
 */
function updateMicrophoneUI(listening) {

  isListening = listening;

  microphone.classList.toggle(
    "is-listening",
    listening
  );

  microphone.setAttribute(
    "aria-pressed",
    String(listening)
  );

  microphone.setAttribute(
    "aria-label",
    listening
      ? "Stop listening"
      : "Use microphone"
  );

  microphone.setAttribute(
    "title",
    listening
      ? "Stop listening"
      : "Voice input"
  );
}


/*
 * Display a voice-related message in the chat.
 */
function showVoiceMessage(message) {
  add(message, "assistant");
}


/*
 * Stop active speech recognition.
 */
function stopVoiceInput() {

  if (!recognition || !isListening) {
    return;
  }

  recognition.stop();
}


/*
 * Start speech recognition.
 */
function startVoiceInput() {

  /*
   * Browser does not support speech recognition.
   */
  if (!SpeechRecognition) {

    showVoiceMessage(
      "Voice input isn't available in this browser. You can type your question instead."
    );

    return;
  }


  /*
   * If already listening, clicking the mic
   * stops the current recognition session.
   */
  if (isListening) {

    stopVoiceInput();

    return;
  }


  /*
   * Do not start voice input while a request
   * is being processed.
   */
  if (input.disabled) {
    return;
  }


  /*
   * Preserve anything the user already typed.
   */
  voiceBaseText = input.value.trim();


  recognition = new SpeechRecognition();

  /*
   * Use the browser's preferred language.
   *
   * Example:
   * en-IN for English India
   * hi-IN for Hindi India
   */
  recognition.lang =
    navigator.language || "en-IN";


  /*
   * One interaction at a time.
   */
  recognition.continuous = false;


  /*
   * Show words while the user is speaking.
   */
  recognition.interimResults = true;


  /*
   * Only use the most likely transcription.
   */
  recognition.maxAlternatives = 1;


  /*
   * Recognition started.
   */
  recognition.onstart = () => {

    updateMicrophoneUI(true);

  };


  /*
   * Speech result received.
   */
  recognition.onresult = event => {

    let transcript = "";

    /*
     * Collect all available results.
     *
     * This prevents interim results from
     * replacing previously recognized words.
     */
    for (
      let i = 0;
      i < event.results.length;
      i++
    ) {

      transcript +=
        event.results[i][0].transcript;
    }


    transcript = transcript.trim();


    if (!transcript) {
      return;
    }


    /*
     * Combine existing typed text with
     * the recognized speech.
     */
    input.value = voiceBaseText
      ? `${voiceBaseText} ${transcript}`
      : transcript;


    /*
     * Recalculate textarea height.
     */
    input.dispatchEvent(
      new Event("input")
    );

  };


  /*
   * Speech recognition error.
   */
  recognition.onerror = event => {

    updateMicrophoneUI(false);


    if (
      event.error === "not-allowed" ||
      event.error === "service-not-allowed"
    ) {

      showVoiceMessage(
        "Microphone access was denied. Please allow microphone access in your browser settings to use voice input."
      );

      return;
    }


    /*
     * No speech is not a serious error.
     *
     * Don't clutter the conversation with
     * an error message.
     */
    if (event.error === "no-speech") {
      return;
    }


    if (event.error === "audio-capture") {

      showVoiceMessage(
        "We couldn't access your microphone. Please check your microphone and try again."
      );

      return;
    }


    showVoiceMessage(
      "Voice input couldn't start. Please try again or type your question."
    );
  };


  /*
   * Recognition ended.
   */
  recognition.onend = () => {

    updateMicrophoneUI(false);

    recognition = null;

    input.focus();
  };


  /*
   * Start recognition.
   */
  try {

    recognition.start();

  } catch (error) {

    updateMicrophoneUI(false);

    recognition = null;

  }
}


/* =========================================================
   Submit
========================================================= */

async function submit(e) {

  e.preventDefault();


  /*
   * Stop microphone before sending.
   */
  if (isListening) {
    stopVoiceInput();
  }


  if (input.disabled) {
    return;
  }


  const p = input.value.trim();


  if (!p) {
    return;
  }


  if (p.length > MAX) {

    add(
      "Your question is too long. Please keep it under 4,000 characters.",
      "assistant"
    );

    return;
  }


  const first =
    !document.querySelector(".message.user");


  input.disabled = true;

  send.disabled = true;


  add(p, "user");


  input.value = "";

  input.style.height = "auto";


  /*
   * Save first question to local history.
   */
  if (first) {

    const a = getHistory();

    a.unshift({
      title: p
        .replace(/\s+/g, " ")
        .slice(0, 55),

      date: Date.now()
    });

    localStorage.setItem(
      historyKey,
      JSON.stringify(a.slice(0, 30))
    );

    renderHistory();

    title.textContent = a[0].title;
  }


  thinking(true);


  try {

    add(
      await ask(p),
      "assistant"
    );

  } catch (e) {

    add(
      e.message,
      "assistant"
    );

  } finally {

    thinking(false);

    input.disabled = false;

    send.disabled = false;

    input.focus();
  }
}


/* =========================================================
   Event listeners
========================================================= */

form.addEventListener(
  "submit",
  submit
);


/*
 * Auto-resize textarea.
 */
input.addEventListener(
  "input",
  () => {

    input.style.height = "auto";

    input.style.height =
      Math.min(
        input.scrollHeight,
        190
      ) + "px";
  }
);


/*
 * Enter = Send
 * Shift + Enter = New line
 */
input.addEventListener(
  "keydown",
  e => {

    if (
      e.key === "Enter" &&
      !e.shiftKey
    ) {

      e.preventDefault();

      form.requestSubmit();
    }
  }
);


/*
 * Suggestion buttons.
 */
document.addEventListener(
  "click",
  e => {

    const b =
      e.target.closest("[data-prompt]");

    if (!b) {
      return;
    }

    input.value =
      b.dataset.prompt;

    input.focus();

    input.dispatchEvent(
      new Event("input")
    );
  }
);


/*
 * Message actions.
 */
messages.addEventListener(
  "click",
  async e => {

    const b =
      e.target.closest(".message-action");

    if (!b) {
      return;
    }


    if (b.dataset.action === "copy") {

      try {

        await navigator.clipboard.writeText(
          b.closest(".message")
            .querySelector(".message-text")
            .innerText
        );

        b.textContent = "✓";

        setTimeout(
          () => {
            b.textContent = "□";
          },
          1000
        );

      } catch {
        // Clipboard unavailable.
      }
    }
  }
);


/* =========================================================
   Navigation
========================================================= */

document.getElementById(
  "newChat"
).onclick = newChat;


document.getElementById(
  "newChatTop"
).onclick = newChat;


document.getElementById(
  "menu"
).onclick = openSidebar;


document.getElementById(
  "overlay"
).onclick = closeSidebar;


document.getElementById(
  "searchChats"
).onclick = () => {

  add(
    "Chat search will be connected when persistent conversation history is added.",
    "assistant"
  );
};


document.getElementById(
  "settings"
).onclick = () => {

  add(
    "Settings will be added as ConBOT features mature.",
    "assistant"
  );
};


document.getElementById(
  "help"
).onclick = () => {

  add(
    "Start with a question below. ConBOT is designed for everyday questions, learning and understanding.",
    "assistant"
  );
};


document.getElementById(
  "attachment"
).onclick = () => {

  add(
    "File upload is coming next. For now, ask ConBOT directly.",
    "assistant"
  );
};


/*
 * Real microphone feature.
 */
microphone.addEventListener(
  "click",
  startVoiceInput
);


/*
 * Theme switching.
 */
document.getElementById(
  "theme"
).onclick = () => {

  const dark =
    !document.body.classList.contains("dark");

  document.body.classList.toggle(
    "dark",
    dark
  );

  localStorage.setItem(
    themeKey,
    dark ? "dark" : "light"
  );

  document.getElementById(
    "themeLabel"
  ).textContent =
    dark
      ? "Light Mode"
      : "Dark Mode";
};


/* =========================================================
   Initial state
========================================================= */

if (
  localStorage.getItem(themeKey) === "dark"
) {

  document.body.classList.add("dark");

  document.getElementById(
    "themeLabel"
  ).textContent = "Light Mode";
}


renderHistory();


/*
 * Keyboard shortcut:
 * Cmd/Ctrl + N
 */
window.addEventListener(
  "keydown",
  e => {

    if (
      (e.metaKey || e.ctrlKey) &&
      e.key.toLowerCase() === "n"
    ) {

      e.preventDefault();

      newChat();
    }
  }
);


/*
 * Keyboard shortcut:
 * Cmd/Ctrl + K
 */
window.addEventListener(
  "keydown",
  e => {

    if (
      (e.metaKey || e.ctrlKey) &&
      e.key.toLowerCase() === "k"
    ) {

      e.preventDefault();

      document.getElementById(
        "searchChats"
      ).click();
    }
  }
);