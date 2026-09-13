// Update API endpoint to live backend
const API_URL = 'https://llama-chatbot-qb2c.onrender.com/ask';

// Add message to chat display
function addMessageToChat(message, sender) {
  const chatMessages = document.getElementById('chatMessages');
  
  // Remove welcome message on first message
  const welcomeMessage = chatMessages.querySelector('.welcome-message');
  if (welcomeMessage) {
    welcomeMessage.remove();
  }

  // Create message element
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${sender}`;
  messageDiv.textContent = message;
  
  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Send message function
async function sendMessage() {
  const userInput = document.getElementById('userInput').value.trim();
  
  if (!userInput) return;

  // Add user message to chat
  addMessageToChat(userInput, 'user');
  document.getElementById('userInput').value = '';

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: userInput,
        model: 'qwen3:14b'
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    addMessageToChat(data.answer, 'assistant');
  } catch (error) {
    console.error('Error:', error);
    addMessageToChat('Sorry, I encountered an error. Please try again.', 'assistant');
  }
}

// Allow Enter key to send message
document.addEventListener('DOMContentLoaded', function() {
  const userInput = document.getElementById('userInput');
  if (userInput) {
    userInput.addEventListener('keypress', function(event) {
      if (event.key === 'Enter') {
        sendMessage();
      }
    });
  }
});