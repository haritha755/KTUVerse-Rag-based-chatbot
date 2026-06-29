import os
import shutil
import sqlite3
import hashlib
import secrets
import json

from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Any

from ollama import chat

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

db = Chroma(
    persist_directory="vectorstore",
    embedding_function=embeddings
)
DATA_DIR = r"C:\Users\harit\uploads"
os.makedirs(DATA_DIR, exist_ok=True)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=2000,
    chunk_overlap=400
)


# =====================================================
# AUTH & CHAT HISTORY (SQLite)
# =====================================================

DB_PATH = "app.db"

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        security_question TEXT,
        security_answer_hash TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tokens (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        title TEXT,
        history TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

init_db()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_id_from_token(token: str):
    if not token:
        return None
    conn = get_db_conn()
    row = conn.execute("SELECT user_id FROM tokens WHERE token=?", (token,)).fetchone()
    conn.close()
    return row["user_id"] if row else None


class AuthRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    security_question: str
    security_answer: str

class ForgotPasswordCheck(BaseModel):
    username: str

class ResetPasswordRequest(BaseModel):
    username: str
    security_answer: str
    new_password: str

class SessionData(BaseModel):
    token: str
    id: str
    title: str
    history: List[dict]

class TokenRequest(BaseModel):
    token: str


@app.post("/register")
def register(req: RegisterRequest):
    username = req.username.strip()
    password = req.password
    security_question = req.security_question.strip()
    security_answer = req.security_answer.strip()

    if not username or not password or not security_question or not security_answer:
        return {"status": "error", "message": "All fields are required"}

    conn = get_db_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, security_question, security_answer_hash) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), security_question, hash_password(security_answer.lower()))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return {"status": "error", "message": "Username already exists"}
    conn.close()
    return {"status": "success"}


@app.post("/forgot-password/question")
def get_security_question(req: ForgotPasswordCheck):
    conn = get_db_conn()
    row = conn.execute(
        "SELECT security_question FROM users WHERE username=?",
        (req.username.strip(),)
    ).fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": "No account found with that username"}

    return {"status": "success", "security_question": row["security_question"]}


@app.post("/forgot-password/reset")
def reset_password(req: ResetPasswordRequest):
    conn = get_db_conn()
    row = conn.execute(
        "SELECT id, security_answer_hash FROM users WHERE username=?",
        (req.username.strip(),)
    ).fetchone()

    if not row:
        conn.close()
        return {"status": "error", "message": "No account found with that username"}

    if row["security_answer_hash"] != hash_password(req.security_answer.strip().lower()):
        conn.close()
        return {"status": "error", "message": "Security answer is incorrect"}

    conn.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (hash_password(req.new_password), row["id"])
    )
    # Invalidate existing sessions for security
    conn.execute("DELETE FROM tokens WHERE user_id=?", (row["id"],))
    conn.commit()
    conn.close()

    return {"status": "success"}


@app.post("/login")
def login(req: AuthRequest):
    conn = get_db_conn()
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE username=?",
        (req.username.strip(),)
    ).fetchone()

    if not row or row["password_hash"] != hash_password(req.password):
        conn.close()
        return {"status": "error", "message": "Invalid username or password"}

    token = secrets.token_hex(16)
    conn.execute("INSERT INTO tokens (token, user_id) VALUES (?, ?)", (token, row["id"]))
    conn.commit()
    conn.close()

    return {"status": "success", "token": token, "username": req.username.strip()}


