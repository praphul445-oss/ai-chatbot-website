"""
My AI Chatbot API  (v9.0)

- Groq LLM (OpenAI-compatible endpoint)
- Supabase login: user identity comes from the VERIFIED access token
- Per-user conversation memory
- Per-user local RAG (PDF upload + TF-IDF style search)

Environment variables (set these on Render and in a local .env / shell):
    GROQ_API_KEY        required
    GROQ_MODEL          optional (default llama-3.3-70b-versatile)
    SUPABASE_URL        required  e.g. https://xxxx.supabase.co
    SUPABASE_ANON_KEY   optional if SUPABASE_PUBLISHABLE_KEY is used
    SUPABASE_PUBLISHABLE_KEY optional alternative auth key
    ALLOWED_ORIGINS     optional  comma separated, e.g. https://mysite.com
                        (default "*" = allow all, fine for testing)
    DATA_DIR            optional  where user data is stored. Point this at a
                        Render persistent disk so data survives redeploys.
"""

import json
import math
import os
import re
import threading
import time
from io import BytesIO

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel
from pypdf import PdfReader


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="My AI Chatbot API",
    description="AI Chatbot with Groq, verified Supabase auth, per-user memory and per-user RAG",
    version="9.1",
)


# =========================================================
# CORS
# =========================================================

_origins_env = os.getenv("ALLOWED_ORIGINS", "*").strip()
ALLOWED_ORIGINS = (
    ["*"]
    if _origins_env == "*"
    else [o.strip() for o in _origins_env.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],  # includes the Authorization header
)


# =========================================================
# SETTINGS
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

def clean_env_value(value):
    """Trim whitespace and accidental surrounding quotes from Render env values."""
    if value is None:
        return ""
    value = str(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
        value = value[1:-1].strip()
    return value


SUPABASE_URL = clean_env_value(os.getenv("SUPABASE_URL")).rstrip("/")

# Render can use the legacy name SUPABASE_ANON_KEY or the newer
# SUPABASE_PUBLISHABLE_KEY. We accept either, without changing the frontend.
SUPABASE_ANON_KEY = clean_env_value(os.getenv("SUPABASE_ANON_KEY"))
SUPABASE_PUBLISHABLE_KEY = clean_env_value(os.getenv("SUPABASE_PUBLISHABLE_KEY"))
SUPABASE_KEY = SUPABASE_ANON_KEY or SUPABASE_PUBLISHABLE_KEY

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.getenv("DATA_DIR") or os.path.join(BASE_DIR, "data", "users")
os.makedirs(USERS_DIR, exist_ok=True)

MAX_MEMORY_MESSAGES = 10
MAX_MESSAGE_CHARS = 4000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
RAG_TOP_K = 5


# =========================================================
# GROQ CLIENT
# =========================================================

if GROQ_API_KEY:
    openai_client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
    print("=== GROQ CONNECTED ===")
    print("Groq model:", GROQ_MODEL)
else:
    openai_client = None
    print("=== WARNING: GROQ_API_KEY NOT SET ===")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("=== WARNING: SUPABASE_URL / SUPABASE auth key NOT SET (all requests will fail auth) ===")
else:
    key_source = "SUPABASE_ANON_KEY" if SUPABASE_ANON_KEY else "SUPABASE_PUBLISHABLE_KEY"
    print("Supabase URL:", SUPABASE_URL)
    print("Supabase auth key source:", key_source)


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are a helpful AI chatbot.

You must remember and use information the user tells you
during the conversation.

If the user tells you their name, remember it and answer
correctly when they later ask for their name.

You also have access to a local RAG knowledge base made of
the user's own uploaded documents.

IMPORTANT RAG RULES:

1. When relevant RAG information is provided, use it
   to answer the user's question.

2. Prefer information from uploaded documents when
   the question is specifically about those documents.

3. Do not invent information that is not supported by
   the provided RAG context.

4. If the RAG context does not contain the answer,
   you may use your general knowledge.

5. Do not say that RAG information came from the internet.

6. Keep answers clear and useful.

7. Do not mention internal retrieval scores or technical
   implementation details unless the user asks.

8. If the user asks a normal general question and the
   uploaded documents are not relevant, answer normally.
"""


# =========================================================
# REQUEST MODEL
# =========================================================

class ChatRequest(BaseModel):
    message: str


# =========================================================
# USER ID SAFETY
# =========================================================

def clean_user_id(user_id):
    """Allow only characters that are safe for folder names (UUIDs pass)."""
    if not user_id:
        return None

    user_id = str(user_id).strip()

    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", user_id):
        return None

    return user_id


# =========================================================
# AUTH: VERIFY THE SUPABASE TOKEN
# =========================================================

async def get_current_user(authorization: str = Header(None)):
    """
    Reads 'Authorization: Bearer <supabase access token>', asks Supabase
    to verify it, and returns the real user id. The client can no longer
    choose which user it pretends to be.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing login token.")

    token = authorization.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Missing login token.")

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Auth is not configured on the server.")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_KEY,
                },
            )
    except Exception as e:
        print("AUTH ERROR:", repr(e))
        raise HTTPException(status_code=503, detail="Could not verify login. Try again.")

    # Diagnostic logging for the current 401 problem. NEVER log the access
    # token or the Supabase key. The response body is truncated.
    print("SUPABASE AUTH STATUS:", r.status_code)
    if r.status_code != 200:
        print("SUPABASE AUTH BODY:", r.text[:500])
        raise HTTPException(status_code=401, detail="Invalid or expired login.")

    try:
        user_id = clean_user_id(r.json().get("id"))
    except Exception:
        user_id = None

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user.")

    return user_id


