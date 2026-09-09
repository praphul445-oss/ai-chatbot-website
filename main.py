from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import requests
import json
import os
import hashlib
from io import BytesIO

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="My AI Chatbot API",
    description="AI Chatbot with Llama, Memory, RAG and Document Upload",
    version="1.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# REQUEST MODEL
# =========================================================

class ChatRequest(BaseModel):
    message: str


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MEMORY_FILE = os.path.join(
    BASE_DIR,
    "conversation_history.json"
)

RAG_DATABASE_DIR = os.path.join(
    BASE_DIR,
    "rag",
    "chroma_db"
)


# =========================================================
# SETTINGS
# =========================================================

MAX_MEMORY_MESSAGES = 10

CHUNK_SIZE = 800


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = {
    "role": "system",
    "content": """
You are a helpful AI chatbot.

You must remember and use information the user tells you during
the conversation.

If the user tells you their name, remember it and answer correctly
when they later ask for their name.

Do not say that you cannot remember previous messages if those
messages are included in the conversation.

You also have access to a local RAG knowledge base.

The knowledge base can contain information from documents uploaded
by the user.

When relevant information from the RAG knowledge base is provided,
use it to answer the user's question.

If the knowledge base does not contain relevant information,
answer normally using your general knowledge.

Do not claim that information from the local knowledge base came
from the internet.

The user is building an offline-first AI chatbot using:

- Python
- FastAPI
- Ollama
- Llama 3.2 3B
- Conversational memory
- RAG
- ChromaDB
- ESP32 hardware
"""
}


# =========================================================
# START RAG
# =========================================================

print()
print("================================")
print("STARTING RAG")
print("================================")

print("RAG database:", RAG_DATABASE_DIR)


try:

    chroma_client = chromadb.PersistentClient(
        path=RAG_DATABASE_DIR
    )

    embedding_function = (
        embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    )

    collection = chroma_client.get_or_create_collection(
        name="knowledge",
        embedding_function=embedding_function
    )

    print("=== RAG DATABASE CONNECTED ===")

    print(
        "Documents/chunks currently stored:",
        collection.count()
    )

except Exception as e:

    print("RAG ERROR:", e)

    chroma_client = None
    collection = None


# =========================================================
# LOAD MEMORY
# =========================================================

def load_history():

    if not os.path.exists(MEMORY_FILE):

        return [SYSTEM_PROMPT]

    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            history = json.load(file)

        if not isinstance(history, list):

            return [SYSTEM_PROMPT]

        # Remove old system messages
        messages = [
            message
            for message in history
            if message.get("role") != "system"
        ]

        # Keep recent messages
        messages = messages[-MAX_MEMORY_MESSAGES:]

        return [SYSTEM_PROMPT] + messages

    except Exception as e:

        print("ERROR LOADING MEMORY:", e)

        return [SYSTEM_PROMPT]


# =========================================================
# SAVE MEMORY
# =========================================================

def save_history(history):

    # Remove system messages
    messages = [
        message
        for message in history
        if message.get("role") != "system"
    ]

    # Keep only recent messages
    messages = messages[-MAX_MEMORY_MESSAGES:]

    trimmed_history = [
        SYSTEM_PROMPT
    ] + messages

    try:

        with open(
            MEMORY_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                trimmed_history,
                file,
                indent=2,
                ensure_ascii=False
            )

    except Exception as e:

        print("ERROR SAVING MEMORY:", e)

    return trimmed_history


# =========================================================
# STARTUP MEMORY
# =========================================================

conversation_history = load_history()

print()
print("================================")
print("STARTUP: MEMORY LOADED")
print("================================")

print(conversation_history)


# =========================================================
# TEXT CHUNKING
# =========================================================

def split_text(text, chunk_size=CHUNK_SIZE):

    text = text.strip()

    if not text:
        return []

    chunks = []

    for start in range(
        0,
        len(text),
        chunk_size
    ):

        chunk = text[
            start:start + chunk_size
        ].strip()

        if chunk:
            chunks.append(chunk)

    return chunks


# =========================================================
# RAG SEARCH
# =========================================================

