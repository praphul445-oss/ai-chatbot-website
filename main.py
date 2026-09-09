from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import json
import os
import time
from io import BytesIO

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader

from google import genai
from google.genai import types


# ==========================================
# FASTAPI APP
# ==========================================

app = FastAPI(
    title="My AI Chatbot API",
    description="AI Chatbot with Gemini, Memory, RAG and PDF Upload",
    version="1.0"
)


# ==========================================
# CORS
# ==========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# CHAT REQUEST
# ==========================================

class ChatRequest(BaseModel):
    message: str


# ==========================================
# GEMINI CONFIGURATION
# ==========================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    print("=== GEMINI CONNECTED ===")
    print("Gemini model:", GEMINI_MODEL)

else:
    gemini_client = None

    print("=== WARNING: GEMINI_API_KEY NOT SET ===")


# ==========================================
# MEMORY
# ==========================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

MEMORY_FILE = os.path.join(
    BASE_DIR,
    "conversation_history.json"
)

MAX_MEMORY_MESSAGES = 10


SYSTEM_PROMPT = """
You are a helpful AI chatbot.

You must remember and use information the user tells you during
this conversation.

If the user tells you their name, remember it and answer correctly
when they later ask for their name.

Do not say that you cannot remember previous messages if those
messages are included in the conversation.

You also have access to a local RAG knowledge base.

When relevant information from the RAG knowledge base is provided,
use it to answer the user's question.

If the knowledge base does not contain relevant information,
answer normally using your general knowledge.

Be helpful, clear and accurate.
"""


def load_history():

    if os.path.exists(MEMORY_FILE):

        try:

            with open(
                MEMORY_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                history = json.load(f)

            if not history:
                return []

            return history[-MAX_MEMORY_MESSAGES:]

        except Exception as e:

            print("MEMORY LOAD ERROR:", e)

            return []

    return []


def save_history(history):

    trimmed_history = history[
        -MAX_MEMORY_MESSAGES:
    ]

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            trimmed_history,
            f,
            indent=2,
            ensure_ascii=False
        )

    return trimmed_history


conversation_history = load_history()

print("=== STARTUP MEMORY ===")
print(conversation_history)


# ==========================================
# RAG CONFIGURATION
# ==========================================

RAG_DATABASE_DIR = os.path.join(
    BASE_DIR,
    "rag",
    "chroma_db"
)

DOCUMENTS_DIR = os.path.join(
    BASE_DIR,
    "rag",
    "documents"
)

os.makedirs(
    DOCUMENTS_DIR,
    exist_ok=True
)


print("=== STARTING RAG ===")
print("RAG database:", RAG_DATABASE_DIR)


try:

    chroma_client = chromadb.PersistentClient(
        path=RAG_DATABASE_DIR
    )

    embedding_function = (
        embedding_functions
        .SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    )

    collection = chroma_client.get_or_create_collection(
        name="knowledge",
        embedding_function=embedding_function
    )

    print("=== RAG DATABASE CONNECTED ===")
    print(
        "Total RAG chunks:",
        collection.count()
    )


except Exception as e:

    print("RAG ERROR:", e)

    chroma_client = None
    collection = None


# ==========================================
# RAG SEARCH
# ==========================================

def search_rag(query):

    if collection is None:

        print("RAG collection unavailable.")

        return ""


    try:

        if collection.count() == 0:

            print("RAG database is empty.")

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


        print("=== RAG SEARCH RESULTS ===")


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


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():

    return {

        "message":
            "AI Chatbot backend is running!",

        "ai":
            "Google Gemini",

        "model":
            GEMINI_MODEL,

        "rag":
            collection is not None,

        "memory":
            True
    }


# ==========================================
# CHAT
# ==========================================

