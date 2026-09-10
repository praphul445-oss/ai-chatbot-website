from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import json
import os
import re
import math
import time
from io import BytesIO

from pypdf import PdfReader
from openai import OpenAI


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="My AI Chatbot API",
    description="AI Chatbot with OpenAI, Memory and Local RAG",
    version="4.0"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# REQUEST MODEL
# =========================================================

class ChatRequest(BaseModel):
    message: str


# =========================================================
# OPENAI
# =========================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6-luna"
)


if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    print("=== OPENAI CONNECTED ===")
    print("OpenAI model:", OPENAI_MODEL)

else:
    openai_client = None

    print("=== WARNING: OPENAI_API_KEY NOT SET ===")


# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# =========================================================
# MEMORY
# =========================================================

MEMORY_FILE = os.path.join(
    BASE_DIR,
    "conversation_history.json"
)

MAX_MEMORY_MESSAGES = 10


SYSTEM_PROMPT = """
You are a helpful AI chatbot.

You must remember and use information the user tells you
during this conversation.

If the user tells you their name, remember it and answer
correctly when they later ask for their name.

You also have access to a local RAG knowledge base.

When relevant information from the RAG knowledge base is
provided, use it to answer the user's question.

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

            return history[-MAX_MEMORY_MESSAGES:]

        except Exception as e:

            print("MEMORY LOAD ERROR:", e)

            return []

    return []


def save_history(history):

    history = history[-MAX_MEMORY_MESSAGES:]

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            history,
            f,
            indent=2,
            ensure_ascii=False
        )

    return history


conversation_history = load_history()


print("=== STARTUP MEMORY ===")
print(conversation_history)


# =========================================================
# LOCAL RAG DATABASE
# =========================================================

DOCUMENTS_DIR = os.path.join(
    BASE_DIR,
    "rag",
    "documents"
)

RAG_FILE = os.path.join(
    BASE_DIR,
    "rag",
    "local_rag.json"
)


os.makedirs(
    DOCUMENTS_DIR,
    exist_ok=True
)

os.makedirs(
    os.path.dirname(RAG_FILE),
    exist_ok=True
)


def load_rag():

    if not os.path.exists(RAG_FILE):

        return []

    try:

        with open(
            RAG_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return data

    except Exception as e:

        print("RAG LOAD ERROR:", e)

        return []


def save_rag(data):

    with open(
        RAG_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


rag_documents = load_rag()


print("=== LOCAL RAG STARTED ===")
print("RAG chunks:", len(rag_documents))


# =========================================================
# TEXT PROCESSING
# =========================================================

def tokenize(text):

    words = re.findall(
        r"[a-zA-Z0-9]+",
        text.lower()
    )

    stop_words = {
        "the",
        "is",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "what",
        "are",
        "how",
        "this",
        "that",
        "from",
        "by",
        "based",
        "as",
        "be",
        "it"
    }

    return [
        word
        for word in words
        if word not in stop_words
    ]


# =========================================================
# LOCAL RAG SEARCH
# =========================================================

def search_rag(query):

    if not rag_documents:

        print("RAG database is empty.")

        return ""


    query_words = tokenize(query)

    if not query_words:

        return ""


    # -----------------------------------------------------
    # Document frequency
    # -----------------------------------------------------

    document_frequency = {}

    for document in rag_documents:

        words = set(
            tokenize(
                document["text"]
            )
        )

        for word in words:

            document_frequency[word] = (
                document_frequency.get(word, 0) + 1
            )


    total_documents = len(
        rag_documents
    )


    # -----------------------------------------------------
    # Score documents
    # -----------------------------------------------------

    scored_documents = []


    for document in rag_documents:

        words = tokenize(
            document["text"]
        )

        if not words:
            continue


        word_counts = {}

        for word in words:

            word_counts[word] = (
                word_counts.get(word, 0) + 1
            )


        score = 0.0


        for query_word in query_words:

            if query_word not in word_counts:

                continue


            term_frequency = (
                word_counts[query_word]
                / len(words)
            )


            df = document_frequency.get(
                query_word,
                0
            )


            idf = math.log(
                (total_documents + 1)
                / (df + 1)
            ) + 1


            score += (
                term_frequency * idf
            )


        if score > 0:

            scored_documents.append(
                (
                    score,
                    document
                )
            )


    # -----------------------------------------------------
    # Sort by relevance
    # -----------------------------------------------------

    scored_documents.sort(
        key=lambda x: x[0],
        reverse=True
    )


    # -----------------------------------------------------
    # Return top 3 chunks
    # -----------------------------------------------------

    top_documents = [
        item[1]
        for item in scored_documents[:3]
    ]


    if not top_documents:

        print(
            "RAG: No relevant information found."
        )

        return ""


    print()
    print("=== LOCAL RAG SEARCH RESULTS ===")


    result_text = []


    for document in top_documents:

        print("--------------------------------")
        print(
            "Source:",
            document["source"]
        )
        print(
            document["text"]
        )


        result_text.append(
            document["text"]
        )


    return "\n\n".join(
        result_text
    )


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    return {
        "message":
            "AI Chatbot backend is running!",

        "ai":
            "OpenAI",

        "model":
            OPENAI_MODEL,

        "rag":
            True,

        "rag_type":
            "Local TF-IDF-style retrieval",

        "rag_chunks":
            len(rag_documents),

        "memory":
            True
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(request: ChatRequest):

    global conversation_history


    if openai_client is None:

        return {
            "reply":
                "OpenAI API key is not configured."
        }


    user_message = request.message


    # -----------------------------------------------------
    # SEARCH LOCAL RAG
    # -----------------------------------------------------

    print()
    print("================================")
    print("SEARCHING LOCAL RAG")
    print("================================")


    rag_context = search_rag(
        user_message
    )


    # -----------------------------------------------------
    # SAVE USER MESSAGE
    # -----------------------------------------------------

    conversation_history.append(
        {
            "role": "user",
            "content": user_message
        }
    )


    conversation_history = (
        conversation_history[
            -MAX_MEMORY_MESSAGES:
        ]
    )


    # -----------------------------------------------------
    # BUILD MESSAGES
    # -----------------------------------------------------

    messages = []


    for message in conversation_history:

        messages.append(
            {
                "role":
                    message["role"],

                "content":
                    message["content"]
            }
        )


    # -----------------------------------------------------
    # ADD RAG CONTEXT
    # -----------------------------------------------------

    if rag_context:

        rag_instruction = f"""

