const chatForm =
  document.getElementById("chatForm");

const promptInput =
  document.getElementById("promptInput");

const chatMessages =
  document.getElementById("chatMessages");

const clearButton =
  document.getElementById("clearButton");

const themeButton =
  document.getElementById("themeButton");

const suggestions =
  document.getElementById("suggestions");


/* =========================
   API CONFIGURATION
========================= */

const API_BASE_URL =
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "";


/* =========================
   INITIAL WELCOME STATE
========================= */

const initialWelcomeMarkup = `
  <div
    class="welcome-state"
    id="welcomeState"
  >

    <div class="welcome-orb">

      <div class="orb-core"></div>

    </div>

    <h2>
      What would you like to know?
    </h2>

    <p>
      Ask naturally.
      Learn something new.
      Understand things more clearly.
    </p>

  </div>
`;


/* =========================
   ASK CONBOT
========================= */

async function askConbot(prompt) {

  const response =
    await fetch(
      `${API_BASE_URL}/ask`,
      {
        method: "POST",

        headers: {
          "Content-Type": "application/json"
        },

        body: JSON.stringify({
          prompt: prompt
        })
      }
    );


  if (!response.ok) {

    let detail = "";

    try {

      const errorData =
        await response.json();

      if (errorData?.detail) {

        detail =
          `: ${errorData.detail}`;

      }

    } catch (_) {
      // Ignore invalid error responses.
    }


    throw new Error(
      `API request failed (${response.status})${detail}`
    );

  }


  const data =
    await response.json();


  if (!data.answer) {

    throw new Error(
      "The AI service returned no answer."
    );

  }


  return data.answer;

}


/* =========================
   ADD MESSAGE
========================= */

function addMessage(
  text,
  sender
) {

  const welcome =
    document.getElementById(
      "welcomeState"
    );


  if (welcome) {

    welcome.remove();

  }


  const message =
    document.createElement(
      "div"
    );


  message.className =
    `message ${sender}`;


  /* USER */

  if (sender === "user") {

    message.innerHTML = `
      <div class="message-content">
        <div class="message-text"></div>
      </div>
    `;

  }


  /* ASSISTANT */

  else {

    message.innerHTML = `
      <div class="avatar">
        AI
      </div>

      <div class="message-content">

        <div class="message-name">
          CONBOT
        </div>

        <div class="message-text"></div>

      </div>
    `;

  }


  const messageText =
    message.querySelector(
      ".message-text"
    );


  /*
   * textContent is deliberately used
   * for safe output.
   *
   * This prevents user/model text
   * from being treated as HTML.
   */

  messageText.textContent =
    text;


  chatMessages.appendChild(
    message
  );


  chatMessages.scrollTop =
    chatMessages.scrollHeight;

}


/* =========================
   TYPING / THINKING STATE
========================= */

function setLoading(
  isLoading
) {

  const existing =
    document.getElementById(
      "typingIndicator"
    );


  if (
    isLoading &&
    !existing
  ) {

    const node =
      document.createElement(
        "div"
      );


    node.className =
      "message assistant";


    node.id =
      "typingIndicator";


    node.innerHTML = `
      <div class="avatar">
        AI
      </div>

      <div class="message-content">

        <div class="message-name">
          CONBOT
        </div>

        <div class="message-text typing-state">
          Thinking…
        </div>

      </div>
    `;


    chatMessages.appendChild(
      node
    );


    chatMessages.scrollTop =
      chatMessages.scrollHeight;

  }


  if (
    !isLoading &&
    existing
  ) {

    existing.remove();

  }

}


/* =========================
   SUBMIT CHAT
========================= */

async function handleSubmit(
  event
) {

  event.preventDefault();


  const prompt =
    promptInput.value.trim();


  if (!prompt) {

    promptInput.focus();

    return;

  }


  addMessage(
    prompt,
    "user"
  );


  promptInput.value =
    "";

  promptInput.style.height =
    "auto";


  setLoading(true);


  try {

    const answer =
      await askConbot(
        prompt
      );


    addMessage(
      answer,
      "assistant"
    );

  }


  catch (error) {

    console.error(
      "CONBOT request failed:",
      error
    );


    addMessage(
      "CONBOT is having trouble connecting right now. Please try again in a moment.",
      "assistant"
    );

  }


  finally {

    setLoading(false);

    promptInput.focus();

  }

}


/* =========================
   FORM SUBMIT
========================= */

chatForm.addEventListener(
  "submit",
  handleSubmit
);


/* =========================
   AUTO-RESIZE TEXTAREA
========================= */

promptInput.addEventListener(
  "input",
  () => {

    promptInput.style.height =
      "auto";


    promptInput.style.height =
      `${Math.min(
        promptInput.scrollHeight,
        190
      )}px`;

  }
);


/* =========================
   ENTER TO SEND
========================= */

promptInput.addEventListener(
  "keydown",
  (event) => {

    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {

      event.preventDefault();

      chatForm.requestSubmit();

    }

  }
);


/* =========================
   CLEAR CHAT
========================= */

clearButton.addEventListener(
  "click",
  () => {

    chatMessages.innerHTML =
      initialWelcomeMarkup;

    promptInput.value =
      "";

    promptInput.style.height =
      "auto";

    promptInput.focus();

  }
);


/* =========================
   EXAMPLE PROMPTS
========================= */

suggestions.addEventListener(
  "click",
  (event) => {

    const button =
      event.target.closest(
        "[data-prompt]"
      );


    if (!button) {
      return;
    }


    promptInput.value =
      button.dataset.prompt;


    promptInput.focus();


    promptInput.dispatchEvent(
      new Event("input")
    );

  }
);


/* =========================
   DARK MODE
========================= */

themeButton.addEventListener(
  "click",
  () => {

    document.body.classList.toggle(
      "dark"
    );


    localStorage.setItem(
      "conbot-theme",
      document.body.classList.contains(
        "dark"
      )
        ? "dark"
        : "light"
    );

  }
);


/* =========================
   RESTORE THEME
========================= */

const storedTheme =
  localStorage.getItem(
    "conbot-theme"
  );


if (
  storedTheme === "dark"
) {

  document.body.classList.add(
    "dark"
  );

}


/* =========================
   INITIAL FOCUS
========================= */

window.addEventListener(
  "load",
  () => {

    /*
     * Don't automatically focus on
     * mobile because it would open
     * the keyboard unexpectedly.
     */

    if (
      window.innerWidth > 700
    ) {

      promptInput.focus();

    }

  }
);