def search_rag(query):

    if collection is None:

        print(
            "RAG collection is not available."
        )

        return ""

    try:

        if collection.count() == 0:

            print(
                "RAG database is empty."
            )

            return ""

        results = collection.query(
            query_texts=[query],
            n_results=min(
                3,
                collection.count()
            )
        )

        documents = results.get(
            "documents",
            [[]]
        )[0]

        if not documents:

            print(
                "RAG: No relevant information found."
            )

            return ""

        print()
        print("================================")
        print("RAG SEARCH RESULTS")
        print("================================")

        for document in documents:

            print("--------------------------------")
            print(document)

        return "\n\n".join(documents)

    except Exception as e:

        print(
            "RAG SEARCH ERROR:",
            e
        )

        return ""


# =========================================================
# HOME ROUTE
# =========================================================

@app.get("/")
def home():

    return {
        "message": "AI Chatbot backend is running!",
        "features": [
            "Llama 3.2 3B",
            "Conversation Memory",
            "RAG",
            "TXT Upload",
            "PDF Upload"
        ]
    }


# =========================================================
# UPLOAD DOCUMENT
# =========================================================

@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...)
):

    print()
    print("================================")
    print("NEW DOCUMENT UPLOAD")
    print("================================")

    print("Filename:", file.filename)

    # -----------------------------------------------------
    # CHECK FILE
    # -----------------------------------------------------

    if not file.filename:

        return {
            "success": False,
            "message": "No filename provided."
        }


    filename = file.filename.lower()


    # -----------------------------------------------------
    # CHECK EXTENSION
    # -----------------------------------------------------

    if not (
        filename.endswith(".txt")
        or filename.endswith(".pdf")
    ):

        return {
            "success": False,
            "message": "Only .txt and .pdf files are supported."
        }


    # -----------------------------------------------------
    # READ FILE
    # -----------------------------------------------------

    try:

        file_data = await file.read()

    except Exception as e:

        return {
            "success": False,
            "message": f"Could not read file: {e}"
        }


    if not file_data:

        return {
            "success": False,
            "message": "The uploaded file is empty."
        }


    # -----------------------------------------------------
    # EXTRACT TEXT
    # -----------------------------------------------------

    extracted_text = ""


    # =====================================================
    # TXT FILE
    # =====================================================

    if filename.endswith(".txt"):

        try:

            extracted_text = file_data.decode(
                "utf-8"
            )

        except UnicodeDecodeError:

            try:

                extracted_text = file_data.decode(
                    "utf-8-sig"
                )

            except Exception:

                return {
                    "success": False,
                    "message": "Could not read the TXT file as UTF-8."
                }


    # =====================================================
    # PDF FILE
    # =====================================================

    elif filename.endswith(".pdf"):

        try:

            pdf_file = BytesIO(file_data)

            reader = PdfReader(
                pdf_file
            )

            pages_text = []

            for page_number, page in enumerate(
                reader.pages,
                start=1
            ):

                try:

                    page_text = page.extract_text()

                    if page_text:

                        pages_text.append(
                            page_text
                        )

                except Exception as e:

                    print(
                        f"Could not read page {page_number}:",
                        e
                    )

            extracted_text = "\n\n".join(
                pages_text
            )

        except Exception as e:

            print(
                "PDF ERROR:",
                e
            )

            return {
                "success": False,
                "message": f"Could not read PDF: {e}"
            }


    # -----------------------------------------------------
    # CHECK EXTRACTED TEXT
    # -----------------------------------------------------

    extracted_text = extracted_text.strip()


    if not extracted_text:

        return {
            "success": False,
            "message": (
                "No readable text was found in this document. "
                "If this is a scanned/image-only PDF, "
                "OCR will be needed later."
            )
        }


    # -----------------------------------------------------
    # CHECK RAG
    # -----------------------------------------------------

    if collection is None:

        return {
            "success": False,
            "message": "RAG database is not available."
        }


    # -----------------------------------------------------
    # SPLIT INTO CHUNKS
    # -----------------------------------------------------

    chunks = split_text(
        extracted_text
    )


    if not chunks:

        return {
            "success": False,
            "message": "No usable text chunks were created."
        }


    # -----------------------------------------------------
    # CREATE UNIQUE DOCUMENT ID
    # -----------------------------------------------------

    file_hash = hashlib.sha256(
        file_data
    ).hexdigest()[:16]


    # -----------------------------------------------------
    # CREATE CHROMADB IDS
    # -----------------------------------------------------

    ids = []

    metadatas = []

    for index in range(
        len(chunks)
    ):

        chunk_id = (
            f"{file_hash}_{index}"
        )

        ids.append(
            chunk_id
        )

        metadatas.append({

            "filename": file.filename,

            "file_type": (
                "pdf"
                if filename.endswith(".pdf")
                else "txt"
            ),

            "chunk": index

        })


    # -----------------------------------------------------
    # STORE IN CHROMADB
    # -----------------------------------------------------

    try:

        collection.upsert(

            documents=chunks,

            ids=ids,

            metadatas=metadatas

        )

    except Exception as e:

        print(
            "CHROMADB UPLOAD ERROR:",
            e
        )

        return {
            "success": False,
            "message": f"Could not store document: {e}"
        }


    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    print()
    print("================================")
    print("DOCUMENT UPLOADED SUCCESSFULLY")
    print("================================")

    print("Filename:", file.filename)

    print(
        "Chunks added:",
        len(chunks)
    )

    print(
        "Total RAG chunks:",
        collection.count()
    )


    return {

        "success": True,

        "message": "Document uploaded successfully.",

        "filename": file.filename,

        "chunks_added": len(chunks),

        "total_rag_chunks": collection.count()

    }


