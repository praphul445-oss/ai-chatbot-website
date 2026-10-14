
"""
My AI Chatbot API (v10.0)

Existing features:
- Groq chat
- Verified Supabase user authentication
- Per-user conversation memory
- Per-user PDF upload and local RAG

Hardware integration:
- Authenticated pairing-code generation
- One-time ESP32-S3 pairing
- Random per-device bearer credentials
- Hashed device credentials at rest
- Authenticated heartbeat endpoint
- Owner-only hardware status
- Device revocation

Required environment variables:
    GROQ_API_KEY
    SUPABASE_URL
    SUPABASE_ANON_KEY or SUPABASE_PUBLISHABLE_KEY

Optional:
    GROQ_MODEL
    ALLOWED_ORIGINS
    DATA_DIR (persistent disk recommended)
"""

import hashlib
import json
import math
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
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
    description="Groq chatbot with Supabase authentication, RAG and secure hardware pairing",
    version="10.0",
)


# =========================================================
# CORS
# =========================================================

_origins_env = os.getenv("ALLOWED_ORIGINS", "*").strip()

ALLOWED_ORIGINS = (
    ["*"]
    if _origins_env == "*"
    else [origin.strip() for origin in _origins_env.split(",") if origin.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# SETTINGS
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def clean_env_value(value):
    if value is None:
        return ""

    value = str(value).strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()

    return value


SUPABASE_URL = clean_env_value(os.getenv("SUPABASE_URL")).rstrip("/")
SUPABASE_ANON_KEY = clean_env_value(os.getenv("SUPABASE_ANON_KEY"))
SUPABASE_PUBLISHABLE_KEY = clean_env_value(
    os.getenv("SUPABASE_PUBLISHABLE_KEY")
)
SUPABASE_KEY = SUPABASE_ANON_KEY or SUPABASE_PUBLISHABLE_KEY

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR") or os.path.join(BASE_DIR, "data")
USERS_DIR = os.path.join(DATA_DIR, "users")
os.makedirs(USERS_DIR, exist_ok=True)

MAX_MEMORY_MESSAGES = 10
MAX_MESSAGE_CHARS = 4000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
RAG_TOP_K = 5

# Hardware security settings
PAIRING_CODE_TTL_SECONDS = 600  # 10 minutes
DEVICE_ONLINE_WINDOW_SECONDS = 90
MAX_DEVICES_PER_USER = 5
MAX_DEVICE_ID_LENGTH = 100
MAX_DEVICE_NAME_LENGTH = 80

HARDWARE_DIR = os.path.join(DATA_DIR, "hardware")
os.makedirs(HARDWARE_DIR, exist_ok=True)

PAIRING_CODES_FILE = os.path.join(HARDWARE_DIR, "pairing_codes.json")
DEVICES_FILE = os.path.join(HARDWARE_DIR, "devices.json")


# =========================================================
# CLIENTS
# =========================================================

if GROQ_API_KEY:
    openai_client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
    print("=== GROQ CONNECTED ===")
    print("Groq model:", GROQ_MODEL)
else:
    openai_client = None
    print("=== WARNING: GROQ_API_KEY NOT SET ===")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("=== WARNING: SUPABASE AUTH NOT CONFIGURED ===")
else:
    print("Supabase URL:", SUPABASE_URL)


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are a helpful AI chatbot.

Remember and use information the user tells you during the conversation.

You have access to a local RAG knowledge base made of the user's uploaded
documents. Prefer relevant uploaded-document information for questions about
those documents. Do not invent information and do not claim that document
information came from the internet. If the documents are not relevant, answer
normally using general knowledge. Keep answers clear and useful.
"""


# =========================================================
# REQUEST MODELS
# =========================================================

class ChatRequest(BaseModel):
    message: str


class PairingCodeRequest(BaseModel):
    # Optional friendly label shown in the Hardware page.
    device_name: str = "ESP32-S3"


class DevicePairRequest(BaseModel):
    pairing_code: str
    device_id: str
    device_name: str = "ESP32-S3"


class DeviceHeartbeatRequest(BaseModel):
    device_id: str
    status: str = "online"
    components: dict = {}


# =========================================================
# COMMON HELPERS
# =========================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat()


def parse_timestamp(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed
    except (ValueError, TypeError, AttributeError):
        return None


def clean_user_id(user_id):
    if not user_id:
        return None

    user_id = str(user_id).strip()

    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", user_id):
        return None

    return user_id


def hash_secret(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def read_json_file(path, default):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            value = json.load(file)

        return value
    except (OSError, json.JSONDecodeError) as error:
        print("JSON READ ERROR:", os.path.basename(path), repr(error))
        return default


def write_json_atomic(path, value):
    temporary_path = path + ".tmp"

    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(value, file, indent=2, ensure_ascii=False)

    os.replace(temporary_path, path)


# =========================================================
# SUPABASE AUTHENTICATION
# =========================================================

async def get_current_user(authorization: str = Header(None)):
    """
    Verify the user's Supabase access token with Supabase Auth.
    Never accept a user ID supplied by the frontend as proof of identity.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing login token.")

    token = authorization.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Missing login token.")

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(
            status_code=500,
            detail="Supabase authentication is not configured.",
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_KEY,
                },
            )
    except httpx.HTTPError as error:
        print("SUPABASE AUTH CONNECTION ERROR:", repr(error))
        raise HTTPException(
            status_code=503,
            detail="Could not verify login. Please try again.",
        )

    if response.status_code != 200:
        # Never log access tokens or authentication keys.
        print("SUPABASE AUTH STATUS:", response.status_code)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login.",
        )

    try:
        user_id = clean_user_id(response.json().get("id"))
    except (ValueError, TypeError, AttributeError):
        user_id = None

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user.")

    return user_id


