document.addEventListener("DOMContentLoaded", function() {
    const chatWindow = document.getElementById("chat-window");
    const chatInput = document.getElementById("chat-input");
    const sendButton = document.getElementById("send-button");

    function addMessage(message, sender) {
        const messageElement = document.createElement("div");
        messageElement.classList.add("chat-message", `${sender}-message`);
        
        if (sender === 'bot') {
            // Sanitize and format the bot's response
            const formattedMessage = message.answer.replace(/\n/g, '<br>');
            let sourcesHTML = '<div class="source-documents mt-2">';
            sourcesHTML += '<strong>출처 문서:</strong><ul>';
            message.documents.forEach(doc => {
                sourcesHTML += `<li>${doc.source}</li>`;
            });
            sourcesHTML += '</ul></div>';
            messageElement.innerHTML = `<p>${formattedMessage}</p>${sourcesHTML}`;
        } else {
            messageElement.innerHTML = `<p>${message}</p>`;
        }
        
        chatWindow.appendChild(messageElement);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function showTypingIndicator() {
        const typingIndicator = document.createElement("div");
        typingIndicator.id = "typing-indicator";
        typingIndicator.classList.add("chat-message", "bot-message");
        typingIndicator.innerHTML = `<p>답변을 생성하는 중...</p>`;
        chatWindow.appendChild(typingIndicator);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function removeTypingIndicator() {
        const typingIndicator = document.getElementById("typing-indicator");
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    async function sendMessage() {
        const question = chatInput.value.trim();
        if (question === "") {
            return;
        }

        addMessage(question, "user");
        chatInput.value = "";
        showTypingIndicator();

        try {
            const response = await fetch("/chatbot/ask", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ question: question }),
            });

            removeTypingIndicator();

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            addMessage(data, "bot");

        } catch (error) {
            console.error("Error:", error);
            removeTypingIndicator();
            addMessage({ answer: "죄송합니다, 답변을 생성하는 동안 오류가 발생했습니다.", documents: [] }, "bot");
        }
    }

    sendButton.addEventListener("click", sendMessage);
    chatInput.addEventListener("keypress", function(event) {
        if (event.key === "Enter") {
            sendMessage();
        }
    });
});
