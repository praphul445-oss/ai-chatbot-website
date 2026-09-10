// =========================================================
// BACKEND
// =========================================================

const BACKEND_URL =
    "https://ai-chatbot-website-zlqu.onrender.com";


// =========================================================
// ELEMENTS
// =========================================================

const input = document.getElementById("userInput");
const chatbox = document.getElementById("chatbox");
const sendButton = document.getElementById("sendButton");
const pdfInput = document.getElementById("pdfInput");
const uploadStatus = document.getElementById("uploadStatus");


// =========================================================
// SEND MESSAGE
// =========================================================

async function sendMessage() {

    const message = input.value.trim();

    if (message === "") {
        return;
    }


    // -----------------------------------------------------
    // Disable input while AI is responding
    // -----------------------------------------------------

    input.disabled = true;
    sendButton.disabled = true;


    // -----------------------------------------------------
    // Show user message
    // -----------------------------------------------------

    const userMessage =
        document.createElement("div");

    userMessage.classList.add(
        "message",
        "user-message"
    );

    userMessage.textContent = message;

    chatbox.appendChild(userMessage);


    // Clear input

    input.value = "";

    chatbox.scrollTop =
        chatbox.scrollHeight;


    // -----------------------------------------------------
    // Show typing animation
    // -----------------------------------------------------

    const thinkingMessage =
        document.createElement("div");

    thinkingMessage.classList.add(
        "message",
        "ai-message"
    );

    thinkingMessage.innerHTML = `
        <div class="typing">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;

    chatbox.appendChild(
        thinkingMessage
    );

    chatbox.scrollTop =
        chatbox.scrollHeight;


    // -----------------------------------------------------
    // Send request to backend
    // -----------------------------------------------------

    try {

        const response =
            await fetch(
                BACKEND_URL + "/chat",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message: message
                    })
                }
            );


        // -------------------------------------------------
        // Check response
        // -------------------------------------------------

        if (!response.ok) {

            throw new Error(
                "Backend error: " +
                response.status
            );
        }


        const data =
            await response.json();


        // Remove typing animation

        thinkingMessage.remove();


        // -------------------------------------------------
        // Create AI message
        // -------------------------------------------------

        const aiMessage =
            document.createElement("div");

        aiMessage.classList.add(
            "message",
            "ai-message"
        );


        if (data.reply) {

            aiMessage.textContent =
                data.reply;

        } else {

            aiMessage.textContent =
                "⚠️ The AI returned an empty response.";
        }


        chatbox.appendChild(
            aiMessage
        );


        chatbox.scrollTop =
            chatbox.scrollHeight;


    } catch (error) {

        console.error(
            "CHAT ERROR:",
            error
        );


        // Remove typing message

        thinkingMessage.remove();


        // -------------------------------------------------
        // Show error
        // -------------------------------------------------

        const errorMessage =
            document.createElement("div");

        errorMessage.classList.add(
            "message",
            "ai-message"
        );

        errorMessage.textContent =
            "❌ I couldn't connect to the AI backend. Please try again.";


        chatbox.appendChild(
            errorMessage
        );


        chatbox.scrollTop =
            chatbox.scrollHeight;
    }


    // -----------------------------------------------------
    // Enable input again
    // -----------------------------------------------------

    input.disabled = false;
    sendButton.disabled = false;

    input.focus();
}


// =========================================================
// PDF UPLOAD / RAG
// =========================================================

async function uploadPDF() {

    if (
        !pdfInput ||
        pdfInput.files.length === 0
    ) {

        uploadStatus.textContent =
            "⚠️ Please select a PDF first.";

        return;
    }


    const file =
        pdfInput.files[0];


    // -----------------------------------------------------
    // Check PDF
    // -----------------------------------------------------

    if (
        file.type !== "application/pdf" &&
        !file.name
            .toLowerCase()
            .endsWith(".pdf")
    ) {

        uploadStatus.textContent =
            "❌ Please select a PDF file.";

        return;
    }


    // -----------------------------------------------------
    // Upload status
    // -----------------------------------------------------

    uploadStatus.textContent =
        "⏳ Uploading PDF and building RAG...";


    try {

        const formData =
            new FormData();

        formData.append(
            "file",
            file
        );


        const response =
            await fetch(
                BACKEND_URL + "/upload",
                {
                    method: "POST",
                    body: formData
                }
            );


        if (!response.ok) {

            throw new Error(
                "Upload error: " +
                response.status
            );
        }


        const data =
            await response.json();


        // -------------------------------------------------
        // Success
        // -------------------------------------------------

        if (data.success) {

            uploadStatus.textContent =
                "✅ " +
                data.message +
                " | " +
                data.chunks_added +
                " chunks added.";


            // Clear file selector

            pdfInput.value = "";


        } else {

            uploadStatus.textContent =
                "❌ " +
                data.message;
        }


    } catch (error) {

        console.error(
            "PDF UPLOAD ERROR:",
            error
        );


        uploadStatus.textContent =
            "❌ Could not upload PDF. Check that the backend is running.";
    }
}


// =========================================================
// NEW CHAT / RESET
// =========================================================

async function newChat() {

    try {

        const response =
            await fetch(
                BACKEND_URL + "/reset",
                {
                    method: "POST"
                }
            );


        if (!response.ok) {

            throw new Error(
                "Reset failed"
            );
        }


        // -------------------------------------------------
        // Clear chat screen
        // -------------------------------------------------

        chatbox.innerHTML = `
            <div class="message ai-message">
                👋 New chat started!
                How can I help you?
            </div>
        `;


        input.value = "";

        input.focus();


    } catch (error) {

        console.error(
            "RESET ERROR:",
            error
        );


        const errorMessage =
            document.createElement("div");

        errorMessage.classList.add(
            "message",
            "ai-message"
        );

        errorMessage.textContent =
            "❌ Could not reset the conversation.";


        chatbox.appendChild(
            errorMessage
        );
    }
}


// =========================================================
// CREATE NEW CHAT BUTTON
// =========================================================

const newChatButton =
    document.createElement("button");

newChatButton.textContent =
    "🔄 New Chat";

newChatButton.type =
    "button";

newChatButton.style.padding =
    "10px 16px";

newChatButton.style.border =
    "none";

newChatButton.style.borderRadius =
    "10px";

newChatButton.style.background =
    "#334155";

newChatButton.style.color =
    "white";

newChatButton.style.fontSize =
    "14px";

newChatButton.style.fontWeight =
    "600";

newChatButton.style.cursor =
    "pointer";

newChatButton.onclick =
    newChat;


// Put New Chat button in header

const header =
    document.querySelector(
        ".chat-header"
    );

if (header) {

    header.style.position =
        "relative";

    header.appendChild(
        newChatButton
    );
}


// =========================================================
// ENTER KEY
// =========================================================

input.addEventListener(
    "keydown",
    function(event) {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            if (!sendButton.disabled) {
                sendMessage();
            }
        }
    }
);