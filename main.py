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

from openai import OpenAI


# =========================================
# FASTAPI APP
# =========================================

app = FastAPI(
    title="My AI Chatbot API",
    description="AI Chatbot with OpenAI, Memory, RAG and PDF Upload",
    version="2.0"
)


# =========================================
# CORS
# =========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================
# CHAT REQUEST
# =========================================

class ChatRequest(BaseModel):
    message: str


# =========================================
# OPENAI CONFIGURATION
# =========================================

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


# =========================================
# PROJECT PATHS
# =========================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

MEMORY_FILE = os.path.join(
    BASE_DIR,
    "conversation_history.json"
)

MAX_MEMORY_MESSAGES = 10


# =========================================
# SYSTEM PROMPT
# =========================================

SYSTEM_PROMPT = """
You are a helpful AI chatbot.

You must remember and use information the user tells you
during this conversation.

If the user tells you their name, remember it and answer
correctly when they later ask for their name.

Do not say that you cannot remember previous messages if
those messages are included in the conversation.

You also have access to a local RAG knowledge base.

When relevant information from the RAG knowledge base is
provided, use it to answer the user's question.

If the knowledge base does not contain relevant information,
answer normally using your general knowledge.

Be helpful, clear and accurate.
"""


# =========================================
# MEMORY
# =========================================

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


# =========================================
# RAG CONFIGURATION
# =========================================

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


# =========================================
# RAG SEARCH
# =========================================

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

            print(
                "--------------------------------"
            )

            print(document)


        return "\n\n".join(documents)


    except Exception as e:

        print(
            "RAG SEARCH ERROR:",
            e
        )

        return ""


# =========================================
# HOME
# =========================================

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
            collection is not None,

        "memory":
            True
    }


# =========================================
# CHAT
# =========================================

@app.post("/chat")
def chat(request: ChatRequest):

    global conversation_history


    if openai_client is None:

        return {

            "reply":
                "OpenAI API key is not configured on the server."
        }


    user_message = request.message


    # =====================================
    # SEARCH RAG
    # =====================================

    print()
    print("================================")
    print("SEARCHING RAG...")
    print("================================")


    rag_context = search_rag(
        user_message
    )


    # =====================================
    # SAVE USER MESSAGE
    # =====================================

    conversation_history.append({

        "role":
            "user",

        "content":
            user_message
    })


    # =====================================
    # BUILD OPENAI INPUT
    # =====================================

    messages = []


    for message in conversation_history:

        messages.append({

            "role":
                message["role"],

            "content":
                message["content"]
        })


    # =====================================
    # ADD RAG CONTEXT
    # =====================================

    if rag_context:

        rag_instruction = f"""

Relevant information from the local knowledge base:

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


    # =====================================
    # SEND TO OPENAI
    # =====================================

    print()
    print("================================")
    print("SENDING REQUEST TO OPENAI")
    print("================================")


    try:

        response = None


        for attempt in range(3):

            try:

                print(
                    f"OPENAI ATTEMPT {attempt + 1}/3"
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


    # =====================================
    # SAVE AI RESPONSE
    # =====================================

    conversation_history.append({

        "role":
            "assistant",

        "content":
            ai_response
    })


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


# =========================================
# RESET MEMORY
# =========================================

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


# =========================================
# PDF UPLOAD
# =========================================

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...)
):

    if not file.filename.lower().endswith(
        ".pdf"
    ):

        return {

            "success":
                False,

            "message":
                "Only PDF files are supported."
        }


    if collection is None:

        return {

            "success":
                False,

            "message":
                "RAG database is not available."
        }


    try:

        # =================================
        # READ PDF
        # =================================

        file_bytes = await file.read()


        # =================================
        # SAVE PDF
        # =================================

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


        # =================================
        # EXTRACT TEXT
        # =================================

        pdf_reader = PdfReader(
            BytesIO(file_bytes)
        )


        full_text = ""


        for page in pdf_reader.pages:

            text = page.extract_text()


            if text:

                full_text += (
                    text + "\n"
                )


        if not full_text.strip():

            return {

                "success":
                    False,

                "message":
                    "Could not extract text from PDF."
            }


        # =================================
        # CREATE CHUNKS
        # =================================

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


        # =================================
        # ADD TO CHROMADB
        # =================================

        start_id = collection.count()


        ids = [

            f"{file.filename}_{start_id + i}"

            for i in range(
                len(chunks)
            )
        ]


        metadatas = [

            {
                "source":
                    file.filename
            }

            for _ in chunks
        ]


        collection.add(

            documents=chunks,

            ids=ids,

            metadatas=metadatas
        )


        total_chunks = collection.count()


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
                total_chunks
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