# =========================================================
# PER-USER LOCKS
# =========================================================

_locks = {}
_locks_guard = threading.Lock()


def user_lock(user_id):
    with _locks_guard:
        if user_id not in _locks:
            _locks[user_id] = threading.Lock()

        return _locks[user_id]


# =========================================================
# USER DATA PATHS
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
    data = read_json_file(path, [])

    return data if isinstance(data, list) else []


# =========================================================
# MEMORY
# =========================================================

def load_history(user_id):
    paths = get_user_paths(user_id)
    return read_json_list(paths["memory_file"])[-MAX_MEMORY_MESSAGES:]


def save_history(user_id, history):
    paths = get_user_paths(user_id)

    try:
        write_json_atomic(
            paths["memory_file"],
            history[-MAX_MEMORY_MESSAGES:],
        )
    except OSError as error:
        print("MEMORY SAVE ERROR:", repr(error))

    return history[-MAX_MEMORY_MESSAGES:]


# =========================================================
# RAG LOAD / SAVE
# =========================================================

def load_rag(user_id):
    return read_json_list(get_user_paths(user_id)["rag_file"])


def save_rag(user_id, data):
    write_json_atomic(get_user_paths(user_id)["rag_file"], data)


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
    return [word for word in words if word not in STOP_WORDS]


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
    return any(document.get("source") == filename for document in rag_documents)


def safe_filename(name):
    name = os.path.basename(name or "")
    name = re.sub(r"[^\w.\- ]", "_", name).strip()
    return name[:150]


# =========================================================
# RAG SEARCH
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

        for query_word in query_words:
            if query_word not in word_counts:
                continue

            term_frequency = word_counts[query_word] / len(words)
            df = document_frequency.get(query_word, 0)
            idf = math.log((total_documents + 1) / (df + 1)) + 1
            score += term_frequency * idf

        if len(normalized_query) >= 8 and normalized_query in text.lower():
            score += 2.0

        matched = sum(
            1 for word in unique_query_words if word in word_counts
        )
        score += (matched / len(unique_query_words)) * 0.5

        if score > 0:
            scored.append((score, document))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_documents = scored[:RAG_TOP_K]

    if not top_documents:
        return empty

    context_parts = []
    sources = []

    for _, document in top_documents:
        source = document.get("source", "Unknown document")
        page = document.get("page", "Unknown")
        text = document.get("text", "")

        context_parts.append(f"[Source: {source} | Page: {page}]\n\n{text}")

        source_entry = {"source": source, "page": page}

        if source_entry not in sources:
            sources.append(source_entry)

    return {
        "context": "\n\n".join(context_parts),
        "sources": sources,
    }


