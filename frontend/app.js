// Update API endpoint to live backend
const API_URL = 'https://llama-chatbot-qb2c.onrender.com/ask';

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

    const data = await response.json();
    addMessageToChat(data.answer, 'assistant');
  } catch (error) {
    console.error('Error:', error);
    addMessageToChat('Sorry, I encountered an error. Please try again.', 'assistant');
  }
}