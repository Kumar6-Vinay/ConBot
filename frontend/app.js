const form = document.getElementById("chatForm");
const input = document.getElementById("promptInput");
const messages = document.getElementById("chatMessages");
const send = document.querySelector(".send");
const microphone = document.getElementById("microphone");
const title = document.getElementById("chatTitle");
const composerArea = document.getElementById("composerArea");
const composerShell = document.querySelector(".welcome .hero-composer");
const moreButton = document.getElementById("more");
const moreMenu = document.getElementById("moreMenu");
const themeTop = document.getElementById("themeTop");
const themeTopLabel = document.getElementById("themeTopLabel");

const historyKey = "conbot-history-v2";
const themeKey = "conbot-theme";

const API =
  location.hostname === "localhost" ||
  location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "";

const MAX = 4000;
const TIMEOUT = 125000;

let recognition = null;
let isListening = false;
let voiceBaseText = "";
let lastUserPrompt = "";
let lastAssistantAnswer = "";

/* =========================================================
   Icons
========================================================= */

const ICONS = {
  copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 13l4 4L19 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  like: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v10H4V10h3Zm3 10h7.5a2 2 0 0 0 1.94-1.52l1.35-5.4A2 2 0 0 0 18.85 10.5H14l.7-3.9a1.8 1.8 0 0 0-3.2-1.4L8 9v11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>',
  dislike: '<svg viewBox="0 0 24 24" aria-hidden="true"><g transform="scale(1,-1) translate(0,-24)"><path d="M7 10v10H4V10h3Zm3 10h7.5a2 2 0 0 0 1.94-1.52l1.35-5.4A2 2 0 0 0 18.85 10.5H14l.7-3.9a1.8 1.8 0 0 0-3.2-1.4L8 9v11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></g></svg>'
};

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
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
}

function codeBlock(lang, code) {
  const langAttr = lang ? ` class="language-${escapeHtml(lang)}"` : "";

  return (
    '<pre class="code-block">' +
    `<button type="button" class="code-copy" data-action="copy-code" title="Copy code" aria-label="Copy code">${ICONS.copy}</button>` +
    (lang ? `<span class="code-lang">${escapeHtml(lang)}</span>` : "") +
    `<code${langAttr}>${escapeHtml(code)}</code>` +
    "</pre>"
  );
}