# =========================================================
# HARDWARE REGISTRY
# =========================================================

_hardware_lock = threading.Lock()


def load_pairing_codes():
    data = read_json_file(PAIRING_CODES_FILE, {})
    return data if isinstance(data, dict) else {}


def save_pairing_codes(data):
    write_json_atomic(PAIRING_CODES_FILE, data)


def load_devices():
    data = read_json_file(DEVICES_FILE, {})
    return data if isinstance(data, dict) else {}


def save_devices(data):
    write_json_atomic(DEVICES_FILE, data)


def clean_device_id(device_id):
    if not isinstance(device_id, str):
        return None

    device_id = device_id.strip()

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", device_id):
        return None

    return device_id


def clean_device_name(device_name):
    if not isinstance(device_name, str):
        return "ESP32-S3"

    device_name = re.sub(r"[\r\n\t]", " ", device_name).strip()

    if not device_name:
        return "ESP32-S3"

    return device_name[:MAX_DEVICE_NAME_LENGTH]


def get_owned_devices(user_id):
    devices = load_devices()

    return {
        device_id: device
        for device_id, device in devices.items()
        if device.get("owner_id") == user_id
            and not device.get("revoked", False)
    }


def device_is_online(device):
    last_seen = parse_timestamp(device.get("last_seen"))

    if last_seen is None:
        return False

    age = (utc_now() - last_seen).total_seconds()

    return 0 <= age <= DEVICE_ONLINE_WINDOW_SECONDS


def public_device_status(device_id, device):
    online = device_is_online(device)

    return {
        "device_id": device_id,
        "device_name": device.get("device_name", "ESP32-S3"),
        "verified": True,
        "status": "online" if online else "offline",
        "last_seen": device.get("last_seen"),
        "components": device.get(
            "components",
            {
                "microphone": {"status": "planned"},
                "audio_output": {"status": "planned"},
            },
        ),
    }


def verify_device_credential(device_id, supplied_token):
    if not supplied_token:
        return None

    devices = load_devices()
    device = devices.get(device_id)

    if not device or device.get("revoked", False):
        return None

    expected_hash = device.get("token_hash", "")

    if not expected_hash:
        return None

    if not secrets.compare_digest(hash_secret(supplied_token), expected_hash):
        return None

    return device


# =========================================================
# HOME / HEALTH CHECK
# =========================================================

@app.get("/")
def home():
    return {
        "message": "AI Chatbot backend is running!",
        "version": "10.0",
        "ai": "Groq",
        "model": GROQ_MODEL,
        "auth": "Supabase verified token",
        "memory": "Per-user",
        "rag": "Per-user local TF-IDF-style retrieval",
        "hardware": "Secure device pairing and heartbeat",
        "rag_top_k": RAG_TOP_K,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
    }


# =========================================================
# HARDWARE: CREATE A PAIRING CODE
# =========================================================