# =========================================================
# PER-USER LOCKS (prevents two requests corrupting one file)
# =========================================================

_locks = {}
_locks_guard = threading.Lock()


def user_lock(user_id):
    with _locks_guard:
        if user_id not in _locks:
            _locks[user_id] = threading.Lock()
        return _locks[user_id]


# =========================================================
# USER PATHS + SAFE JSON HELPERS
# =========================================================

def get_user_paths(user_id):
    safe_user_id = clean_user_id(user_id)

    if not safe_user_id:
        raise ValueError("Invalid user ID.")

    user_dir = os.path.join(USERS_DIR, safe_user_id)
    rag_dir = os.path.join(user_dir, "rag")
    documents_dir = os.path.join(rag_dir, "documents")

    os.makedirs(documents_dir, exist_ok=True)

    return {
        "user_dir": user_dir,
        "rag_dir": rag_dir,
        "documents_dir": documents_dir,
        "memory_file": os.path.join(user_dir, "conversation_history.json"),
        "rag_file": os.path.join(rag_dir, "local_rag.json"),
    }


def read_json_list(path):
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        print("JSON LOAD ERROR:", path, e)
        return []


def write_json_atomic(path, data):
    """Write to a temp file then swap it in, so a crash can't leave half a file."""
    tmp_path = path + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    os.replace(tmp_path, path)


# =========================================================
# MEMORY
# =========================================================

def load_history(user_id):
    paths = get_user_paths(user_id)
    return read_json_list(paths["memory_file"])[-MAX_MEMORY_MESSAGES:]


def save_history(user_id, history):
    paths = get_user_paths(user_id)
    history = history[-MAX_MEMORY_MESSAGES:]

    try:
        write_json_atomic(paths["memory_file"], history)
    except Exception as e:
        print("MEMORY SAVE ERROR:", e)

    return history


# =========================================================
# RAG LOAD / SAVE
# =========================================================

def load_rag(user_id):
    paths = get_user_paths(user_id)
    return read_json_list(paths["rag_file"])


def save_rag(user_id, data):
    paths = get_user_paths(user_id)
    write_json_atomic(paths["rag_file"], data)


# =========================================================
# TEXT PROCESSING
# =========================================================

STOP_WORDS = {
    "the", "is", "a", "an", "and", "or", "of", "to", "in", "on", "for",
    "with", "what", "are", "how", "this", "that", "from", "by", "based",
    "as", "be", "it", "was", "were", "about", "according", "into", "can",
    "does", "do", "which", "their", "they", "them", "these", "those",
}


def tokenize(text):
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def create_chunks(text, page_number):
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + CHUNK_SIZE, text_length)
        chunk = text[start:end].strip()

        if chunk:
            chunks.append({"page": page_number, "text": chunk})

        if end >= text_length:
            break

        next_start = end - CHUNK_OVERLAP

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


def document_exists(rag_documents, filename):
    return any(d.get("source") == filename for d in rag_documents)


def safe_filename(name):
    name = os.path.basename(name)
    name = re.sub(r"[^\w.\- ]", "_", name).strip()
    return name[:150]


# =========================================================
# RAG SEARCH (only ever searches ONE user's chunks)
# =========================================================

