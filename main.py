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
    description="AI Chatbot with OpenAI, Memory and Improved Local RAG",
    version="5.0"
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

    openai_client = OpenAI(
        api_key=OPENAI_API_KEY
    )

    print("=== OPENAI CONNECTED ===")
    print("OpenAI model:", OPENAI_MODEL)

else:

    openai_client = None

    print("=== WARNING: OPENAI_API_KEY NOT SET ===")


# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


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

IMPORTANT RAG RULES:

1. When relevant RAG information is provided, use it
   to answer the user's question.

2. Prefer the information from the uploaded documents
   when the question is specifically about those documents.

3. Do not invent information that is not supported by
   the provided RAG context.

4. If the RAG context does not contain the answer,
   you may use your general knowledge.

5. Do not say that the RAG information came from the internet.

6. Keep answers clear and useful.

7. Do not mention internal retrieval scores or technical
   implementation details unless the user asks.
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

            print(
                "MEMORY LOAD ERROR:",
                e
            )

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

        if not isinstance(data, list):

            return []

        return data

    except Exception as e:

        print(
            "RAG LOAD ERROR:",
            e
        )

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
print(
    "RAG chunks:",
    len(rag_documents)
)


# =========================================================
# RAG SETTINGS
# =========================================================

CHUNK_SIZE = 900

CHUNK_OVERLAP = 150

RAG_TOP_K = 5


# =========================================================
# TEXT PROCESSING
# =========================================================

STOP_WORDS = {
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
    "it",
    "was",
    "were",
    "about",
    "according",
    "into",
    "can",
    "does",
    "do",
    "which",
    "their",
    "they",
    "them",
    "these",
    "those"
}


def tokenize(text):

    words = re.findall(
        r"[a-zA-Z0-9]+",
        text.lower()
    )

    return [
        word
        for word in words
        if word not in STOP_WORDS
    ]


# =========================================================
# CREATE CHUNKS
# =========================================================

def create_chunks(text, page_number):

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    if not text:

        return []


    chunks = []

    start = 0

    text_length = len(text)


    while start < text_length:

        end = min(
            start + CHUNK_SIZE,
            text_length
        )


        chunk = text[
            start:end
        ].strip()


        if chunk:

            chunks.append(
                {
                    "page": page_number,
                    "text": chunk
                }
            )


        if end >= text_length:

            break


        next_start = (
            end - CHUNK_OVERLAP
        )


        if next_start <= start:

            next_start = end


        start = next_start


    return chunks


# =========================================================
# CHECK IF DOCUMENT ALREADY EXISTS
# =========================================================

def document_exists(filename):

    for document in rag_documents:

        if document.get("source") == filename:

            return True

    return False


# =========================================================
# LOCAL RAG SEARCH
# =========================================================