function markdown(s) {
  const out = [];
  let p = [];
  let list = null;

  const fp = () => {
    if (!p.length) return;

    out.push(
      "<p>" +
      inline(p.join("\n")).replaceAll("\n", "<br>") +
      "</p>"
    );

    p = [];
  };

  const fl = () => {
    if (list) {
      out.push("</" + list + ">");
      list = null;
    }
  };

  const lines = s.replace(/\r\n/g, "\n").split("\n");
  let i = 0;

  while (i < lines.length) {
    const raw = lines[i];
    const l = raw.trim();

    const fence = l.match(/^```(\S*)\s*$/);

    if (fence) {
      fp();
      fl();

      const lang = fence[1];
      const codeLines = [];
      i++;

      while (i < lines.length && !/^```\s*$/.test(lines[i].trim())) {
        codeLines.push(lines[i]);
        i++;
      }

      i++;

      out.push(codeBlock(lang, codeLines.join("\n")));
      continue;
    }

    if (!l) {
      fp();
      fl();
      i++;
      continue;
    }

    const h = l.match(/^#{1,3}\s+(.+)$/);

    if (h) {
      fp();
      fl();

      const n = h[0].match(/^#+/)[0].length + 1;

      out.push(`<h${n}>${inline(h[1])}</h${n}>`);
      i++;
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

      out.push("<li>" + inline((u || o)[1]) + "</li>");
      i++;
      continue;
    }

    fl();
    p.push(l);
    i++;
  }

  fp();
  fl();

  return out.join("");
}

/* =========================================================
   Composer state
========================================================= */

function setComposerActive(active) {
  if (!composerShell) return;

  if (active) {
    composerArea.appendChild(composerShell);
    composerShell.classList.add("active-composer");

    input.placeholder = "Ask a follow-up question…";

    if (!composerArea.querySelector(".trust")) {
      const trust = document.createElement("p");
      trust.className = "trust";
      trust.textContent = "AI can make mistakes. Verify important information.";
      composerArea.appendChild(trust);
    }
  } else {
    const welcome = messages.querySelector(".welcome");

    if (welcome) {
      const subtitle = welcome.querySelector(".hero-subtitle");
      const trySection = welcome.querySelector(".try-section");

      composerShell.classList.remove("active-composer");
      welcome.insertBefore(composerShell, trySection || subtitle.nextSibling);
    }

    composerArea.querySelector(".trust")?.remove();
    input.placeholder = "What are you curious about?";
  }
}

/* =========================================================
   Understanding actions
========================================================= */

function addUnderstandingActions(container) {
  const actions = document.createElement("div");
  actions.className = "understand-actions";

  const followups = [
    ["Explain simpler", "Explain that in simpler words."],
    ["Give an example", "Give me a simple real-life example."],
    ["Compare", "Compare this with something familiar."],
    ["What next?", "What should I understand next?"]
  ];

  followups.forEach(([label, prompt]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "understand-action";
    button.dataset.followup = prompt;
    button.textContent = label;
    actions.appendChild(button);
  });

  container.appendChild(actions);
}

/* =========================================================
   Chat messages
========================================================= */

function add(text, sender) {
  const welcome = document.getElementById("welcome");

  if (sender === "user" || !document.querySelector(".message.user")) {
    setComposerActive(true);
    welcome?.remove();
  }

  const m = document.createElement("div");
  m.className = "message " + sender;

  if (sender === "user") {
    m.innerHTML = `
      <div class="message-content">
        <div class="message-text"></div>
      </div>
    `;

    m.querySelector(".message-text").textContent = text;
    lastUserPrompt = text;
  } else {
    m.innerHTML = `
      <div class="avatar-ai">AI</div>

      <div class="message-content">
        <div class="message-name">ConBOT</div>

        <div class="message-text"></div>

        <div class="message-actions">
          <button class="message-action" data-action="copy" title="Copy" aria-label="Copy response">${ICONS.copy}</button>
          <button class="message-action" data-action="like" title="Helpful" aria-label="Helpful" aria-pressed="false">${ICONS.like}</button>
          <button class="message-action" data-action="dislike" title="Not helpful" aria-label="Not helpful" aria-pressed="false">${ICONS.dislike}</button>
        </div>
      </div>
    `;

    m.querySelector(".message-text").innerHTML = markdown(text);
    addUnderstandingActions(m.querySelector(".message-content"));
    lastAssistantAnswer = text;
  }

  messages.appendChild(m);
  messages.scrollTop = messages.scrollHeight;
}

/* =========================================================
   Thinking state
========================================================= */

function thinking(on) {
  document.getElementById("typing")?.remove();

  if (!on) return;

  const m = document.createElement("div");
  m.id = "typing";
  m.className = "message assistant";

  m.innerHTML = `
    <div class="avatar-ai">AI</div>

    <div class="message-content">
      <div class="message-name">ConBOT</div>
      <div class="message-text typing">Thinking…</div>
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
  const t = setTimeout(() => c.abort(), TIMEOUT);

  try {
    const r = await fetch(API + "/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
      signal: c.signal
    });

    if (!r.ok) {
      throw new Error("HTTP " + r.status);
    }

    const d = await r.json();

    if (!d || typeof d.answer !== "string" || !d.answer.trim()) {
      throw new Error("Invalid");
    }

    return d.answer;
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error("ConBOT is taking longer than expected. Please try again.");
    }

    if (e.message.includes("429")) {
      throw new Error("You're sending questions a little too quickly. Please wait a moment.");
    }

    if (e.message.includes("503") || e.message.includes("504")) {
      throw new Error("ConBOT is temporarily unavailable. Please try again in a few minutes.");
    }

    if (e.message.includes("400")) {
      throw new Error("We couldn't process that question. Please check it and try again.");
    }

    throw new Error("We're having trouble connecting to ConBOT right now. Please try again in a moment.");
  } finally {
    clearTimeout(t);
  }
}

function buildFollowupPrompt(followup) {
  if (!lastUserPrompt || !lastAssistantAnswer) {
    return followup;
  }

  return `
We are continuing an existing conversation.

Original user question:
${lastUserPrompt}

Previous ConBOT answer:
${lastAssistantAnswer}

Now the user wants:
${followup}

Answer the new request naturally and use the previous context. Do not mention this context block.
`.trim();
}

/* =========================================================
   History
========================================================= */

function getHistory() {
  try {
    return JSON.parse(localStorage.getItem(historyKey) || "[]");
  } catch {
    return [];
  }
}

function renderHistory() {
  const a = getHistory();
  const today = document.getElementById("todayHistory");
  const yesterday = document.getElementById("yesterdayHistory");

  today.replaceChildren();
  yesterday.replaceChildren();

  if (!a.length) {
    const e = document.createElement("div");
    e.className = "history-empty";
    e.textContent = "Your conversations will appear here.";
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
   Welcome / New chat
========================================================= */

function renderWelcome() {
  messages.innerHTML = `
    <div class="welcome" id="welcome">

      <h1>
        Ask. Learn.
        <span>Understand.</span>
      </h1>

      <p class="hero-subtitle">
        Your questions. Made clear.
      </p>

      <div class="try-section">
        <span class="try-label">Try asking</span>

        <div class="suggestions">
          <button data-prompt="Explain GST simply">Explain GST simply</button>
          <button data-prompt="Plan a 3-day Jaipur trip">Plan a Jaipur trip</button>
          <button data-prompt="What should I cook today?">What should I cook?</button>
          <button data-prompt="Why is the price of gold changing?">Why is gold rising?</button>
        </div>
      </div>
    </div>
  `;

  setComposerActive(false);
}

function newChat() {
  if (isListening) {
    stopVoiceInput();
  }

  renderWelcome();

  title.textContent = "New conversation";
  lastUserPrompt = "";
  lastAssistantAnswer = "";

  input.value = "";
  input.style.height = "auto";

  closeMoreMenu();
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
   More menu
========================================================= */

function closeMoreMenu() {
  moreMenu.hidden = true;
  moreButton.setAttribute("aria-expanded", "false");
}

function toggleMoreMenu() {
  const open = moreMenu.hidden;
  moreMenu.hidden = !open;
  moreButton.setAttribute("aria-expanded", String(open));
}

/* =========================================================
   Voice input
========================================================= */

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

function updateMicrophoneUI(listening) {
  isListening = listening;

  microphone.classList.toggle("is-listening", listening);
  microphone.setAttribute("aria-pressed", String(listening));
  microphone.setAttribute("aria-label", listening ? "Stop listening" : "Use microphone");
  microphone.setAttribute("title", listening ? "Stop listening" : "Voice input");
}

function showVoiceMessage(message) {
  add(message, "assistant");
}

function stopVoiceInput() {
  if (!recognition || !isListening) return;
  recognition.stop();
}

function startVoiceInput() {
  if (!SpeechRecognition) {
    showVoiceMessage("Voice input isn't available in this browser. You can type your question instead.");
    return;
  }

  if (isListening) {
    stopVoiceInput();
    return;
  }

  if (input.disabled) return;

  voiceBaseText = input.value.trim();
  recognition = new SpeechRecognition();
  recognition.lang = navigator.language || "en-IN";
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => updateMicrophoneUI(true);

  recognition.onresult = event => {
    let transcript = "";

    for (let i = 0; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }

    transcript = transcript.trim();
    if (!transcript) return;

    input.value = voiceBaseText
      ? `${voiceBaseText} ${transcript}`
      : transcript;

    input.dispatchEvent(new Event("input"));
  };

  recognition.onerror = event => {
    updateMicrophoneUI(false);

    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      showVoiceMessage("Microphone access was denied. Please allow microphone access in your browser settings to use voice input.");
      return;
    }

    if (event.error === "no-speech") return;

    if (event.error === "audio-capture") {
      showVoiceMessage("We couldn't access your microphone. Please check your microphone and try again.");
      return;
    }

    showVoiceMessage("Voice input couldn't start. Please try again or type your question.");
  };

  recognition.onend = () => {
    updateMicrophoneUI(false);
    recognition = null;
    input.focus();
  };

  try {
    recognition.start();
  } catch {
    updateMicrophoneUI(false);
    recognition = null;
  }
}

/* =========================================================
   Submit
========================================================= */

async function submitPrompt(visiblePrompt, requestPrompt = visiblePrompt) {
  if (isListening) {
    stopVoiceInput();
  }

  if (input.disabled) {
    return;
  }

  const p = String(visiblePrompt || "").trim();
  const apiPrompt = String(requestPrompt || p).trim();

  if (!p) {
    return;
  }

  if (apiPrompt.length > MAX) {
    add("Your question is too long. Please keep it under 4,000 characters.", "assistant");
    return;
  }

  const first = !document.querySelector(".message.user");

  input.disabled = true;
  send.disabled = true;

  add(p, "user");

  input.value = "";
  input.style.height = "auto";

  if (first) {
    const a = getHistory();

    a.unshift({
      title: p.replace(/\s+/g, " ").slice(0, 55),
      date: Date.now()
    });

    localStorage.setItem(historyKey, JSON.stringify(a.slice(0, 30)));
    renderHistory();
    title.textContent = a[0].title;
  }

  thinking(true);

  try {
    add(await ask(apiPrompt), "assistant");
  } catch (e) {
    add(e.message, "assistant");
  } finally {
    thinking(false);
    input.disabled = false;
    send.disabled = false;
    input.focus();
  }
}

async function submit(e) {
  e.preventDefault();
  await submitPrompt(input.value);
}


/* =========================================================
   Event listeners
========================================================= */

form.addEventListener("submit", submit);

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 190) + "px";
});

input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

document.addEventListener("click", async e => {
  const promptButton = e.target.closest("[data-prompt]");

  if (promptButton) {
    input.value = promptButton.dataset.prompt;
    input.focus();
    input.dispatchEvent(new Event("input"));
    return;
  }

  const followupButton = e.target.closest("[data-followup]");

  if (followupButton) {
    const followup = followupButton.dataset.followup;
    const followupPrompt = buildFollowupPrompt(followup);
    await submitPrompt(followup, followupPrompt);
    return;
  }

  const codeCopyButton = e.target.closest(".code-copy");

  if (codeCopyButton) {
    try {
      const code = codeCopyButton.closest(".code-block").querySelector("code").innerText;
      await navigator.clipboard.writeText(code);

      codeCopyButton.innerHTML = ICONS.check;
      codeCopyButton.classList.add("is-copied");

      setTimeout(() => {
        codeCopyButton.innerHTML = ICONS.copy;
        codeCopyButton.classList.remove("is-copied");
      }, 1200);
    } catch {
      // Clipboard unavailable.
    }

    return;
  }

  const messageAction = e.target.closest(".message-action");

  if (messageAction && messageAction.dataset.action === "copy") {
    try {
      await navigator.clipboard.writeText(
        messageAction.closest(".message").querySelector(".message-text").innerText
      );

      messageAction.innerHTML = ICONS.check;
      setTimeout(() => {
        messageAction.innerHTML = ICONS.copy;
      }, 1200);
    } catch {
      // Clipboard unavailable.
    }

    return;
  }

  if (messageAction && (messageAction.dataset.action === "like" || messageAction.dataset.action === "dislike")) {
    const actions = messageAction.closest(".message-actions");
    const isActive = messageAction.getAttribute("aria-pressed") === "true";

    actions.querySelectorAll(".message-action[aria-pressed]").forEach(button => {
      button.setAttribute("aria-pressed", "false");
      button.classList.remove("is-active");
    });

    if (!isActive) {
      messageAction.setAttribute("aria-pressed", "true");
      messageAction.classList.add("is-active");
    }
  }
});

/* =========================================================
   Navigation
========================================================= */

document.getElementById("newChat").onclick = newChat;
document.getElementById("newChatTop").onclick = newChat;
document.getElementById("menu").onclick = openSidebar;
document.getElementById("overlay").onclick = closeSidebar;

moreButton.onclick = event => {
  event.stopPropagation();
  toggleMoreMenu();
};

moreMenu.addEventListener("click", event => {
  event.stopPropagation();
});

document.addEventListener("click", event => {
  if (!event.target.closest(".more-wrap")) {
    closeMoreMenu();
  }
});

document.getElementById("searchChats").onclick = () => {
  add("Chat search will be connected when persistent conversation history is added.", "assistant");
};

document.getElementById("settings").onclick = () => {
  closeMoreMenu();
  add("Settings will be added as ConBOT features mature.", "assistant");
};

document.getElementById("help").onclick = () => {
  closeMoreMenu();
  add("Start with a question below. ConBOT is designed for everyday questions, learning and understanding.", "assistant");
};

document.getElementById("attachment").onclick = () => {
  add("File upload is coming next. For now, ask ConBOT directly.", "assistant");
};

microphone.addEventListener("click", startVoiceInput);

function toggleTheme() {
  const dark = !document.body.classList.contains("dark");

  document.body.classList.toggle("dark", dark);

  localStorage.setItem(themeKey, dark ? "dark" : "light");

  themeTopLabel.textContent = dark ? "Light Mode" : "Dark Mode";
  themeTop.title = dark ? "Light Mode" : "Dark Mode";
}

themeTop.onclick = toggleTheme;

/* =========================================================
   Initial state
========================================================= */

if (localStorage.getItem(themeKey) === "dark") {
  document.body.classList.add("dark");
  themeTopLabel.textContent = "Light Mode";
  themeTop.title = "Light Mode";
}

renderHistory();

window.addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") {
    e.preventDefault();
    newChat();
  }

  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    document.getElementById("searchChats").click();
  }

  if (e.key === "Escape") {
    closeMoreMenu();
    closeSidebar();
  }
});
