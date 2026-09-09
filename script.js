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

    input.value = "";

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
        // Remove Thinking
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

        console.error(
            "CHAT ERROR:",
            error
        );


        // -----------------------------
        // Remove Thinking
        // -----------------------------

        thinkingMessage.remove();


        // -----------------------------
        // Create error message
        // -----------------------------

        const errorMessage =
            document.createElement("div");

        errorMessage.classList.add(
            "message",
            "ai-message"
        );

        errorMessage.textContent =
            "❌ Error: Cannot connect to AI backend.";


        chatbox.appendChild(errorMessage);

        chatbox.scrollTop =
            chatbox.scrollHeight;
    }
}


// =====================================
// PDF UPLOAD
// =====================================

async function uploadPDF() {

    // -----------------------------
    // Get selected PDF
    // -----------------------------

    const pdfInput =
        document.getElementById("pdfInput");

    const uploadStatus =
        document.getElementById("uploadStatus");


    // -----------------------------
    // Check if PDF selected
    // -----------------------------

    if (pdfInput.files.length === 0) {

        uploadStatus.textContent =
            "⚠️ Please select a PDF first.";

        return;
    }


    const file = pdfInput.files[0];


    // -----------------------------
    // Check file type
    // -----------------------------

    if (
        file.type !== "application/pdf" &&
        !file.name.toLowerCase().endsWith(".pdf")
    ) {

        uploadStatus.textContent =
            "❌ Please select a PDF file.";

        return;
    }


    // -----------------------------
    // Show uploading status
    // -----------------------------

    uploadStatus.textContent =
        "⏳ Uploading PDF...";


    try {

        // -----------------------------
        // Create FormData
        // -----------------------------

        const formData = new FormData();

        formData.append(
            "file",
            file
        );


        // -----------------------------
        // Send PDF to FastAPI
        // -----------------------------

        const response = await fetch(
            "http://127.0.0.1:8000/upload",
            {
                method: "POST",

                body: formData
            }
        );


        // -----------------------------
        // Check response
        // -----------------------------

        if (!response.ok) {

            throw new Error(
                "Upload error: " +
                response.status
            );
        }


        // -----------------------------
        // Convert response to JSON
        // -----------------------------

        const data =
            await response.json();


        // -----------------------------
        // Show result
        // -----------------------------

        if (data.success) {

            uploadStatus.textContent =
                "✅ " +
                data.message +
                " | " +
                data.chunks_added +
                " chunks added.";

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
            "❌ Could not upload PDF. Check that the FastAPI server is running.";
    }
}


// =====================================
// PRESS ENTER TO SEND
// =====================================

document
    .getElementById("userInput")
    .addEventListener(
        "keydown",
        function(event) {

            if (event.key === "Enter") {

                event.preventDefault();

                sendMessage();
            }

        }
    );