@app.post("/logout")
def logout(req: TokenRequest):
    conn = get_db_conn()
    conn.execute("DELETE FROM tokens WHERE token=?", (req.token,))
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.post("/sessions/list")
def list_sessions(req: TokenRequest):
    user_id = get_user_id_from_token(req.token)
    if not user_id:
        return {"status": "error", "message": "Invalid or expired token"}

    conn = get_db_conn()
    rows = conn.execute(
        "SELECT id, title, history FROM sessions WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()

    sessions = [
        {"id": r["id"], "title": r["title"], "history": json.loads(r["history"])}
        for r in rows
    ]
    return {"status": "success", "sessions": sessions}


@app.post("/sessions/save")
def save_session(data: SessionData):
    user_id = get_user_id_from_token(data.token)
    if not user_id:
        return {"status": "error", "message": "Invalid or expired token"}

    conn = get_db_conn()
    existing = conn.execute(
        "SELECT id FROM sessions WHERE id=? AND user_id=?", (data.id, user_id)
    ).fetchone()

    history_json = json.dumps(data.history)

    if existing:
        conn.execute(
            "UPDATE sessions SET title=?, history=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (data.title, history_json, data.id)
        )
    else:
        conn.execute(
            "INSERT INTO sessions (id, user_id, title, history) VALUES (?, ?, ?, ?)",
            (data.id, user_id, data.title, history_json)
        )

    conn.commit()
    conn.close()
    return {"status": "success"}


class Message(BaseModel):
    role: str
    content: str

class Query(BaseModel):
    message: str
    history: Optional[List[Message]] = []


def rewrite_query(history: List[Message], new_query: str) -> str:
    vague_phrases = [
    "in more detail", "more detail", "explain", "tell me more",
    "elaborate", "go on", "continue", "and?", "what else", "expand",
    "in detail", "detail", "more", "elaborate more", "tell more"
]

    is_vague = any(phrase in new_query.lower() for phrase in vague_phrases)

    if not is_vague or not history:
        return new_query

    last_user_msg = ""
    for msg in reversed(history):
        if msg.role == "user":
            last_user_msg = msg.content
            break

    if last_user_msg:
        rewritten = f"{last_user_msg} - explain in more detail"
        print(f"[Query Rewriter] '{new_query}' → '{rewritten}'")
        return rewritten

    return new_query


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        file_path = os.path.join(DATA_DIR, file.filename)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        loader = PyPDFLoader(file_path)
        pages = loader.load()
        chunks = text_splitter.split_documents(pages)

        for chunk in chunks:
            chunk.metadata["source"] = file.filename

        db.add_documents(chunks)
        db.persist()

        return {"status": "success", "chunks_added": len(chunks)}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/sources")
def list_sources():
    """List all unique PDF filenames currently indexed in the vector store, with chunk counts."""
    try:
        all_docs = db.get()
        metadatas = all_docs.get("metadatas", [])

        counts = {}
        for meta in metadatas:
            source = meta.get("source", "unknown")
            counts[source] = counts.get(source, 0) + 1

        sources = [
            {"filename": name, "chunks": count}
            for name, count in sorted(counts.items())
        ]
        return {"status": "success", "sources": sources}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class DeleteSourceRequest(BaseModel):
    filename: str

@app.post("/delete-source")
def delete_source(req: DeleteSourceRequest):
    """Delete all vector chunks belonging to a specific uploaded PDF, and remove the file from disk."""
    try:
        db.delete(where={"source": req.filename})
        db.persist()

        # Strip any folder prefix baked into the stored filename (e.g. "data/x.pdf" -> "x.pdf")
        clean_name = os.path.basename(req.filename)
        file_path = os.path.join(DATA_DIR, clean_name)

        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            return {"status": "success", "message": f"Removed {req.filename} from search index (file was not found on disk, may have been added with a different path)"}

        return {"status": "success", "message": f"Removed {req.filename} from knowledge base"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
@app.post("/chat")
def chatbot(query: Query):

    try:
        user_query = query.message
        history = query.history or []
        normalized = user_query.lower().strip()

        # -------------------------
        # Greetings & casual chat (prefix-aware, not exact-match-only)
        # -------------------------

        greetings = ["hi", "hello", "hey", "good morning", "good evening", "how are you", "thanks", "thank you"]

        is_greeting = any(
            normalized == g or normalized.startswith(g + " ") or normalized.startswith(g + ",") or normalized.startswith(g + "!")
            for g in greetings
        )

        if is_greeting:
            response = chat(
                model="llama3.2:3b",
                messages=[
                    {"role": "system", "content": "You are KTUVerse, a friendly assistant for KTU university students. Keep casual replies brief and warm."},
                    {"role": "user", "content": user_query}
                ]
            )
            return {"response": response["message"]["content"]}

        # -------------------------
        # Rewrite vague queries
        # -------------------------

        smart_query = rewrite_query(history, user_query)

        # -------------------------
        # Search RAG DB with relevance scores
        # -------------------------

        docs_with_scores = db.similarity_search_with_score(smart_query, k=8)

        # Chroma returns L2 distance by default: LOWER score = MORE similar.
        # Keep only chunks that are reasonably close to the query.
        RELEVANCE_THRESHOLD = 1.0  # tune this based on testing (see note below)

        relevant_docs = [doc for doc, score in docs_with_scores if score < RELEVANCE_THRESHOLD]

        context = "\n\n".join(doc.page_content for doc in relevant_docs)

        # -------------------------
        # No relevant context found — likely off-topic/chit-chat, don't force a RAG answer
        # -------------------------

        if len(context.strip()) < 100:
            response = chat(
                model="llama3.2:3b",
                messages=[
                    {"role": "system", "content": (
                        "You are KTUVerse, a helpful assistant for KTU university students. "
                        "This question doesn't match anything in the KTU scheme knowledge base. "
                        "Answer briefly and naturally as a general assistant, and if relevant, "
                        "mention you're best at KTU 2024 scheme questions (syllabus, credits, exams, internships)."
                    )},
                    {"role": "user", "content": user_query}
                ]
            )
            return {"response": response["message"]["content"]}

        # -------------------------
        # Build Ollama history
        # -------------------------

        recent_history = history[-6:] if len(history) > 6 else history
        messages = [
            {
                "role": "system",
                "content": """You are KTUVerse, an expert AI assistant for KTU.
RULES:
- Answer from the provided context.
- Extract and present ALL relevant information from the context clearly.
- Use bullet points and structure your answer well.
- If elaborating on a previous topic, focus ONLY on that topic.
- Do NOT say 'it is not explicitly stated' — just present what IS in the context.
- Be direct and informative."""
            }
        ]
        for msg in recent_history:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({
            "role": "user",
            "content": f"""Context from KTU knowledge base:

{context}

Student's Question:
{user_query}

Answer based strictly on the context above. If elaborating, stay on the same topic as before."""
        })

        response = chat(model="llama3.2:3b", messages=messages)
        return {"response": response["message"]["content"]}

    except Exception as e:
        return {"response": str(e)}