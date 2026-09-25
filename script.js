/* =========================================================
   MY AI ASSISTANT
   Authentication + Chatbot + PDF/RAG + Local History
   ========================================================= */


/* =========================================================
   1. SUPABASE CONFIGURATION
   ========================================================= */

const SUPABASE_URL =
    "https://jjuuilevlddifxoitffp.supabase.co";

const SUPABASE_PUBLISHABLE_KEY =
    "sb_publishable_eQFWdaObL0JtrBmkwqJ_sw_lzbtjt-I";

const supabaseClient =
    window.supabase.createClient(
        SUPABASE_URL,
        SUPABASE_PUBLISHABLE_KEY
    );


/* =========================================================
   2. BACKEND
   ========================================================= */

const BACKEND_URL =
    "https://ai-chatbot-website-zlqu.onrender.com";


/* =========================================================
   3. DOM ELEMENTS
   ========================================================= */

let userInput;
let chatbox;
let sendButton;
let pdfInput;
let imageInput;
let uploadStatus;
let attachmentMenu;

let authScreen;
let appShell;

let authMessage;

let loginButton;
let signupButton;

let userEmail;
let userAvatar;


/* =========================================================
   4. CHAT HISTORY
   ========================================================= */

const HISTORY_KEY =
    "my_ai_chat_history";

let currentMessages = [];


/* =========================================================
   5. INITIALIZATION
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    async function () {

        userInput =
            document.getElementById("userInput");

        chatbox =
            document.getElementById("chatbox");

        sendButton =
            document.getElementById("sendButton");

        pdfInput =
            document.getElementById("pdfInput");

        imageInput =
            document.getElementById("imageInput");

        uploadStatus =
            document.getElementById("uploadStatus");

        attachmentMenu =
            document.getElementById("attachmentMenu");

        authScreen =
            document.getElementById("authScreen");

        appShell =
            document.getElementById("appShell");

        authMessage =
            document.getElementById("authMessage");

        loginButton =
            document.getElementById("loginButton");

        signupButton =
            document.getElementById("signupButton");

        userEmail =
            document.getElementById("userEmail");

        userAvatar =
            document.getElementById("userAvatar");


        /* PDF input */

        if (pdfInput) {

            pdfInput.addEventListener(
                "change",
                function () {

                    if (
                        pdfInput.files &&
                        pdfInput.files.length > 0
                    ) {

                        uploadPDF(
                            pdfInput.files[0]
                        );

                    }

                }
            );

        }


        /* Image input */

        if (imageInput) {

            imageInput.addEventListener(
                "change",
                function () {

                    if (
                        imageInput.files &&
                        imageInput.files.length > 0
                    ) {

                        handleImageSelected(
                            imageInput.files[0]
                        );

                    }

                }
            );

        }


        /* Textarea */

        if (userInput) {

            userInput.addEventListener(
                "input",
                autoResizeInput
            );


            userInput.addEventListener(
                "keydown",
                function (event) {

                    if (
                        event.key === "Enter" &&
                        !event.shiftKey
                    ) {

                        event.preventDefault();

                        sendMessage();

                    }

                }
            );

        }


        /* Supabase authentication listener */

        supabaseClient.auth.onAuthStateChange(
            function (event, session) {

                console.log(
                    "Supabase Auth Event:",
                    event
                );

                handleAuthState(
                    session
                );

            }
        );


        /* Check existing session */

        try {

            const {
                data,
                error
            } = await supabaseClient.auth.getSession();


            if (error) {

                console.error(
                    "Session error:",
                    error
                );

                showLoginScreen();

                return;

            }


            handleAuthState(
                data.session
            );

        } catch (error) {

            console.error(
                "Authentication initialization error:",
                error
            );

            showLoginScreen();

        }

    }
);


/* =========================================================
   6. AUTHENTICATION STATE
   ========================================================= */

function handleAuthState(session) {

    if (
        session &&
        session.user
    ) {

        showApp(
            session.user
        );

    } else {

        showLoginScreen();

    }

}


/* =========================================================
   7. SHOW LOGIN SCREEN
   ========================================================= */

function showLoginScreen() {

    if (authScreen) {

        authScreen.hidden = false;

    }


    if (appShell) {

        appShell.hidden = true;

    }


    clearAuthMessage();

}


/* =========================================================
   8. SHOW MAIN APPLICATION
   ========================================================= */

function showApp(user) {

    if (authScreen) {

        authScreen.hidden = true;

    }


    if (appShell) {

        appShell.hidden = false;

    }


    updateUserDisplay(
        user
    );


    loadHistoryList();

    autoResizeInput();

}