@app.post("/hardware/pairing-code")
def create_pairing_code(
    request: PairingCodeRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Called by the signed-in website.

    Returns a one-time pairing code. Show it only to the signed-in user.
    The code expires after ten minutes and is consumed when successfully used.
    """
    device_name = clean_device_name(request.device_name)
    code = secrets.token_urlsafe(24)
    now = utc_now()

    with _hardware_lock:
        devices = load_devices()

        owned_count = sum(
            1
            for device in devices.values()
            if device.get("owner_id") == user_id
            and not device.get("revoked", False)
        )

        if owned_count >= MAX_DEVICES_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"You can register up to {MAX_DEVICES_PER_USER} devices.",
            )

        codes = load_pairing_codes()

        # Remove expired codes before saving.
        codes = {
            code_hash: item
            for code_hash, item in codes.items()
            if parse_timestamp(item.get("expires_at")) is not None
            and parse_timestamp(item.get("expires_at")) > now
        }

        codes[hash_secret(code)] = {
            "owner_id": user_id,
            "device_name": device_name,
            "created_at": now.isoformat(),
            "expires_at": (
                now + timedelta(seconds=PAIRING_CODE_TTL_SECONDS)
            ).isoformat(),
        }

        save_pairing_codes(codes)

    # This is the only response that reveals the pairing code.
    return {
        "success": True,
        "pairing_code": code,
        "device_name": device_name,
        "expires_in_seconds": PAIRING_CODE_TTL_SECONDS,
        "message": "Enter this code into your trusted ESP32 setup.",
    }


# =========================================================
# HARDWARE: PAIR AN ESP32-S3
# =========================================================

@app.post("/hardware/pair")
def pair_device(request: DevicePairRequest):
    """
    Called by the ESP32-S3 setup process.

    A successful pairing consumes the code and returns a random device
    credential exactly once. The server stores only its SHA-256 hash.
    """
    device_id = clean_device_id(request.device_id)

    if not device_id:
        raise HTTPException(status_code=400, detail="Invalid device ID.")

    code = request.pairing_code.strip()

    if not code or len(code) > 200:
        raise HTTPException(status_code=400, detail="Invalid pairing code.")

    device_name = clean_device_name(request.device_name)
    code_hash = hash_secret(code)
    now = utc_now()

    with _hardware_lock:
        codes = load_pairing_codes()
        pairing_record = codes.get(code_hash)

        if not pairing_record:
            raise HTTPException(
                status_code=401,
                detail="Invalid or already-used pairing code.",
            )

        expires_at = parse_timestamp(pairing_record.get("expires_at"))

        if expires_at is None or expires_at <= now:
            codes.pop(code_hash, None)
            save_pairing_codes(codes)

            raise HTTPException(
                status_code=401,
                detail="Pairing code expired. Generate a new code.",
            )

        owner_id = pairing_record.get("owner_id")

        if not clean_user_id(owner_id):
            raise HTTPException(status_code=401, detail="Invalid pairing owner.")

        devices = load_devices()

        # A device ID cannot be claimed by another owner.
        existing = devices.get(device_id)

        if existing and not existing.get("revoked", False):
            raise HTTPException(
                status_code=409,
                detail="This device ID is already registered.",
            )

        owned_count = sum(
            1
            for device in devices.values()
            if device.get("owner_id") == owner_id
            and not device.get("revoked", False)
        )

        if owned_count >= MAX_DEVICES_PER_USER:
            raise HTTPException(
                status_code=400,
                detail=f"You can register up to {MAX_DEVICES_PER_USER} devices.",
            )

        # Generate a high-entropy, unique credential.
        device_token = secrets.token_urlsafe(48)

        devices[device_id] = {
            "owner_id": owner_id,
            "device_name": clean_device_name(
                pairing_record.get("device_name") or device_name
            ),
            "token_hash": hash_secret(device_token),
            "created_at": now.isoformat(),
            "last_seen": None,
            "components": {
                "microphone": {"status": "planned"},
                "audio_output": {"status": "planned"},
            },
            "revoked": False,
        }

        # Consume the pairing code on successful pairing.
        codes.pop(code_hash, None)

        save_devices(devices)
        save_pairing_codes(codes)

    # IMPORTANT: this raw token is not saved in the registry.
    # The ESP32 must store it securely and never print it to logs.
    return {
        "success": True,
        "device_id": device_id,
        "device_token": device_token,
        "message": "Device paired. Save this credential securely.",
    }


# =========================================================
# HARDWARE: DEVICE HEARTBEAT
# =========================================================

@app.post("/hardware/heartbeat")
def hardware_heartbeat(
    request: DeviceHeartbeatRequest,
    authorization: str = Header(None),
):
    """
    The ESP32 calls this endpoint periodically.

    Authorization: Bearer <device_token>

    The device credential is different from the user's Supabase token.
    """
    device_id = clean_device_id(request.device_id)

    if not device_id:
        raise HTTPException(status_code=400, detail="Invalid device ID.")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing device credential.",
        )

    device_token = authorization.split(" ", 1)[1].strip()

    if not device_token:
        raise HTTPException(
            status_code=401,
            detail="Missing device credential.",
        )

    safe_components = {}

    # Only accept the two known component status fields.
    incoming_components = request.components or {}

    for incoming_key, output_key in (
        ("microphone", "microphone"),
        ("audio_output", "audio_output"),
    ):
        value = incoming_components.get(incoming_key)

        if isinstance(value, dict):
            component_status = value.get("status", "unknown")
        elif isinstance(value, str):
            component_status = value
        else:
            component_status = None

        if component_status is not None:
            component_status = str(component_status).lower()

            if component_status not in {
                "planned", "connected", "ready", "error", "unknown"
            }:
                component_status = "unknown"

            safe_components[output_key] = {
                "status": component_status
            }

    with _hardware_lock:
        devices = load_devices()
        device = verify_device_credential(device_id, device_token)

        if not device:
            raise HTTPException(
                status_code=401,
                detail="Invalid or revoked device credential.",
            )

        device["last_seen"] = iso_now()

        # Do not claim components are connected unless the device reports it.
        if safe_components:
            current_components = device.get("components", {})
            current_components.update(safe_components)
            device["components"] = current_components

        # Status is derived from authenticated heartbeats, not user input.
        device["last_status"] = "online"
        devices[device_id] = device
        save_devices(devices)

    return {
        "success": True,
        "verified": True,
        "device_id": device_id,
        "status": "online",
        "last_seen": device["last_seen"],
    }


# =========================================================
# HARDWARE: STATUS FOR THE SIGNED-IN USER
# =========================================================

@app.get("/hardware/status")
def hardware_status(user_id: str = Depends(get_current_user)):
    """
    This route matches the website's existing /hardware/status request.
    It never returns device credentials or another user's devices.
    """
    with _hardware_lock:
        devices = get_owned_devices(user_id)

    if not devices:
        return {
            "success": True,
            "verified": False,
            "status": "not_paired",
            "connection": "Not connected",
            "last_seen": None,
            "device": None,
            "components": {
                "microphone": {"status": "planned"},
                "audio_output": {"status": "planned"},
            },
            "message": "No device has been paired with this account.",
        }

    # Show the most recently active registered device.
    device_id, device = max(
        devices.items(),
        key=lambda item: item[1].get("last_seen") or "",
    )

    public_status = public_device_status(device_id, device)

    return {
        "success": True,
        "verified": True,
        "status": public_status["status"],
        "connection": (
            "Connected" if public_status["status"] == "online"
            else "Offline"
        ),
        "last_seen": public_status["last_seen"],
        "device": public_status,
        "components": public_status["components"],
        "message": (
            "Device verified and online."
            if public_status["status"] == "online"
            else "Device paired, but no recent heartbeat was received."
        ),
    }


# =========================================================
# HARDWARE: REVOKE A DEVICE
# =========================================================

@app.delete("/hardware/devices/{device_id}")
def revoke_device(
    device_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    Revoke only a device owned by the authenticated user.
    A revoked credential can no longer send heartbeats.
    """
    safe_device_id = clean_device_id(device_id)

    if not safe_device_id:
        raise HTTPException(status_code=400, detail="Invalid device ID.")

    with _hardware_lock:
        devices = load_devices()
        device = devices.get(safe_device_id)

        if not device or device.get("owner_id") != user_id:
            # Do not reveal whether another user's device exists.
            raise HTTPException(status_code=404, detail="Device not found.")

        device["revoked"] = True
        device["revoked_at"] = iso_now()
        devices[safe_device_id] = device
        save_devices(devices)

    return {
        "success": True,
        "device_id": safe_device_id,
        "message": "Device revoked successfully.",
    }


# =========================================================
# CHAT
# =========================================================

@app.post("/chat")
def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user),
):
    user_message = request.message.strip()

    if not user_message:
        return {"reply": "Please enter a message."}

    if len(user_message) > MAX_MESSAGE_CHARS:
        return {
            "reply": f"Message is too long (max {MAX_MESSAGE_CHARS} characters)."
        }

    if openai_client is None:
        return {"reply": "Groq API key is not configured on the backend."}

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

