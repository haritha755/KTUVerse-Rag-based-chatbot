from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
import google.generativeai as genai
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

genai.configure(api_key="YOUR_GEMINI_API_KEY")

model = genai.GenerativeModel("gemini-2.5-flash")

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

db = Chroma(
    persist_directory="vectorstore",
    embedding_function=embeddings
)

st.title("RAG Chatbot")

question = st.text_input("Ask a question")

if question:
    docs = db.similarity_search(question, k=3)

    context = "\n".join([doc.page_content for doc in docs])

    prompt = f"""
    Answer only using the provided context.

    Context:
    {context}

    Question:
    {question}
    """

    response = model.generate_content(prompt)

    st.write(response.text)