/* =========================================================
   9. USER DISPLAY
   ========================================================= */

function updateUserDisplay(user) {

    if (!user) {
        return;
    }


    const email =
        user.email || "User";


    if (userEmail) {

        userEmail.textContent =
            email;

    }


    if (userAvatar) {

        const firstLetter =
            email
                .charAt(0)
                .toUpperCase();

        userAvatar.textContent =
            firstLetter;

    }

}


/* =========================================================
   10. AUTH FORM SWITCHING
   ========================================================= */

function showAuthForm(form) {

    const loginForm =
        document.getElementById(
            "loginForm"
        );

    const signupForm =
        document.getElementById(
            "signupForm"
        );

    const loginTab =
        document.getElementById(
            "loginTab"
        );

    const signupTab =
        document.getElementById(
            "signupTab"
        );


    clearAuthMessage();


    if (form === "login") {

        loginForm.classList.add(
            "active"
        );

        signupForm.classList.remove(
            "active"
        );

        loginTab.classList.add(
            "active"
        );

        signupTab.classList.remove(
            "active"
        );

    } else {

        signupForm.classList.add(
            "active"
        );

        loginForm.classList.remove(
            "active"
        );

        signupTab.classList.add(
            "active"
        );

        loginTab.classList.remove(
            "active"
        );

    }

}


/* =========================================================
   11. AUTH MESSAGE
   ========================================================= */

function showAuthMessage(
    message,
    type = ""
) {

    if (!authMessage) {
        return;
    }


    authMessage.textContent =
        message;


    authMessage.className =
        "auth-message";


    if (type) {

        authMessage.classList.add(
            type
        );

    }

}


function clearAuthMessage() {

    if (!authMessage) {
        return;
    }


    authMessage.textContent = "";

    authMessage.className =
        "auth-message";

}


/* =========================================================
   12. LOGIN
   ========================================================= */

async function loginUser(event) {

    event.preventDefault();


    const email =
        document
            .getElementById("loginEmail")
            .value
            .trim();


    const password =
        document
            .getElementById("loginPassword")
            .value;


    if (
        !email ||
        !password
    ) {

        showAuthMessage(
            "Please enter your email and password.",
            "error"
        );

        return;

    }


    loginButton.disabled =
        true;

    loginButton.textContent =
        "Logging in...";


    clearAuthMessage();


    try {

        const {
            data,
            error
        } = await supabaseClient.auth.signInWithPassword({

            email: email,

            password: password

        });


        if (error) {

            console.error(
                "Login error:",
                error
            );

            showAuthMessage(
                error.message ||
                "Login failed. Please check your details.",
                "error"
            );

            return;

        }


        if (
            data &&
            data.user
        ) {

            showAuthMessage(
                "Login successful.",
                "success"
            );

        }


    } catch (error) {

        console.error(
            "Login exception:",
            error
        );

        showAuthMessage(
            "Something went wrong while logging in.",
            "error"
        );

    } finally {

        loginButton.disabled =
            false;

        loginButton.textContent =
            "Login";

    }

}


/* =========================================================
   13. SIGN UP
   ========================================================= */

async function signupUser(event) {

    event.preventDefault();


    const email =
        document
            .getElementById("signupEmail")
            .value
            .trim();


    const password =
        document
            .getElementById("signupPassword")
            .value;


    const confirmPassword =
        document
            .getElementById(
                "signupConfirmPassword"
            )
            .value;


    if (!email) {

        showAuthMessage(
            "Please enter your email.",
            "error"
        );

        return;

    }


    if (
        password.length < 6
    ) {

        showAuthMessage(
            "Password must be at least 6 characters.",
            "error"
        );

        return;

    }


    if (
        password !==
        confirmPassword
    ) {

        showAuthMessage(
            "Passwords do not match.",
            "error"
        );

        return;

    }


    signupButton.disabled =
        true;

    signupButton.textContent =
        "Creating account...";


    clearAuthMessage();


    try {

        const {
            data,
            error
        } = await supabaseClient.auth.signUp({

            email: email,

            password: password

        });


        if (error) {

            console.error(
                "Signup error:",
                error
            );

            showAuthMessage(
                error.message ||
                "Account creation failed.",
                "error"
            );

            return;

        }


        /*
           If email confirmation is enabled,
           Supabase returns a user without
           an active session.
        */

        if (
            data &&
            data.user &&
            !data.session
        ) {

            showAuthMessage(
                "Account created. Please check your email and verify your account before logging in.",
                "success"
            );

            return;

        }


        if (
            data &&
            data.session
        ) {

            showAuthMessage(
                "Account created successfully.",
                "success"
            );

        }


    } catch (error) {

        console.error(
            "Signup exception:",
            error
        );

        showAuthMessage(
            "Something went wrong while creating your account.",
            "error"
        );

    } finally {

        signupButton.disabled =
            false;

        signupButton.textContent =
            "Create Account";

    }

}


