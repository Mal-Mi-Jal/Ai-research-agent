import sys

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

vectorstore = Chroma(
    collection_name="research_reports",
    embedding_function=embeddings,
    persist_directory="./chroma_db",
    collection_metadata={"hnsw:space": "cosine"},
)

SIMILARITY_THRESHOLD = 0.85


def find_similar_report(question: str) -> str | None:
    results = vectorstore.similarity_search_with_relevance_scores(question, k=1)
    if not results:
        return None

    doc, score = results[0]
    print(f"[memory] 가장 비슷한 과거 질문과의 유사도: {score:.3f}", file=sys.stderr)
    if score < SIMILARITY_THRESHOLD:
        return None
    return doc.metadata["report"]


def save_report(question: str, report: str) -> None:
    vectorstore.add_texts(texts=[question], metadatas=[{"report": report}])
