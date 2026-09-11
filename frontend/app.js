const chatForm =
    document.getElementById("chatForm");

const promptInput =
    document.getElementById("promptInput");

const chatMessages =
    document.getElementById("chatMessages");

const themeButton =
    document.getElementById("themeButton");

const suggestions =
    document.getElementById("suggestions");

const sendButton =
    document.querySelector(".send-button");

const attachmentButton =
    document.getElementById("attachmentButton");

const microphoneButton =
    document.getElementById("microphoneButton");


/* =========================================================
   API CONFIGURATION
========================================================= */

const API_BASE_URL =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1"
        ? "http://localhost:8000"
        : "";


/* =========================================================
   REQUEST LIMITS
========================================================= */

const MAX_PROMPT_LENGTH = 4000;

const REQUEST_TIMEOUT = 125000;


/* =========================================================
   INITIAL WELCOME STATE
========================================================= */

const initialWelcomeMarkup = `
    <div
        class="welcome-state"
        id="welcomeState"
    >
        <h2>
            What would you like to know?
        </h2>

        <p>
            Ask naturally. Learn something new.
            Understand things more clearly.
        </p>
    </div>
`;


/* =========================================================
   CONBOT ERROR
========================================================= */

class ConbotError extends Error {

    constructor(type, message) {

        super(message);

        this.name =
            "ConbotError";

        this.type =
            type;
    }
}


/* =========================================================
   ASK CONBOT
========================================================= */

async function askConbot(prompt) {

    const controller =
        new AbortController();

    const timeoutId =
        setTimeout(
            () => controller.abort(),
            REQUEST_TIMEOUT
        );

    try {

        const response =
            await fetch(
                `${API_BASE_URL}/ask`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        prompt: prompt
                    }),

                    signal:
                        controller.signal
                }
            );


        /* -----------------------------------------
           HTTP ERROR HANDLING
        ----------------------------------------- */

        if (!response.ok) {

            switch (response.status) {

                case 400:

                    throw new ConbotError(
                        "INVALID_REQUEST",
                        "The request could not be processed."
                    );


                case 429:

                    throw new ConbotError(
                        "RATE_LIMITED",
                        "Too many requests."
                    );


                case 503:

                    throw new ConbotError(
                        "SERVICE_UNAVAILABLE",
                        "The AI service is temporarily unavailable."
                    );


                case 504:

                    throw new ConbotError(
                        "SERVICE_TIMEOUT",
                        "The AI service took too long to respond."
                    );


                default:

                    if (
                        response.status >= 500
                    ) {

                        throw new ConbotError(
                            "SERVER_ERROR",
                            "The server is temporarily unavailable."
                        );
                    }


                    throw new ConbotError(
                        "REQUEST_FAILED",
                        "The request could not be completed."
                    );
            }
        }


        /* -----------------------------------------
           PARSE RESPONSE
        ----------------------------------------- */

        let data;

        try {

            data =
                await response.json();

        } catch (_) {

            throw new ConbotError(
                "INVALID_RESPONSE",
                "The server returned an invalid response."
            );
        }


        /* -----------------------------------------
           VALIDATE ANSWER
        ----------------------------------------- */

        if (
            !data ||
            typeof data.answer !== "string" ||
            !data.answer.trim()
        ) {

            throw new ConbotError(
                "INVALID_RESPONSE",
                "The AI service returned an invalid answer."
            );
        }


        return data.answer;


    } catch (error) {

        /* -----------------------------------------
           REQUEST TIMEOUT
        ----------------------------------------- */

        if (
            error.name ===
            "AbortError"
        ) {

            throw new ConbotError(
                "SERVICE_TIMEOUT",
                "The request timed out."
            );
        }


        /* -----------------------------------------
           OUR OWN CONTROLLED ERRORS
        ----------------------------------------- */

        if (
            error instanceof
            ConbotError
        ) {

            throw error;
        }


        /* -----------------------------------------
           NETWORK FAILURE
        ----------------------------------------- */

        throw new ConbotError(
            "NETWORK_ERROR",
            "Unable to connect to ConBOT."
        );


    } finally {

        clearTimeout(
            timeoutId
        );
    }
}


/* =========================================================
   USER-FRIENDLY ERROR MESSAGE
========================================================= */

function getErrorMessage(error) {

    switch (error?.type) {

        case "RATE_LIMITED":

            return (
                "You're sending questions a little too quickly. " +
                "Please wait a moment and try again."
            );


        case "SERVICE_TIMEOUT":

            return (
                "ConBOT is taking longer than expected. " +
                "Please try again."
            );


        case "SERVICE_UNAVAILABLE":

            return (
                "ConBOT is temporarily unavailable. " +
                "Please try again in a few minutes."
            );


        case "INVALID_REQUEST":

            return (
                "We couldn't process that question. " +
                "Please check it and try again."
            );


        case "INVALID_RESPONSE":

            return (
                "ConBOT couldn't complete that answer. " +
                "Please try again."
            );


        case "NETWORK_ERROR":

            return (
                "We're having trouble connecting to ConBOT right now. " +
                "Please try again in a moment."
            );


        case "SERVER_ERROR":

            return (
                "ConBOT is temporarily unavailable. " +
                "Please try again in a few minutes."
            );


        default:

            return (
                "Something went wrong. " +
                "Please try again in a moment."
            );
    }
}