Use the document information when it is relevant. If it does not answer the
question, you may use general knowledge. Do not claim the document information
came from the internet.
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

    response = None
    last_error = None

    for attempt in range(3):
        try:
            response = openai_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
            )
            break
        except Exception as error:
            last_error = error
            print("GROQ ERROR:", repr(error))

            if attempt < 2:
                time.sleep(2 ** attempt)

    if response is None:
        print("GROQ FINAL ERROR:", repr(last_error))
        return {
            "reply": "I could not get a response from the AI right now. Please try again."
        }

    try:
        assistant_message = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as error:
        print("RESPONSE PARSING ERROR:", repr(error))
        return {"reply": "The AI returned an invalid response."}

    if not assistant_message:
        assistant_message = "The AI returned an empty response."

    assistant_message = assistant_message.strip()

    with user_lock(user_id):
        latest_history = load_history(user_id)
        latest_history.append({"role": "user", "content": user_message})
        latest_history.append(
            {"role": "assistant", "content": assistant_message}
        )
        save_history(user_id, latest_history)

    final_reply = assistant_message

    if sources:
        source_lines = [
            f"• {source.get('source', 'Unknown')} — Page {source.get('page', 'Unknown')}"
            for source in sources
        ]
        final_reply += "\n\n📚 Sources:\n" + "\n".join(source_lines)

    return {"reply": final_reply, "sources": sources}