def search_rag(user_id, query):
    rag_documents = load_rag(user_id)

    empty = {"context": "", "sources": []}

    if not rag_documents:
        return empty

    query_words = tokenize(query)

    if not query_words:
        return empty

    normalized_query = re.sub(r"\s+", " ", query.lower()).strip()
    unique_query_words = set(query_words)

    # Tokenize each chunk once
    tokenized = []
    document_frequency = {}

    for document in rag_documents:
        words = tokenize(document.get("text", ""))
        tokenized.append(words)

        for word in set(words):
            document_frequency[word] = document_frequency.get(word, 0) + 1

    total_documents = len(rag_documents)
    scored = []

    for document, words in zip(rag_documents, tokenized):
        text = document.get("text", "")

        if not text or not words:
            continue

        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1

        score = 0.0

        # TF-IDF style score
        for query_word in query_words:
            if query_word not in word_counts:
                continue

            term_frequency = word_counts[query_word] / len(words)
            df = document_frequency.get(query_word, 0)
            idf = math.log((total_documents + 1) / (df + 1)) + 1
            score += term_frequency * idf

        # Exact phrase bonus
        if len(normalized_query) >= 8 and normalized_query in text.lower():
            score += 2.0

        # Query coverage bonus
        matched = sum(1 for w in unique_query_words if w in word_counts)
        score += (matched / len(unique_query_words)) * 0.5

        if score > 0:
            scored.append((score, document))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_documents = scored[:RAG_TOP_K]

    if not top_documents:
        return empty

    context_parts = []
    sources = []

    for score, document in top_documents:
        source = document.get("source", "Unknown document")
        page = document.get("page", "Unknown")
        text = document.get("text", "")

        context_parts.append(f"[Source: {source} | Page: {page}]\n\n{text}")

        source_entry = {"source": source, "page": page}
        if source_entry not in sources:
            sources.append(source_entry)

    return {"context": "\n\n".join(context_parts), "sources": sources}


# =========================================================
# HOME (public health check, no user data)
# =========================================================

@app.get("/")
def home():
    return {
        "message": "AI Chatbot backend is running!",
        "version": "9.1",
        "ai": "Groq",
        "model": GROQ_MODEL,
        "auth": "Supabase (verified token)",
        "memory": "Per-user",
        "rag": "Per-user local TF-IDF-style retrieval",
        "rag_top_k": RAG_TOP_K,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
    }


# =========================================================
# CHAT
# (plain "def" so FastAPI runs it in a worker thread; the Groq call
#  and retry sleeps no longer freeze the server for other users)
# =========================================================

@app.post("/chat")
def chat(request: ChatRequest, user_id: str = Depends(get_current_user)):

    user_message = request.message.strip()

    if not user_message:
        return {"reply": "Please enter a message."}

    if len(user_message) > MAX_MESSAGE_CHARS:
        return {"reply": f"Message is too long (max {MAX_MESSAGE_CHARS} characters)."}

    print(f"\n=== CHAT | user {user_id} ===")
    print("User:", user_message)

    if openai_client is None:
        return {"reply": "⚠️ Groq API key is not configured on the backend."}

    # Load this user's memory + search this user's documents
    conversation_history = load_history(user_id)
    rag_result = search_rag(user_id, user_message)

    rag_context = rag_result["context"]
    sources = rag_result["sources"]

    if rag_context:
        user_content = f"""
User question:

{user_message}

Relevant information from the user's uploaded documents:

{rag_context}

Use the document information when it is relevant.

If the document information does not answer the
question, you may use your general knowledge.

Do not claim that the document information came
from the internet.
"""
    else:
        user_content = user_message

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for item in conversation_history:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_content})

    # Groq request with retries
    response = None
    last_error = None

    for attempt in range(3):
        try:
            print(f"Groq request attempt {attempt + 1}")
            response = openai_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
            )
            break
        except Exception as e:
            last_error = e
            print("GROQ ERROR:", e)

            if attempt < 2:
                time.sleep(2 ** attempt)

    if response is None:
        print("GROQ FINAL ERROR:", last_error)
        return {"reply": "⚠️ I could not get a response from the AI right now. Please try again."}

    try:
        assistant_message = response.choices[0].message.content
    except Exception as e:
        print("RESPONSE PARSING ERROR:", e)
        return {"reply": "⚠️ The AI returned an invalid response."}

    if not assistant_message:
        assistant_message = "⚠️ The AI returned an empty response."

    assistant_message = assistant_message.strip()

    # Save memory (re-load inside the lock so parallel requests don't lose messages)
    with user_lock(user_id):
        latest_history = load_history(user_id)
        latest_history.append({"role": "user", "content": user_message})
        latest_history.append({"role": "assistant", "content": assistant_message})
        save_history(user_id, latest_history)

    final_reply = assistant_message

    if sources:
        source_lines = [
            f"• {s.get('source', 'Unknown')} — Page {s.get('page', 'Unknown')}"
            for s in sources
        ]
        final_reply += "\n\n📚 Sources:\n" + "\n".join(source_lines)

    print("AI:", assistant_message)

    return {"reply": final_reply, "sources": sources}