/* =========================================================
   ADD MESSAGE
========================================================= */

function addMessage(text, sender) {

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


    /* -----------------------------------------
       USER MESSAGE
    ----------------------------------------- */

    if (
        sender === "user"
    ) {

        message.innerHTML = `
            <div class="message-content">
                <div class="message-text"></div>
            </div>
        `;

    }


    /* -----------------------------------------
       ASSISTANT MESSAGE
    ----------------------------------------- */

    else {

        message.innerHTML = `
            <div class="avatar">
                AI
            </div>

            <div class="message-content">

                <div class="message-name">
                    ConBOT
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
       SECURITY:
       Use textContent rather than innerHTML
       for user/model generated content.
    */

    messageText.textContent =
        text;


    chatMessages.appendChild(
        message
    );


    chatMessages.scrollTop =
        chatMessages.scrollHeight;
}


/* =========================================================
   THINKING STATE
========================================================= */

function setLoading(isLoading) {

    const existing =
        document.getElementById(
            "typingIndicator"
        );


    /* -----------------------------------------
       START THINKING
    ----------------------------------------- */

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
                    ConBOT
                </div>

                <div
                    class="message-text typing-state"
                    role="status"
                    aria-live="polite"
                >
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


    /* -----------------------------------------
       STOP THINKING
    ----------------------------------------- */

    if (
        !isLoading &&
        existing
    ) {

        existing.remove();
    }
}


/* =========================================================
   SUBMIT CHAT
========================================================= */

async function handleSubmit(event) {

    event.preventDefault();


    if (
        !promptInput ||
        promptInput.disabled
    ) {

        return;
    }


    const prompt =
        promptInput.value.trim();


    /* -----------------------------------------
       EMPTY INPUT
    ----------------------------------------- */

    if (!prompt) {

        promptInput.focus();

        return;
    }


    /* -----------------------------------------
       LENGTH VALIDATION
    ----------------------------------------- */

    if (
        prompt.length >
        MAX_PROMPT_LENGTH
    ) {

        addMessage(
            "Your question is too long. Please keep it under 4,000 characters.",
            "assistant"
        );


        promptInput.focus();

        return;
    }


    /* -----------------------------------------
       DISABLE UI
    ----------------------------------------- */

    promptInput.disabled =
        true;


    if (sendButton) {

        sendButton.disabled =
            true;
    }


    /* -----------------------------------------
       ADD USER MESSAGE
    ----------------------------------------- */

    addMessage(
        prompt,
        "user"
    );


    promptInput.value =
        "";


    promptInput.style.height =
        "auto";


    /* -----------------------------------------
       SHOW THINKING
    ----------------------------------------- */

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


    } catch (error) {

        console.error(
            "ConBOT request failed:",
            error
        );


        addMessage(
            getErrorMessage(error),
            "assistant"
        );


    } finally {

        setLoading(false);


        promptInput.disabled =
            false;


        if (sendButton) {

            sendButton.disabled =
                false;
        }


        promptInput.focus();
    }
}


/* =========================================================
   FORM SUBMIT
========================================================= */

if (chatForm) {

    chatForm.addEventListener(
        "submit",
        handleSubmit
    );
}


/* =========================================================
   AUTO-RESIZE TEXTAREA
========================================================= */

if (promptInput) {

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
}


/* =========================================================
   ENTER TO SEND
========================================================= */

if (promptInput) {

    promptInput.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Enter" &&
                !event.shiftKey
            ) {

                event.preventDefault();


                if (chatForm) {

                    chatForm.requestSubmit();
                }
            }
        }
    );
}


/* =========================================================
   EXAMPLE PROMPTS
========================================================= */

if (suggestions) {

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


            const prompt =
                button.dataset.prompt;


            if (
                !prompt ||
                prompt.length >
                MAX_PROMPT_LENGTH
            ) {

                return;
            }


            promptInput.value =
                prompt;


            promptInput.focus();


            promptInput.dispatchEvent(
                new Event(
                    "input"
                )
            );
        }
    );
}


/* =========================================================
   DARK MODE
========================================================= */

if (themeButton) {

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
}


/* =========================================================
   RESTORE THEME
========================================================= */

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


/* =========================================================
   FUTURE FEATURES
========================================================= */

/*
   These controls are intentionally not wired yet.

   File upload:
   attachmentButton

   Microphone:
   microphoneButton

   We will implement these properly in the next phase
   instead of adding fake functionality.
*/


if (attachmentButton) {

    attachmentButton.addEventListener(
        "click",
        () => {

            /*
               File upload will be implemented
               in the document Q&A phase.
            */

            console.info(
                "ConBOT file upload will be added next."
            );
        }
    );
}


if (microphoneButton) {

    microphoneButton.addEventListener(
        "click",
        () => {

            /*
               Microphone transcription will be implemented
               after document upload.
            */

            console.info(
                "ConBOT microphone will be added next."
            );
        }
    );
}


/* =========================================================
   INITIAL FOCUS
========================================================= */

window.addEventListener(
    "load",
    () => {

        if (
            window.innerWidth > 700 &&
            promptInput
        ) {

            promptInput.focus();
        }
    }
);