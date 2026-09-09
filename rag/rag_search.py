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

client = chromadb.PersistentClient(
    path=DATABASE_DIR
)


# -----------------------------
# LOCAL EMBEDDING MODEL
# -----------------------------

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


# -----------------------------
# CREATE / GET COLLECTION
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

if os.path.exists(DOCUMENTS_DIR):

    for filename in os.listdir(DOCUMENTS_DIR):

        if filename.endswith(".txt"):

            file_path = os.path.join(
                DOCUMENTS_DIR,
                filename
            )

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as file:

                text = file.read()


            # Split document into smaller chunks
            chunk_size = 500

            for i in range(0, len(text), chunk_size):

                chunk = text[i:i + chunk_size].strip()

                if chunk:

                    documents.append(chunk)

                    ids.append(
                        f"{filename}_{i}"
                    )


# -----------------------------
# ADD TO VECTOR DATABASE
# -----------------------------

if documents:

    collection.upsert(
        documents=documents,
        ids=ids
    )

    print("================================")
    print("RAG DATABASE READY")
    print("================================")
    print("Documents:", len(documents))

else:

    print("No .txt documents found.")


# -----------------------------
# RAG SEARCH FUNCTION
# -----------------------------

def search_knowledge(query, n_results=3):

    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )

    documents = results.get(
        "documents",
        [[]]
    )[0]

    return documents


# -----------------------------
# TEST DATABASE
# -----------------------------

if __name__ == "__main__":

    print()
    print("Testing RAG database...")

    results = search_knowledge(
        "What is this AI chatbot project?",
        2
    )

    print()
    print("SEARCH RESULTS:")

    for result in results:

        print("--------------------------------")

        print(result)