Relevant information from the local
knowledge base:

---------------- RAG CONTEXT ----------------

{rag_context}

-------------- END RAG CONTEXT --------------

Use this information when it is relevant
to the user's question.

Do not claim that this information came
from the internet.
"""


        messages[-1]["content"] = (
            messages[-1]["content"]
            + rag_instruction
        )


    # -----------------------------------------------------
    # OPENAI
    # -----------------------------------------------------

    print()
    print("================================")
    print("SENDING REQUEST TO OPENAI")
    print("================================")


    try:

        response = None


        for attempt in range(3):

            try:

                print(
                    f"OPENAI ATTEMPT "
                    f"{attempt + 1}/3"
                )


                response = (
                    openai_client
                    .responses
                    .create(
                        model=OPENAI_MODEL,
                        instructions=SYSTEM_PROMPT,
                        input=messages,
                        max_output_tokens=1000
                    )
                )


                print(
                    "OPENAI REQUEST SUCCESSFUL"
                )


                break


            except Exception as e:

                print(
                    f"OPENAI ATTEMPT "
                    f"{attempt + 1} FAILED:",
                    e
                )


                if attempt < 2:

                    wait_time = 2 ** attempt

                    print(
                        f"Retrying OpenAI "
                        f"in {wait_time} seconds..."
                    )

                    time.sleep(
                        wait_time
                    )

                else:

                    raise


        ai_response = response.output_text


    except Exception as e:

        print(
            "OPENAI ERROR:",
            e
        )


        if conversation_history:

            conversation_history.pop()


        return {
            "reply":
                "Sorry, I could not connect to the OpenAI AI service. Please try again."
        }


    # -----------------------------------------------------
    # SAVE AI RESPONSE
    # -----------------------------------------------------

    conversation_history.append(
        {
            "role":
                "assistant",

            "content":
                ai_response
        }
    )


    conversation_history = save_history(
        conversation_history
    )


    print()
    print("================================")
    print("OPENAI RESPONSE")
    print("================================")

    print(ai_response)


    return {
        "reply":
            ai_response
    }


# =========================================================
# RESET MEMORY
# =========================================================

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


# =========================================================
# PDF UPLOAD
# =========================================================

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...)
):


    global rag_documents


    # -----------------------------------------------------
    # Check PDF
    # -----------------------------------------------------

    if not file.filename.lower().endswith(".pdf"):

        return {
            "success":
                False,

            "message":
                "Only PDF files are supported."
        }


    try:

        print()
        print("================================")
        print("PDF UPLOAD STARTED")
        print("================================")


        file_bytes = await file.read()


        # -------------------------------------------------
        # Save original PDF
        # -------------------------------------------------

        pdf_path = os.path.join(
            DOCUMENTS_DIR,
            file.filename
        )


        with open(
            pdf_path,
            "wb"
        ) as f:

            f.write(
                file_bytes
            )


        # -------------------------------------------------
        # Extract text
        # -------------------------------------------------

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


        if not full_text.strip():

            return {
                "success":
                    False,

                "message":
                    "Could not extract text from PDF."
            }


        # -------------------------------------------------
        # Create chunks
        # -------------------------------------------------

        chunk_size = 1000


        chunks = []


        for i in range(
            0,
            len(full_text),
            chunk_size
        ):

            chunk = (
                full_text[
                    i:i + chunk_size
                ]
                .strip()
            )


            if chunk:

                chunks.append(
                    chunk
                )


        if not chunks:

            return {
                "success":
                    False,

                "message":
                    "No usable text chunks found."
            }


        # -------------------------------------------------
        # Add chunks to local RAG
        # -------------------------------------------------

        for chunk in chunks:

            rag_documents.append(
                {
                    "source":
                        file.filename,

                    "text":
                        chunk
                }
            )


        # -------------------------------------------------
        # Save local RAG
        # -------------------------------------------------

        save_rag(
            rag_documents
        )


        print()
        print("================================")
        print("PDF UPLOADED SUCCESSFULLY")
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
            "Total RAG chunks:",
            len(rag_documents)
        )


        return {

            "success":
                True,

            "message":
                "Document uploaded successfully",

            "filename":
                file.filename,

            "chunks_added":
                len(chunks),

            "total_chunks":
                len(rag_documents)
        }


    except Exception as e:

        print(
            "PDF UPLOAD ERROR:",
            e
        )


        return {

            "success":
                False,

            "message":
                str(e)
        }