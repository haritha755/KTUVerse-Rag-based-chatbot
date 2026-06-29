from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

db = Chroma(
    persist_directory="vectorstore",
    embedding_function=embeddings
)

results = db.get()

ids_to_delete = [
    results['ids'][i]
    for i, meta in enumerate(results['metadatas'])
    if meta.get('source') in ['data/dbmsmod1.pdf', 'data/B.Techregulation.pdf','data/B.TechRegulations_2024.pdf','data/2019_scheme.pdf']  # ← put your filenames here
]

db.delete(ids=ids_to_delete)
db.persist()
print(f"Deleted {len(ids_to_delete)} chunks.")