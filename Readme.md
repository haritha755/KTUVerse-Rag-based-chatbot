# KTUVerse

KTUVerse is a RAG-based chatbot that helps KTU (APJ Abdul Kalam Technological University) students navigate the 2024 academic scheme — covering syllabus, credit structure, exam rules, internships, and project/seminar evaluation.

It retrieves answers from official KTU documents instead of relying on general knowledge, so responses stay grounded in the actual scheme rules.

## Features

- Chat interface with conversation history per user
- PDF upload to expand the knowledge base on the fly
- Knowledge base manager to view and delete indexed documents
- Voice input (speech-to-text) and voice output (text-to-speech)
- User accounts with login, registration, and password recovery via security question

## Tech Stack

- **Backend:** FastAPI, SQLite (auth & chat sessions)
- **RAG pipeline:** LangChain, Chroma (vector store), HuggingFace sentence-transformer embeddings
- **LLM:** Llama 3.2 (3B) via Ollama
- **Frontend:** HTML, CSS, JavaScript

## Project Structure

```
KTUVerse/
├── backend.py              # FastAPI app: auth, chat, RAG, PDF upload/delete
├── chatbot.html             # Main chat interface
├── auth.html                # Login / register / forgot password
├── requirements.txt
├── scripts/
│   ├── ingest.py            # One-time: build the vector store from data/
│   ├── inspect_source.py    # List indexed sources and chunk counts
│   └── dlt.py                # Bulk-delete chunks by filename
└── .gitignore
```

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install and run Ollama**, then pull the model:
   ```bash
   ollama pull llama3.2:3b
   ```

3. **Add source PDFs** to a `data/` folder (KTU scheme documents, syllabus, etc.)

4. **Build the vector store**
   ```bash
   python scripts/ingest.py
   ```

5. **Run the backend**
   ```bash
   python backend.py
   ```
   The API runs on `http://127.0.0.1:8000`.

6. **Open the frontend**
   Open `auth.html` in your browser to log in or register, then continue to `chatbot.html`.

## Maintenance Scripts

- `scripts/ingest.py` — builds the vector store from all PDFs in `data/`. Run once initially, or whenever you want to rebuild from scratch.
- `scripts/inspect_source.py` — prints all currently indexed document sources and how many chunks each contributed. Useful for checking what's in the knowledge base.
- `scripts/dlt.py` — removes specific files from the vector store by filename. Edit the filenames list in the script before running.

These are developer tools for managing the knowledge base directly. The app itself also supports adding and removing documents through the UI (PDF upload button and "Manage Knowledge Base" panel).

## Roadmap

- Previous Year Questions (PYQs) integration
- Important questions / topic-based exam predictions

## Notes

- The vector store, uploaded PDFs, and SQLite database are excluded from version control (see `.gitignore`) since they're generated/user data, not source code.
- Make sure to keep any API keys out of source files — use environment variables instead.