/* =========================================================
   14. LOGOUT
   ========================================================= */

async function logoutUser() {

    try {

        const {
            error
        } = await supabaseClient.auth.signOut();


        if (error) {

            console.error(
                "Logout error:",
                error
            );

            alert(
                "Logout failed. Please try again."
            );

            return;

        }


        currentMessages = [];

        showLoginScreen();


        const loginPassword =
            document.getElementById(
                "loginPassword"
            );


        if (loginPassword) {

            loginPassword.value = "";

        }


    } catch (error) {

        console.error(
            "Logout exception:",
            error
        );

        alert(
            "Something went wrong while logging out."
        );

    }

}


/* =========================================================
   15. SEND CHAT MESSAGE
   ========================================================= */

async function sendMessage() {

    if (!userInput) {
        return;
    }


    const message =
        userInput.value.trim();


    if (!message) {
        return;
    }


    toggleAttachmentMenu(
        false
    );


    if (sendButton) {

        sendButton.disabled =
            true;

    }


    userInput.disabled =
        true;


    addMessage(
        "user",
        message
    );


    currentMessages.push({

        role: "user",

        content: message

    });


    userInput.value = "";

    autoResizeInput();


    const thinkingMessage =
        addMessage(
            "assistant",
            "Thinking..."
        );


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
                "Server returned " +
                response.status
            );

        }


        const data =
            await response.json();


        const reply =
            data.response ||
            data.message ||
            data.reply ||
            "I couldn't generate a response.";


        updateMessage(
            thinkingMessage,
            reply
        );


        currentMessages.push({

            role: "assistant",

            content: reply

        });


        saveCurrentConversation();


    } catch (error) {

        console.error(
            "Chat error:",
            error
        );


        updateMessage(
            thinkingMessage,
            "Sorry, I couldn't connect to the AI server."
        );

    } finally {

        if (sendButton) {

            sendButton.disabled =
                false;

        }


        userInput.disabled =
            false;


        userInput.focus();

    }

}


/* =========================================================
   16. ADD MESSAGE
   ========================================================= */

function addMessage(
    role,
    content
) {

    const messageDiv =
        document.createElement(
            "div"
        );


    messageDiv.className =
        "message " + role;


    const contentDiv =
        document.createElement(
            "div"
        );


    contentDiv.className =
        "message-content";


    contentDiv.textContent =
        content;


    messageDiv.appendChild(
        contentDiv
    );


    chatbox.appendChild(
        messageDiv
    );


    scrollToBottom();


    return messageDiv;

}


/* =========================================================
   17. UPDATE MESSAGE
   ========================================================= */

function updateMessage(
    messageElement,
    content
) {

    if (!messageElement) {
        return;
    }


    const contentDiv =
        messageElement.querySelector(
            ".message-content"
        );


    if (contentDiv) {

        contentDiv.textContent =
            content;

    } else {

        messageElement.textContent =
            content;

    }


    scrollToBottom();

}


/* =========================================================
   18. PDF SELECTION
   ========================================================= */

function selectPDF() {

    if (!pdfInput) {
        return;
    }


    toggleAttachmentMenu(
        false
    );


    pdfInput.click();

}


/* =========================================================
   19. PDF UPLOAD
   ========================================================= */

async function uploadPDF(
    file
) {

    if (!file) {
        return;
    }


    if (
        file.type !==
        "application/pdf"
    ) {

        showUploadStatus(
            "Please select a PDF file.",
            "error"
        );

        return;

    }


    showUploadStatus(
        "Uploading PDF...",
        "loading"
    );


    const formData =
        new FormData();


    formData.append(
        "file",
        file
    );


    try {

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
                "Upload failed with status " +
                response.status
            );

        }


        const data =
            await response.json();


        showUploadStatus(
            data.message ||
            "PDF uploaded successfully.",
            "success"
        );


    } catch (error) {

        console.error(
            "PDF upload error:",
            error
        );


        showUploadStatus(
            "PDF upload failed.",
            "error"
        );

    } finally {

        pdfInput.value = "";

    }

}


/* =========================================================
   20. IMAGE SELECTION
   ========================================================= */

function selectImage() {

    if (!imageInput) {
        return;
    }


    toggleAttachmentMenu(
        false
    );


    imageInput.click();

}


/* =========================================================
   21. IMAGE HANDLING
   ========================================================= */

