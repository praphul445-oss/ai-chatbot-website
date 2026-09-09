async function sendMessage() {

    // -----------------------------
    // Get input
    // -----------------------------

    const input = document.getElementById("userInput");
    const message = input.value.trim();

    if (message === "") {
        return;
    }

    // -----------------------------
    // Get chatbox
    // -----------------------------

    const chatbox = document.getElementById("chatbox");


    // -----------------------------
    // Add USER message
    // -----------------------------

    const userMessage = document.createElement("div");

    userMessage.classList.add("message", "user-message");
    userMessage.textContent = message;

    chatbox.appendChild(userMessage);

    // Clear input
    input.value = "";

    // Scroll down
    chatbox.scrollTop = chatbox.scrollHeight;


    // -----------------------------
    // Add THINKING message
    // -----------------------------

    const thinkingMessage = document.createElement("div");

    thinkingMessage.classList.add("message", "ai-message");
    thinkingMessage.textContent = "Thinking...";

    chatbox.appendChild(thinkingMessage);

    chatbox.scrollTop = chatbox.scrollHeight;


    try {

        // -----------------------------
        // Send message to FastAPI
        // -----------------------------

        const response = await fetch(
            "http://127.0.0.1:8000/chat",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    message: message
                })
            }
        );


        // -----------------------------
        // Check server response
        // -----------------------------

        if (!response.ok) {
            throw new Error(
                "Backend error: " + response.status
            );
        }


        // -----------------------------
        // Convert response to JSON
        // -----------------------------

        const data = await response.json();


        // -----------------------------
        // REMOVE "Thinking..."
        // -----------------------------

        thinkingMessage.remove();


        // -----------------------------
        // Create AI message
        // -----------------------------

        const aiMessage = document.createElement("div");

        aiMessage.classList.add(
            "message",
            "ai-message"
        );


        // -----------------------------
        // Get AI response
        // -----------------------------

        if (data.reply) {

            aiMessage.textContent = data.reply;

        } else {

            aiMessage.textContent =
                "⚠️ The AI returned an empty response.";

        }


        // -----------------------------
        // Add AI response
        // -----------------------------

        chatbox.appendChild(aiMessage);

        chatbox.scrollTop = chatbox.scrollHeight;


    } catch (error) {

        // -----------------------------
        // Show error in console
        // -----------------------------

        console.error("CHAT ERROR:", error);


        // -----------------------------
        // Remove "Thinking..."
        // -----------------------------

        thinkingMessage.remove();


        // -----------------------------
        // Create error message
        // -----------------------------

        const errorMessage = document.createElement("div");

        errorMessage.classList.add(
            "message",
            "ai-message"
        );

        errorMessage.textContent =
            "❌ Error: Cannot connect to AI backend.";


        // -----------------------------
        // Add error message
        // -----------------------------

        chatbox.appendChild(errorMessage);

        chatbox.scrollTop = chatbox.scrollHeight;
    }
}


// =====================================
// PRESS ENTER TO SEND
// =====================================

document
    .getElementById("userInput")
    .addEventListener("keydown", function(event) {

        if (event.key === "Enter") {

            event.preventDefault();

            sendMessage();
        }

    });