# =========================================================
# RESET (clears ONLY the logged-in user's memory)
# =========================================================

@app.post("/reset")
def reset_memory(user_id: str = Depends(get_current_user)):

    with user_lock(user_id):
        save_history(user_id, [])

    print(f"=== MEMORY RESET | user {user_id} ===")

    return {
        "success": True,
        "message": "Your conversation memory has been reset.",
    }


# =========================================================
# LIST MY DOCUMENTS
# =========================================================

@app.get("/documents")
def list_documents(user_id: str = Depends(get_current_user)):

    rag_documents = load_rag(user_id)

    counts = {}
    for d in rag_documents:
        name = d.get("source", "Unknown")
        counts[name] = counts.get(name, 0) + 1

    return {
        "success": True,
        "documents": [{"filename": n, "chunks": c} for n, c in counts.items()],
    }


# =========================================================
# PDF UPLOAD (plain "def": PDF parsing is CPU work, runs in a thread)
# =========================================================

@app.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):

    print(f"\n=== PDF UPLOAD | user {user_id} ===")

    if not file.filename:
        return {"success": False, "message": "No filename provided."}

    filename = safe_filename(file.filename)

    if not filename.lower().endswith(".pdf"):
        return {"success": False, "message": "Only PDF files are supported."}

    print("Filename:", filename)

    # Read at most limit + 1 bytes so oversized files are rejected early
    try:
        file_data = file.file.read(MAX_UPLOAD_BYTES + 1)
    except Exception as e:
        print("FILE READ ERROR:", e)
        return {"success": False, "message": "Could not read the uploaded file."}

    if not file_data:
        return {"success": False, "message": "The uploaded PDF is empty."}

    if len(file_data) > MAX_UPLOAD_BYTES:
        return {
            "success": False,
            "message": f"PDF is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        }

    # Extract text
    try:
        reader = PdfReader(BytesIO(file_data))

        if reader.is_encrypted:
            return {"success": False, "message": "Password-protected PDFs are not supported."}

        all_chunks = []

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text()

                if page_text:
                    all_chunks.extend(create_chunks(page_text, page_number))

            except Exception as e:
                print(f"Could not read page {page_number}:", e)

        page_count = len(reader.pages)

    except Exception as e:
        print("PDF EXTRACTION ERROR:", e)
        return {"success": False, "message": "Could not read this PDF. Is it a valid file?"}

    if not all_chunks:
        return {
            "success": False,
            "message": (
                "No readable text was found in the PDF. "
                "If this is a scanned PDF, OCR will be needed later."
            ),
        }

    new_documents = [
        {"source": filename, "page": c["page"], "text": c["text"]}
        for c in all_chunks
    ]

    # Duplicate check + save, under this user's lock
    with user_lock(user_id):

        rag_documents = load_rag(user_id)

        if document_exists(rag_documents, filename):
            return {"success": False, "message": "This PDF is already uploaded."}

        paths = get_user_paths(user_id)
        pdf_path = os.path.join(paths["documents_dir"], filename)

        try:
            with open(pdf_path, "wb") as f:
                f.write(file_data)
        except Exception as e:
            print("PDF SAVE ERROR:", e)
            return {"success": False, "message": "Could not save the PDF."}

        try:
            rag_documents.extend(new_documents)
            save_rag(user_id, rag_documents)
        except Exception as e:
            print("RAG SAVE ERROR:", e)
            return {"success": False, "message": "Could not save the document to your knowledge base."}

        total_chunks = len(rag_documents)

    print(f"PDF uploaded: {filename} | pages {page_count} | chunks {len(new_documents)}")

    return {
        "success": True,
        "message": "PDF uploaded successfully.",
        "filename": filename,
        "pages": page_count,
        "chunks_added": len(new_documents),
        "total_rag_chunks": total_chunks,
    }