# =========================================================
# RESET USER MEMORY
# =========================================================

@app.post("/reset")
def reset_memory(user_id: str = Depends(get_current_user)):
    with user_lock(user_id):
        save_history(user_id, [])

    return {
        "success": True,
        "message": "Your conversation memory has been reset.",
    }


# =========================================================
# LIST USER DOCUMENTS
# =========================================================

@app.get("/documents")
def list_documents(user_id: str = Depends(get_current_user)):
    rag_documents = load_rag(user_id)
    counts = {}

    for document in rag_documents:
        name = document.get("source", "Unknown")
        counts[name] = counts.get(name, 0) + 1

    return {
        "success": True,
        "documents": [
            {"filename": name, "chunks": count}
            for name, count in counts.items()
        ],
    }


# =========================================================
# PDF UPLOAD
# =========================================================

@app.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    if not file.filename:
        return {"success": False, "message": "No filename provided."}

    filename = safe_filename(file.filename)

    if not filename.lower().endswith(".pdf"):
        return {"success": False, "message": "Only PDF files are supported."}

    try:
        file_data = file.file.read(MAX_UPLOAD_BYTES + 1)
    except Exception as error:
        print("FILE READ ERROR:", repr(error))
        return {"success": False, "message": "Could not read the uploaded file."}

    if not file_data:
        return {"success": False, "message": "The uploaded PDF is empty."}

    if len(file_data) > MAX_UPLOAD_BYTES:
        return {
            "success": False,
            "message": f"PDF is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        }

    try:
        reader = PdfReader(BytesIO(file_data))

        if reader.is_encrypted:
            return {
                "success": False,
                "message": "Password-protected PDFs are not supported.",
            }

        all_chunks = []

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text()

                if page_text:
                    all_chunks.extend(create_chunks(page_text, page_number))
            except Exception as error:
                print(f"Could not read page {page_number}:", repr(error))

        page_count = len(reader.pages)

    except Exception as error:
        print("PDF EXTRACTION ERROR:", repr(error))
        return {
            "success": False,
            "message": "Could not read this PDF. Is it a valid file?",
        }

    if not all_chunks:
        return {
            "success": False,
            "message": (
                "No readable text was found in the PDF. "
                "Scanned PDFs will need OCR."
            ),
        }

    new_documents = [
        {
            "source": filename,
            "page": chunk["page"],
            "text": chunk["text"],
        }
        for chunk in all_chunks
    ]

    with user_lock(user_id):
        rag_documents = load_rag(user_id)

        if document_exists(rag_documents, filename):
            return {
                "success": False,
                "message": "This PDF is already uploaded.",
            }

        paths = get_user_paths(user_id)
        pdf_path = os.path.join(paths["documents_dir"], filename)

        try:
            with open(pdf_path, "wb") as file_handle:
                file_handle.write(file_data)
        except OSError as error:
            print("PDF SAVE ERROR:", repr(error))
            return {"success": False, "message": "Could not save the PDF."}

        try:
            rag_documents.extend(new_documents)
            save_rag(user_id, rag_documents)
        except Exception as error:
            print("RAG SAVE ERROR:", repr(error))
            return {
                "success": False,
                "message": "Could not save the document to your knowledge base.",
            }

        total_chunks = len(rag_documents)

    return {
        "success": True,
        "message": "PDF uploaded successfully.",
        "filename": filename,
        "pages": page_count,
        "chunks_added": len(new_documents),
        "total_rag_chunks": total_chunks,
    }