function handleImageSelected(
    file
) {

    if (!file) {
        return;
    }


    showUploadStatus(
        "Image selected. Vision integration will be added next.",
        "loading"
    );


    imageInput.value = "";

}


/* =========================================================
   22. UPLOAD STATUS
   ========================================================= */

function showUploadStatus(
    message,
    type = ""
) {

    if (!uploadStatus) {
        return;
    }


    uploadStatus.textContent =
        message;


    uploadStatus.className =
        "upload-status";


    if (type) {

        uploadStatus.classList.add(
            type
        );

    }


    if (
        type === "success"
    ) {

        setTimeout(
            function () {

                uploadStatus.textContent =
                    "";

            },
            5000
        );

    }

}


/* =========================================================
   23. ATTACHMENT MENU
   ========================================================= */

function toggleAttachmentMenu(
    forceState
) {

    if (!attachmentMenu) {
        return;
    }


    if (
        typeof forceState ===
        "boolean"
    ) {

        if (forceState) {

            attachmentMenu.classList.add(
                "show"
            );

        } else {

            attachmentMenu.classList.remove(
                "show"
            );

        }

        return;

    }


    attachmentMenu.classList.toggle(
        "show"
    );

}


/* =========================================================
   24. NEW CHAT
   ========================================================= */

async function newChat() {

    saveCurrentConversation();


    currentMessages = [];


    if (chatbox) {

        chatbox.innerHTML = `

            <div class="welcome-message">

                <div class="welcome-icon">
                    🤖
                </div>

                <h2>
                    How can I help you?
                </h2>

                <p>
                    Ask me anything or upload a document
                    to work with your knowledge base.
                </p>

            </div>

        `;

    }


    if (userInput) {

        userInput.value = "";

        autoResizeInput();

        userInput.focus();

    }


    try {

        await fetch(
            BACKEND_URL + "/reset",
            {
                method: "POST"
            }
        );

    } catch (error) {

        console.warn(
            "Backend reset failed:",
            error
        );

    }

}


/* =========================================================
   25. SAVE LOCAL CONVERSATION
   ========================================================= */

function saveCurrentConversation() {

    if (
        !currentMessages ||
        currentMessages.length === 0
    ) {

        return;

    }


    const firstUserMessage =
        currentMessages.find(
            function (message) {

                return message.role ===
                    "user";

            }
        );


    if (!firstUserMessage) {
        return;
    }


    const title =
        firstUserMessage.content
            .substring(0, 45);


    let histories =
        getHistories();


    if (
        histories.length > 0
    ) {

        const latest =
            histories[0];


        if (
            latest &&
            latest.messages &&
            JSON.stringify(
                latest.messages
            ) ===
            JSON.stringify(
                currentMessages
            )
        ) {

            return;

        }

    }


    const conversation = {

        id: Date.now(),

        title:
            title ||
            "New Conversation",

        date:
            new Date().toLocaleString(),

        messages:
            [...currentMessages]

    };


    histories.unshift(
        conversation
    );


    histories =
        histories.slice(
            0,
            30
        );


    localStorage.setItem(
        HISTORY_KEY,
        JSON.stringify(
            histories
        )
    );


    loadHistoryList();

}


/* =========================================================
   26. GET LOCAL HISTORY
   ========================================================= */

function getHistories() {

    try {

        const stored =
            localStorage.getItem(
                HISTORY_KEY
            );


        if (!stored) {

            return [];

        }


        const histories =
            JSON.parse(
                stored
            );


        return Array.isArray(
            histories
        )
            ? histories
            : [];


    } catch (error) {

        console.error(
            "History read error:",
            error
        );

        return [];

    }

}


/* =========================================================
   27. LOAD HISTORY LIST
   ========================================================= */

function loadHistoryList() {

    const historyList =
        document.getElementById(
            "historyList"
        );


    if (!historyList) {
        return;
    }


    const histories =
        getHistories();


    if (
        histories.length === 0
    ) {

        historyList.innerHTML = `

            <div class="empty-state">

                <div class="empty-icon">
                    🕘
                </div>

                <h3>
                    No chat history yet
                </h3>

                <p>
                    Your conversations will appear here.
                </p>

            </div>

        `;

        return;

    }


    historyList.innerHTML = "";


    histories.forEach(
        function (conversation) {

            const item =
                document.createElement(
                    "div"
                );


            item.className =
                "history-item";


            item.innerHTML = `

                <div class="history-item-main">

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

                <button
                    class="history-open-btn"
                    type="button"
                >
                    Open
                </button>

            `;


            const openButton =
                item.querySelector(
                    ".history-open-btn"
                );


            if (openButton) {

                openButton.addEventListener(
                    "click",
                    function () {

                        restoreConversation(
                            conversation.id
                        );

                    }
                );

            }


            historyList.appendChild(
                item
            );

        }
    );

}