@app.post("/chat")
def chat(request: ChatRequest):

    global conversation_history


    # --------------------------------------
    # CHECK GEMINI
    # --------------------------------------

    if gemini_client is None:

        return {
            "reply":
                "Gemini API key is not configured on the server."
        }


    user_message = request.message


    # --------------------------------------
    # RAG SEARCH
    # --------------------------------------

    print()
    print("================================")
    print("SEARCHING RAG...")
    print("================================")


    rag_context = search_rag(
        user_message
    )


    # --------------------------------------
    # ADD USER MESSAGE TO MEMORY
    # --------------------------------------

    conversation_history.append({

        "role": "user",

        "content": user_message
    })


    # --------------------------------------
    # BUILD GEMINI CONTENTS
    # --------------------------------------

    contents = []


    for message in conversation_history:

        if message["role"] == "user":

            contents.append(

                types.Content(

                    role="user",

                    parts=[
                        types.Part(
                            text=message["content"]
                        )
                    ]
                )
            )


        elif message["role"] == "assistant":

            contents.append(

                types.Content(

                    role="model",

                    parts=[
                        types.Part(
                            text=message["content"]
                        )
                    ]
                )
            )


    # --------------------------------------
    # ADD RAG CONTEXT
    # --------------------------------------

    if rag_context:

        rag_instruction = f"""
Relevant information from the local knowledge base:

---------------- RAG CONTEXT ----------------

{rag_context}

-------------- END RAG CONTEXT --------------

Use this information when it is relevant to the user's question.

Do not claim that this information came from the internet.
"""


        contents[-1].parts[0].text = (

            contents[-1].parts[0].text

            + rag_instruction
        )


    # --------------------------------------
    # SEND REQUEST TO GEMINI
    # WITH AUTOMATIC RETRIES
    # --------------------------------------

    print()
    print("================================")
    print("SENDING REQUEST TO GEMINI")
    print("================================")


    try:

        response = None


        # Try Gemini up to 3 times
        for attempt in range(3):

            try:

                print(
                    f"GEMINI ATTEMPT {attempt + 1}/3"
                )


                response = (
                    gemini_client
                    .models
                    .generate_content(

                        model=GEMINI_MODEL,

                        contents=contents,

                        config=(
                            types
                            .GenerateContentConfig(

                                system_instruction=
                                    SYSTEM_PROMPT,

                                max_output_tokens=1000
                            )
                        )
                    )
                )


                # Request succeeded
                print(
                    "GEMINI REQUEST SUCCESSFUL"
                )

                break


            except Exception as e:

                print(
                    f"GEMINI ATTEMPT {attempt + 1} FAILED:",
                    e
                )


                # If this wasn't the final attempt,
                # wait and try again.

                if attempt < 2:

                    wait_time = 2 ** attempt

                    print(
                        f"Retrying Gemini in {wait_time} seconds..."
                    )

                    time.sleep(
                        wait_time
                    )

                else:

                    # All attempts failed
                    raise


        # ----------------------------------
        # GET GEMINI RESPONSE
        # ----------------------------------

        ai_response = response.text


    except Exception as e:

        print(
            "GEMINI ERROR:",
            e
        )


        # Remove the user message because
        # Gemini did not successfully answer.

        if conversation_history:

            conversation_history.pop()


        return {

            "reply":
                "Sorry, I could not connect to the Gemini AI service. Please try again."
        }


    # --------------------------------------
    # SAVE AI RESPONSE TO MEMORY
    # --------------------------------------

    conversation_history.append({

        "role": "assistant",

        "content": ai_response
    })


    conversation_history = save_history(
        conversation_history
    )


    # --------------------------------------
    # PRINT RESPONSE
    # --------------------------------------

    print()
    print("================================")
    print("GEMINI RESPONSE")
    print("================================")

    print(ai_response)


    # --------------------------------------
    # RETURN TO WEBSITE
    # --------------------------------------

    return {

        "reply": ai_response

    }


# ==========================================
# RESET MEMORY
# ==========================================

@app.post("/reset")
def reset():

    global conversation_history


    conversation_history = []


    save_history(
        conversation_history
    )


    return {

        "message":
            "Conversation reset."
    }


# ==========================================
# PDF UPLOAD / RAG
# ==========================================

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...)
):

    # --------------------------------------
    # CHECK FILE TYPE
    # --------------------------------------

    if not file.filename.lower().endswith(".pdf"):

        return {

            "success": False,

            "message":
                "Only PDF files are supported."
        }


    # --------------------------------------
    # CHECK RAG
    # --------------------------------------

    if collection is None:

        return {

            "success": False,

            "message":
                "RAG database is not available."
        }


    try:

        # ----------------------------------
        # READ PDF
        # ----------------------------------

        file_bytes = await file.read()


        # ----------------------------------
        # SAVE PDF
        # ----------------------------------

        pdf_path = os.path.join(

            DOCUMENTS_DIR,

            file.filename
        )


        with open(
            pdf_path,
            "wb"
        ) as f:

            f.write(file_bytes)


        # ----------------------------------
        # EXTRACT TEXT
        # ----------------------------------

        pdf_reader = PdfReader(
            BytesIO(file_bytes)
        )


        full_text = ""


        for page in pdf_reader.pages:

            text = page.extract_text()


            if text:

                full_text += (
                    text
                    + "\n"
                )


        # ----------------------------------
        # CHECK TEXT
        # ----------------------------------

        if not full_text.strip():

            return {

                "success": False,

                "message":
                    "Could not extract text from PDF."
            }


        # ----------------------------------
        # SPLIT INTO CHUNKS
        # ----------------------------------

        chunk_size = 1000

        chunks = []


        for i in range(
            0,
            len(full_text),
            chunk_size
        ):

            chunk = full_text[
                i:i + chunk_size
            ].strip()


            if chunk:

                chunks.append(
                    chunk
                )


        # ----------------------------------
        # CREATE UNIQUE IDS
        # ----------------------------------

        start_id = collection.count()


        ids = [

            f"{file.filename}_{start_id + i}"

            for i in range(
                len(chunks)
            )
        ]


        # ----------------------------------
        # METADATA
        # ----------------------------------

        metadatas = [

            {
                "source":
                    file.filename
            }

            for _ in chunks
        ]


        # ----------------------------------
        # ADD TO CHROMADB
        # ----------------------------------

        collection.add(

            documents=chunks,

            ids=ids,

            metadatas=metadatas
        )


        total_chunks = collection.count()


        # ----------------------------------
        # PRINT UPLOAD INFO
        # ----------------------------------

        print()
        print("================================")
        print("PDF UPLOADED")
        print("================================")

        print(
            "Filename:",
            file.filename
        )

        print(
            "Chunks added:",
            len(chunks)
        )

        print(
            "Total chunks:",
            total_chunks
        )


        # ----------------------------------
        # RETURN SUCCESS
        # ----------------------------------

        return {

            "success": True,

            "message":
                "Document uploaded successfully",

            "filename":
                file.filename,

            "chunks_added":
                len(chunks),

            "total_chunks":
                total_chunks
        }


    except Exception as e:

        print(
            "PDF UPLOAD ERROR:",
            e
        )


        return {

            "success": False,

            "message":
                str(e)
        }