# =========================================================
# CHAT ROUTE
# =========================================================

@app.post("/chat")
def chat(
    request: ChatRequest
):

    global conversation_history


    print()
    print("================================")
    print("NEW USER MESSAGE")
    print("================================")

    print(
        request.message
    )


    # -----------------------------------------------------
    # 1. ADD USER MESSAGE TO MEMORY
    # -----------------------------------------------------

    conversation_history.append({

        "role": "user",

        "content": request.message

    })


    # -----------------------------------------------------
    # 2. SEARCH RAG
    # -----------------------------------------------------

    print()
    print("================================")
    print("SEARCHING RAG...")
    print("================================")

    rag_context = search_rag(
        request.message
    )


    # -----------------------------------------------------
    # 3. CREATE OLLAMA MESSAGES
    # -----------------------------------------------------

    messages_for_ollama = [

        SYSTEM_PROMPT

    ]


    # -----------------------------------------------------
    # ADD RAG CONTEXT
    # -----------------------------------------------------

    if rag_context:

        messages_for_ollama.append({

            "role": "system",

            "content": f"""
Relevant information from the local knowledge base:

{rag_context}

Use this information when it is relevant to
the user's question.

Do not claim that this information came from
the internet.

If the retrieved information does not answer
the question, use your general knowledge.
"""

        })


    # -----------------------------------------------------
    # ADD CONVERSATION MEMORY
    # -----------------------------------------------------

    messages_for_ollama.extend(
        conversation_history[1:]
    )


    # -----------------------------------------------------
    # SHOW DATA SENT TO OLLAMA
    # -----------------------------------------------------

    print()
    print("================================")
    print("HISTORY + RAG SENT TO OLLAMA")
    print("================================")

    print(
        messages_for_ollama
    )


    # -----------------------------------------------------
    # 4. SEND TO OLLAMA
    # -----------------------------------------------------

    try:

        response = requests.post(

            "http://localhost:11434/api/chat",

            json={

                "model": "llama3.2:3b",

                "messages":
                messages_for_ollama,

                "stream": False

            },

            timeout=120

        )

        response.raise_for_status()

        data = response.json()

        ai_response = data[
            "message"
        ][
            "content"
        ]


    except Exception as e:

        print()
        print("================================")
        print("OLLAMA ERROR")
        print("================================")

        print(e)

        return {

            "reply":
            "Sorry, I could not connect to the local AI model."

        }


    # -----------------------------------------------------
    # 5. ADD AI RESPONSE TO MEMORY
    # -----------------------------------------------------

    conversation_history.append({

        "role": "assistant",

        "content": ai_response

    })


    # -----------------------------------------------------
    # 6. SAVE MEMORY
    # -----------------------------------------------------

    conversation_history = save_history(
        conversation_history
    )


    # -----------------------------------------------------
    # SHOW SAVED MEMORY
    # -----------------------------------------------------

    print()
    print("================================")
    print("HISTORY AFTER SAVE")
    print("================================")

    print(
        conversation_history
    )


    # -----------------------------------------------------
    # 7. RETURN RESPONSE
    # -----------------------------------------------------

    return {

        "reply": ai_response

    }


# =========================================================
# RESET MEMORY
# =========================================================

@app.post("/reset")
def reset():

    global conversation_history


    conversation_history = [
        SYSTEM_PROMPT
    ]


    conversation_history = save_history(
        conversation_history
    )


    return {

        "message": "Conversation reset."

    }