/* =========================================================
   28. RESTORE CONVERSATION
   ========================================================= */

function restoreConversation(
    id
) {

    const histories =
        getHistories();


    const conversation =
        histories.find(
            function (item) {

                return item.id === id;

            }
        );


    if (!conversation) {
        return;
    }


    currentMessages =
        [
            ...(conversation.messages || [])
        ];


    if (chatbox) {

        chatbox.innerHTML = "";

    }


    currentMessages.forEach(
        function (message) {

            addMessage(
                message.role,
                message.content
            );

        }
    );


    showSection(
        "chat"
    );


    if (userInput) {

        userInput.focus();

    }

}


/* =========================================================
   29. CLEAR HISTORY
   ========================================================= */

function clearChatHistory() {

    const confirmed =
        confirm(
            "Are you sure you want to clear your local chat history?"
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


/* =========================================================
   30. SECTION NAVIGATION
   ========================================================= */

function showSection(
    section
) {

    const sections = {

        chat:
            document.getElementById(
                "chatSection"
            ),

        history:
            document.getElementById(
                "historySection"
            ),

        documents:
            document.getElementById(
                "documentsSection"
            ),

        vision:
            document.getElementById(
                "visionSection"
            ),

        hardware:
            document.getElementById(
                "hardwareSection"
            ),

        settings:
            document.getElementById(
                "settingsSection"
            )

    };


    Object.values(
        sections
    ).forEach(
        function (element) {

            if (element) {

                element.classList.remove(
                    "active"
                );

            }

        }
    );


    if (
        sections[section]
    ) {

        sections[section].classList.add(
            "active"
        );

    }


    const navItems =
        document.querySelectorAll(
            ".nav-item"
        );


    navItems.forEach(
        function (item) {

            item.classList.remove(
                "active"
            );

        }
    );


    const sectionIndex = {

        chat: 0,

        history: 1,

        documents: 2,

        vision: 3,

        hardware: 4,

        settings: 5

    };


    const index =
        sectionIndex[section];


    if (
        index !== undefined &&
        navItems[index]
    ) {

        navItems[index].classList.add(
            "active"
        );

    }


    const titles = {

        chat: [
            "AI Chat",
            "Your personal AI assistant"
        ],

        history: [
            "Chat History",
            "Your previous conversations"
        ],

        documents: [
            "Documents",
            "Your AI knowledge base"
        ],

        vision: [
            "Vision",
            "Image understanding"
        ],

        hardware: [
            "Hardware",
            "Connect your AI assistant to hardware"
        ],

        settings: [
            "Settings",
            "Manage your assistant"
        ]

    };


    const titleData =
        titles[section];


    if (titleData) {

        const pageTitle =
            document.getElementById(
                "pageTitle"
            );

        const pageSubtitle =
            document.getElementById(
                "pageSubtitle"
            );


        if (pageTitle) {

            pageTitle.textContent =
                titleData[0];

        }


        if (pageSubtitle) {

            pageSubtitle.textContent =
                titleData[1];

        }

    }


    document.body.classList.remove(
        "sidebar-open"
    );

}


/* =========================================================
   31. AUTO RESIZE TEXTAREA
   ========================================================= */

function autoResizeInput() {

    if (!userInput) {
        return;
    }


    userInput.style.height =
        "auto";


    userInput.style.height =
        Math.min(
            userInput.scrollHeight,
            180
        ) + "px";

}


/* =========================================================
   32. SCROLL CHAT
   ========================================================= */

function scrollToBottom() {

    if (!chatbox) {
        return;
    }


    chatbox.scrollTop =
        chatbox.scrollHeight;

}


/* =========================================================
   33. ESCAPE HTML
   ========================================================= */

function escapeHTML(
    value
) {

    const div =
        document.createElement(
            "div"
        );


    div.textContent =
        value == null
            ? ""
            : String(value);


    return div.innerHTML;

}


/* =========================================================
   34. CLOSE ATTACHMENT MENU
   ========================================================= */

document.addEventListener(
    "click",
    function (event) {

        if (!attachmentMenu) {

            return;

        }


        const clickedInsideMenu =
            attachmentMenu.contains(
                event.target
            );


        const clickedButton =
            event.target.closest(
                ".attachment-btn"
            );


        if (
            !clickedInsideMenu &&
            !clickedButton
        ) {

            attachmentMenu.classList.remove(
                "show"
            );

        }

    }
);
