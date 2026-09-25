// =========================================================
// BACKEND
// =========================================================

const BACKEND_URL =
    "https://ai-chatbot-website-zlqu.onrender.com";


// =========================================================
// ELEMENTS
// =========================================================

const input =
    document.getElementById("userInput");

const chatbox =
    document.getElementById("chatbox");

const sendButton =
    document.getElementById("sendButton");

const pdfInput =
    document.getElementById("pdfInput");

const imageInput =
    document.getElementById("imageInput");

const uploadStatus =
    document.getElementById("uploadStatus");

const attachmentMenu =
    document.getElementById("attachmentMenu");


// =========================================================
// CHAT HISTORY STORAGE
// =========================================================

const HISTORY_KEY =
    "my_ai_chat_history";

let currentMessages = [];


// =========================================================
// STARTUP
// =========================================================

document.addEventListener(
    "DOMContentLoaded",
    function () {

        loadHistoryList();

        autoResizeInput();

    }
);


// =========================================================
// SEND MESSAGE
// =========================================================

async function sendMessage() {

    const message =
        input.value.trim();

    if (message === "") {
        return;
    }


    // Close attachment menu

    closeAttachmentMenu();


    // Disable controls

    input.disabled = true;

    sendButton.disabled = true;


    // -----------------------------------------------------
    // User message
    // -----------------------------------------------------

    addMessage(
        message,
        "user"
    );


    // Save locally

    currentMessages.push({
        role: "user",
        content: message
    });


    input.value = "";

    autoResizeInput();


    scrollChat();


    // -----------------------------------------------------
    // Typing
    // -----------------------------------------------------

    const typingMessage =
        document.createElement("div");

    typingMessage.className =
        "message ai-message";

    typingMessage.innerHTML = `
        <div class="typing">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;

    chatbox.appendChild(
        typingMessage
    );

    scrollChat();


    // -----------------------------------------------------
    // Backend request
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


        if (!response.ok) {

            throw new Error(
                "Backend error " +
                response.status
            );

        }


        const data =
            await response.json();


        typingMessage.remove();


        const reply =
            data.reply ||
            "The AI returned an empty response.";


        addMessage(
            reply,
            "ai"
        );


        // Save AI message

        currentMessages.push({
            role: "assistant",
            content: reply
        });


        // Save conversation

        saveCurrentConversation();


    } catch (error) {

        console.error(
            "CHAT ERROR:",
            error
        );


        typingMessage.remove();


        addMessage(
            "❌ I couldn't connect to the AI backend. Please try again.",
            "ai"
        );

    }


    // Enable again

    input.disabled = false;

    sendButton.disabled = false;

    input.focus();

}


// =========================================================
// ADD MESSAGE
// =========================================================

function addMessage(
    text,
    role
) {

    const message =
        document.createElement("div");

    message.classList.add(
        "message"
    );


    if (role === "user") {

        message.classList.add(
            "user-message"
        );

    } else {

        message.classList.add(
            "ai-message"
        );

    }


    message.textContent =
        text;


    chatbox.appendChild(
        message
    );

}


// =========================================================
// PDF SELECTION
// =========================================================

function selectPDF() {

    closeAttachmentMenu();

    pdfInput.click();

}


// =========================================================
// PDF INPUT CHANGE
// =========================================================

pdfInput.addEventListener(
    "change",
    function () {

        if (
            pdfInput.files &&
            pdfInput.files.length > 0
        ) {

            uploadPDF();

        }

    }
);


// =========================================================
// UPLOAD PDF
// =========================================================

async function uploadPDF() {

    if (
        !pdfInput.files ||
        pdfInput.files.length === 0
    ) {

        return;

    }


    const file =
        pdfInput.files[0];


    if (
        file.type !== "application/pdf" &&
        !file.name
            .toLowerCase()
            .endsWith(".pdf")
    ) {

        uploadStatus.textContent =
            "Please select a PDF file.";

        return;

    }


    uploadStatus.textContent =
        "Uploading PDF and building RAG...";


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
                "Upload failed"
            );

        }


        const data =
            await response.json();


        uploadStatus.textContent =
            "✓ " +
            (
                data.message ||
                "PDF uploaded successfully"
            ) +
            (
                data.chunks_added
                    ? " • " +
                      data.chunks_added +
                      " chunks"
                    : ""
            );


        pdfInput.value = "";


    } catch (error) {

        console.error(
            "PDF ERROR:",
            error
        );


        uploadStatus.textContent =
            "❌ Could not upload PDF.";

    }

}


// =========================================================
// IMAGE SELECTION
// =========================================================

function selectImage() {

    closeAttachmentMenu();

    imageInput.click();

}


// =========================================================
// IMAGE INPUT
// =========================================================

imageInput.addEventListener(
    "change",
    function () {

        if (
            imageInput.files &&
            imageInput.files.length > 0
        ) {

            const file =
                imageInput.files[0];


            uploadStatus.textContent =
                "Image selected. Vision integration will be added next.";


            imageInput.value = "";

        }

    }
);


// =========================================================
// ATTACHMENT MENU
// =========================================================

function toggleAttachmentMenu() {

    attachmentMenu.classList.toggle(
        "show"
    );

}


function closeAttachmentMenu() {

    attachmentMenu.classList.remove(
        "show"
    );

}


// =========================================================
// CLICK OUTSIDE ATTACHMENT MENU
// =========================================================

document.addEventListener(
    "click",
    function (event) {

        const plusButton =
            document.getElementById(
                "plusButton"
            );


        if (
            attachmentMenu &&
            !attachmentMenu.contains(event.target) &&
            !plusButton.contains(event.target)
        ) {

            closeAttachmentMenu();

        }

    }
);


// =========================================================
// NEW CHAT
// =========================================================

async function newChat() {

    // Save existing conversation

    if (
        currentMessages.length > 0
    ) {

        saveCurrentConversation();

    }


    try {

        await fetch(
            BACKEND_URL + "/reset",
            {
                method: "POST"
            }
        );

    } catch (error) {

        console.error(
            "RESET ERROR:",
            error
        );

    }


    // Clear current messages

    currentMessages = [];


    // Reset screen

    chatbox.innerHTML = `

        <div class="welcome">

            <div class="welcome-logo">
                AI
            </div>

            <h2>
                How can I help you?
            </h2>

            <p>
                Ask me anything or upload a document
                to give me additional knowledge.
            </p>

        </div>

        <div class="message ai-message">

            Hello! I am your AI assistant.
            How can I help you today?

        </div>

    `;


    showSection(
        "chat"
    );


    input.value = "";

    autoResizeInput();

    input.focus();

}


// =========================================================
// SAVE CURRENT CONVERSATION
// =========================================================

function saveCurrentConversation() {

    if (
        currentMessages.length === 0
    ) {

        return;

    }


    const histories =
        getHistories();


    // Create title from first user message

    const firstUserMessage =
        currentMessages.find(
            message =>
                message.role === "user"
        );


    const title =
        firstUserMessage
            ? firstUserMessage.content
                .substring(0, 45)
            : "New conversation";


    const conversation = {

        id:
            Date.now(),

        title:
            title,

        date:
            new Date().toLocaleString(),

        messages:
            [...currentMessages]

    };


    histories.unshift(
        conversation
    );


    // Keep latest 30

    const limited =
        histories.slice(
            0,
            30
        );


    localStorage.setItem(
        HISTORY_KEY,
        JSON.stringify(
            limited
        )
    );


    loadHistoryList();

}


// =========================================================
// GET HISTORY
// =========================================================

function getHistories() {

    try {

        return JSON.parse(
            localStorage.getItem(
                HISTORY_KEY
            )
        ) || [];

    } catch {

        return [];

    }

}


// =========================================================
// LOAD HISTORY LIST
// =========================================================

function loadHistoryList() {

    const list =
        document.getElementById(
            "historyList"
        );


    if (!list) {
        return;
    }


    const histories =
        getHistories();


    list.innerHTML = "";


    if (
        histories.length === 0
    ) {

        list.innerHTML = `

            <div class="history-empty">

                No conversations yet.

                <br>

                Start a new chat and your
                conversations will appear here.

            </div>

        `;

        return;

    }


    histories.forEach(
        conversation => {

            const item =
                document.createElement(
                    "button"
                );


            item.className =
                "history-item";


            item.innerHTML = `

                <div>

                    <div class="history-title">

                        ${escapeHTML(
                            conversation.title
                        )}

                    </div>

                    <div class="history-date">

                        ${escapeHTML(
                            conversation.date
                        )}

                    </div>

                </div>

                <div class="history-arrow">
                    →
                </div>

            `;


            item.onclick =
                function () {

                    restoreConversation(
                        conversation.id
                    );

                };


            list.appendChild(
                item
            );

        }
    );

}


// =========================================================
// RESTORE CONVERSATION
// =========================================================

function restoreConversation(
    id
) {

    const histories =
        getHistories();


    const conversation =
        histories.find(
            item =>
                item.id === id
        );


    if (!conversation) {
        return;
    }


    currentMessages =
        [
            ...conversation.messages
        ];


    chatbox.innerHTML = "";


    currentMessages.forEach(
        message => {

            addMessage(
                message.content,
                message.role === "user"
                    ? "user"
                    : "ai"
            );

        }
    );


    showSection(
        "chat"
    );


    scrollChat();

}


// =========================================================
// CLEAR HISTORY
// =========================================================

function clearChatHistory() {

    const confirmed =
        confirm(
            "Delete all saved chat history?"
        );


    if (!confirmed) {
        return;
    }


    localStorage.removeItem(
        HISTORY_KEY
    );


    currentMessages = [];


    loadHistoryList();

}


// =========================================================
// HTML ESCAPE
// =========================================================

function escapeHTML(
    text
) {

    const div =
        document.createElement(
            "div"
        );


    div.textContent =
        text;


    return div.innerHTML;

}


// =========================================================
// SECTION NAVIGATION
// =========================================================

function showSection(
    section
) {

    const sections = {

        chat:
            "chatSection",

        history:
            "historySection",

        documents:
            "documentsSection",

        vision:
            "visionSection",

        hardware:
            "hardwareSection",

        settings:
            "settingsSection"

    };


    // Hide all

    document
        .querySelectorAll(".section")
        .forEach(
            element => {

                element.classList.remove(
                    "active"
                );

            }
        );


    // Show selected

    const target =
        document.getElementById(
            sections[section]
        );


    if (target) {

        target.classList.add(
            "active"
        );

    }


    // Active sidebar button

    document
        .querySelectorAll(
            ".nav-item"
        )
        .forEach(
            item => {

                item.classList.remove(
                    "active"
                );


                if (
                    item.dataset.section ===
                    section
                ) {

                    item.classList.add(
                        "active"
                    );

                }

            }
        );


    // Header

    const titles = {

        chat: [
            "Chat",
            "AI Assistant"
        ],

        history: [
            "Chat history",
            "Your conversations"
        ],

        documents: [
            "Documents",
            "PDF & RAG"
        ],

        vision: [
            "Vision",
            "AI image understanding"
        ],

        hardware: [
            "Hardware",
            "AI hardware control"
        ],

        settings: [
            "Settings",
            "AI Assistant settings"
        ]

    };


    document.getElementById(
        "pageTitle"
    ).textContent =
        titles[section][0];


    document.getElementById(
        "pageSubtitle"
    ).textContent =
        titles[section][1];


    // Close mobile sidebar

    if (
        window.innerWidth <= 700
    ) {

        document
            .getElementById("sidebar")
            .classList.remove(
                "open"
            );

    }


    if (
        section === "history"
    ) {

        loadHistoryList();

    }

}


// =========================================================
// MOBILE SIDEBAR
// =========================================================

function toggleSidebar() {

    document
        .getElementById("sidebar")
        .classList.toggle(
            "open"
        );

}


// =========================================================
// AUTO RESIZE TEXTAREA
// =========================================================

function autoResizeInput() {

    input.style.height =
        "auto";


    input.style.height =
        Math.min(
            input.scrollHeight,
            150
        ) + "px";

}


// =========================================================
// TEXTAREA EVENTS
// =========================================================

input.addEventListener(
    "input",
    autoResizeInput
);


input.addEventListener(
    "keydown",
    function (event) {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            if (
                !sendButton.disabled
            ) {

                sendMessage();

            }

        }

    }
);


// =========================================================
// SCROLL
// =========================================================

function scrollChat() {

    chatbox.scrollTop =
        chatbox.scrollHeight;

}
