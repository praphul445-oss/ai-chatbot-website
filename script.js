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
            <div class="welcome-section">

                <div class="welcome-icon">
                    🤖
                </div>

                <h2>
                    How can I help you?
                </h2>

                <p>
                    Ask me anything, or upload a PDF
                    to use it as knowledge.
                </p>

            </div>

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
// SIDEBAR SECTION CONTROL
// =========================================================

function showSection(section) {

    // -----------------------------------------------------
    // Get sidebar buttons
    // -----------------------------------------------------

    const navItems =
        document.querySelectorAll(
            ".sidebar .nav-item"
        );


    // -----------------------------------------------------
    // Remove active state
    // -----------------------------------------------------

    navItems.forEach(item => {
        item.classList.remove("active");
    });


    // -----------------------------------------------------
    // Section names
    // -----------------------------------------------------

    const sectionNames = {

        chat: "Chat",

        history: "Chat History",

        documents: "Documents / RAG",

        vision: "Vision",

        hardware: "Hardware",

        settings: "Settings"

    };


    // -----------------------------------------------------
    // Highlight selected section
    // -----------------------------------------------------

    navItems.forEach(item => {

        const text =
            item.innerText.trim();

        if (
            sectionNames[section] &&
            text.includes(
                sectionNames[section]
            )
        ) {

            item.classList.add("active");
        }

    });


    // -----------------------------------------------------
    // Chat
    // -----------------------------------------------------

    if (section === "chat") {

        document
            .querySelector(".main-header h1")
            .textContent = "Chat";

        document
            .querySelector(".main-header p")
            .textContent =
                "Talk with your AI assistant";

        input.focus();

        return;
    }


    // -----------------------------------------------------
    // Chat History
    // -----------------------------------------------------

    if (section === "history") {

        document
            .querySelector(".main-header h1")
            .textContent =
                "Chat History";

        document
            .querySelector(".main-header p")
            .textContent =
                "Your previous conversations";

        alert(
            "Chat History will be added in the next step."
        );

        return;
    }


    // -----------------------------------------------------
    // Documents / RAG
    // -----------------------------------------------------

    if (section === "documents") {

        document
            .querySelector(".main-header h1")
            .textContent =
                "Documents / RAG";

        document
            .querySelector(".main-header p")
            .textContent =
                "Upload documents and use them as AI knowledge";

        alert(
            "Your PDF/RAG system is already connected. We will build the Documents page next."
        );

        return;
    }


    // -----------------------------------------------------
    // Vision
    // -----------------------------------------------------

    if (section === "vision") {

        document
            .querySelector(".main-header h1")
            .textContent =
                "Vision";

        document
            .querySelector(".main-header p")
            .textContent =
                "Image understanding";

        alert(
            "Vision will be added later."
        );

        return;
    }


    // -----------------------------------------------------
    // Hardware
    // -----------------------------------------------------

    if (section === "hardware") {

        document
            .querySelector(".main-header h1")
            .textContent =
                "Hardware";

        document
            .querySelector(".main-header p")
            .textContent =
                "Connect and control your AI hardware";

        alert(
            "Hardware control will be added after the website interface is ready."
        );

        return;
    }


    // -----------------------------------------------------
    // Settings
    // -----------------------------------------------------

    if (section === "settings") {

        document
            .querySelector(".main-header h1")
            .textContent =
                "Settings";

        document
            .querySelector(".main-header p")
            .textContent =
                "Manage your AI assistant";

        alert(
            "Settings will be added later."
        );

        return;
    }
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
