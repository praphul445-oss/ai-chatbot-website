import os
import chromadb
from chromadb.utils import embedding_functions

# -----------------------------
# PATHS
# -----------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOCUMENTS_DIR = os.path.join(BASE_DIR, "documents")
DATABASE_DIR = os.path.join(BASE_DIR, "chroma_db")

# -----------------------------
# CHROMA DATABASE
# -----------------------------

client = chromadb.PersistentClient(path=DATABASE_DIR)

# -----------------------------
# LOCAL EMBEDDING MODEL
# -----------------------------

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# -----------------------------
# CREATE COLLECTION
# -----------------------------

collection = client.get_or_create_collection(
    name="knowledge",
    embedding_function=embedding_function
)

# -----------------------------
# LOAD DOCUMENTS
# -----------------------------

documents = []
ids = []

for filename in os.listdir(DOCUMENTS_DIR):

    if filename.endswith(".txt"):

        file_path = os.path.join(DOCUMENTS_DIR, filename)

        with open(file_path, "r", encoding="utf-8") as file:
            text = file.read()

        # Split document into smaller chunks
        chunk_size = 500

        for i in range(0, len(text), chunk_size):

            chunk = text[i:i + chunk_size].strip()

            if chunk:
                documents.append(chunk)
                ids.append(f"{filename}_{i}")

# -----------------------------
# ADD TO VECTOR DATABASE
# -----------------------------

if documents:

    collection.upsert(
        documents=documents,
        ids=ids
    )

    print("================================")
    print("RAG DATABASE CREATED SUCCESSFULLY")
    print("================================")
    print("Documents:", len(documents))

else:

    print("No .txt documents found.")

# -----------------------------
# TEST DATABASE
# -----------------------------

print()
print("Testing RAG database...")

results = collection.query(
    query_texts=["What is this AI chatbot project?"],
    n_results=2
)

print()
print("SEARCH RESULTS:")

for result in results["documents"][0]:
    print("--------------------------------")
    print(result)