def search_rag(query):

    if not rag_documents:

        print(
            "RAG database is empty."
        )

        return {
            "context": "",
            "sources": []
        }


    query_words = tokenize(
        query
    )


    if not query_words:

        return {
            "context": "",
            "sources": []
        }


    # -----------------------------------------------------
    # Query phrase
    # -----------------------------------------------------

    normalized_query = re.sub(
        r"\s+",
        " ",
        query.lower()
    ).strip()


    # -----------------------------------------------------
    # Document frequency
    # -----------------------------------------------------

    document_frequency = {}


    for document in rag_documents:

        words = set(
            tokenize(
                document.get(
                    "text",
                    ""
                )
            )
        )


        for word in words:

            document_frequency[word] = (
                document_frequency.get(
                    word,
                    0
                )
                + 1
            )


    total_documents = len(
        rag_documents
    )


    # -----------------------------------------------------
    # Score documents
    # -----------------------------------------------------

    scored_documents = []


    for document in rag_documents:

        text = document.get(
            "text",
            ""
        )


        if not text:

            continue


        words = tokenize(
            text
        )


        if not words:

            continue


        word_counts = {}


        for word in words:

            word_counts[word] = (
                word_counts.get(
                    word,
                    0
                )
                + 1
            )


        score = 0.0


        # -------------------------------------------------
        # TF-IDF style scoring
        # -------------------------------------------------

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
                term_frequency
                * idf
            )


        # -------------------------------------------------
        # Exact phrase bonus
        # -------------------------------------------------

        if (
            len(normalized_query) >= 8
            and normalized_query in text.lower()
        ):

            score += 2.0


        # -------------------------------------------------
        # Query word coverage bonus
        # -------------------------------------------------

        matched_words = 0


        for query_word in set(
            query_words
        ):

            if query_word in word_counts:

                matched_words += 1


        if query_words:

            coverage = (
                matched_words
                / len(
                    set(query_words)
                )
            )

            score += (
                coverage * 0.5
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
    # Top results
    # -----------------------------------------------------

    top_documents = [
        item
        for item in scored_documents[
            :RAG_TOP_K
        ]
    ]


    if not top_documents:

        print(
            "RAG: No relevant information found."
        )

        return {
            "context": "",
            "sources": []
        }


    # -----------------------------------------------------
    # Build context
    # -----------------------------------------------------

    print()
    print(
        "=== LOCAL RAG SEARCH RESULTS ==="
    )


    context_parts = []

    sources = []


    for rank, item in enumerate(
        top_documents,
        start=1
    ):

        score = item[0]

        document = item[1]


        source = document.get(
            "source",
            "Unknown document"
        )


        page = document.get(
            "page",
            "Unknown"
        )


        text = document.get(
            "text",
            ""
        )


        print(
            "--------------------------------"
        )


        print(
            f"Result {rank}"
        )


        print(
            "Source:",
            source
        )


        print(
            "Page:",
            page
        )


        print(
            "Score:",
            round(
                score,
                4
            )
        )


        print(
            text
        )


        context_parts.append(
            f"""
[Source: {source} | Page: {page}]

{text}
"""
        )


        source_entry = {
            "source": source,
            "page": page
        }


        if source_entry not in sources:

            sources.append(
                source_entry
            )


    context = "\n\n".join(
        context_parts
    )


    return {
        "context": context,
        "sources": sources
    }


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
            "Improved local TF-IDF-style retrieval",

        "rag_chunks":
            len(rag_documents),

        "rag_top_k":
            RAG_TOP_K,

        "chunk_size":
            CHUNK_SIZE,

        "chunk_overlap":
            CHUNK_OVERLAP,

        "memory":
            True
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(
    request: ChatRequest
):

    global conversation_history


    if openai_client is None:

        return {
            "reply":
                "OpenAI API key is not configured."
        }


    user_message = request.message


    # -----------------------------------------------------
    # SEARCH RAG
    # -----------------------------------------------------

    print()
    print(
        "================================"
    )
    print(
        "SEARCHING LOCAL RAG"
    )
    print(
        "================================"
    )


    rag_result = search_rag(
        user_message
    )


    rag_context = rag_result[
        "context"
    ]


    rag_sources = rag_result[
        "sources"
    ]


    # -----------------------------------------------------
    # SAVE USER MESSAGE
    # -----------------------------------------------------

    conversation_history.append(
        {
            "role":
                "user",

            "content":
                user_message
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

================ RAG CONTEXT ================

{rag_context}

============== END RAG CONTEXT ==============

Use the RAG context when it is relevant
to the user's question.

If the user asks specifically about the
uploaded document, prioritize the document
information.

Do not claim that the information came
from the internet.

Do not mention retrieval scores.
"""


        messages[-1]["content"] = (
            messages[-1]["content"]
            + rag_instruction
        )


    # -----------------------------------------------------
    # OPENAI
    # -----------------------------------------------------

    print()
    print(
        "================================"
    )
    print(
        "SENDING REQUEST TO OPENAI"
    )
    print(
        "================================"
    )


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


        ai_response = (
            response.output_text
        )


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
    # ADD SOURCES
    # -----------------------------------------------------

    if rag_sources:

        source_lines = []


        for source in rag_sources:

            source_name = source[
                "source"
            ]


            page = source[
                "page"
            ]


            source_lines.append(
                f"📄 {source_name} — Page {page}"
            )


        sources_text = (
            "\n\n📚 Sources used:\n"
            + "\n".join(
                source_lines
            )
        )


        ai_response = (
            ai_response
            + sources_text
        )


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


    conversation_history = (
        save_history(
            conversation_history
        )
    )


    # -----------------------------------------------------
    # LOG RESPONSE
    # -----------------------------------------------------

    print()
    print(
        "================================"
    )
    print(
        "OPENAI RESPONSE"
    )
    print(
        "================================"
    )


    print(
        ai_response
    )


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


# =====================================================