const chatForm = document.getElementById("chatForm");
const promptInput = document.getElementById("promptInput");
const chatMessages = document.getElementById("chatMessages");
const sendButton = document.querySelector(".send-button");


async function askLlama(prompt) {

    const response = await fetch("/ask", {
        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({
            prompt: prompt
        })
    });

    if (!response.ok) {
        throw new Error(`API request failed: ${response.status}`);
    }

    const data = await response.json();

    return data.answer;
}


chatForm.addEventListener("submit", async function (event) {

    event.preventDefault();

    const prompt = promptInput.value.trim();

    if (!prompt) {
        return;
    }

    addMessage(prompt, "user");

    promptInput.value = "";

    try {

        const answer = await askLlama(prompt);

        addMessage(answer, "assistant");

    } catch (error) {

        console.error("AI request failed:", error);

        addMessage(
            "Sorry, I couldn't connect to the AI service.",
            "assistant"
        );
    }
});


function addMessage(text, sender) {

    const message = document.createElement("div");

    message.className = `message ${sender}`;


    if (sender === "user") {

        message.innerHTML = `
            <div class="message-content">
                <div class="message-name">You</div>
                <div class="message-text"></div>
            </div>
        `;

    } else {

        message.innerHTML = `
            <div class="avatar">AI</div>

            <div class="message-content">
                <div class="message-name">Conbot</div>
                <div class="message-text"></div>
            </div>
        `;
    }


    const messageText =
        message.querySelector(".message-text");


    if (
        sender === "assistant" &&
        typeof marked !== "undefined"
    ) {

        messageText.innerHTML =
            marked.parse(text);

    } else {

        messageText.textContent = text;
    }


    chatMessages.appendChild(message);

    chatMessages.scrollTop =
        chatMessages.scrollHeight;
}