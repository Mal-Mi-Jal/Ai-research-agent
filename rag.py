"""검색 원문을 조각(chunk)으로 잘라 임베딩하고, 소제목별로 관련 조각을 찾아오는 RAG 모듈.

memory.py처럼 torch를 import하므로 agent.py에서 MEMORY_ENABLED일 때만 불러온다.
"""
import sys
import uuid

from langchain_chroma import Chroma

from embedding import embeddings

# 임베딩 모델은 최대 128토큰까지만 임베딩하고 나머지는 잘라버린다. 한국어 300자 ≈ 128토큰.
CHUNK_SIZE = 300
CHUNK_OVERLAP = 50
# 원문이 수만 자인 페이지도 있어서, 임베딩 시간을 제한하려고 출처당 앞부분만 쓴다
MAX_CHARS_PER_SOURCE = 10000


def split_text(text: str) -> list[str]:
    """CHUNK_SIZE 글자 단위로 자르되, 단어 중간이 아니라 공백에서 끊고,
    조각 경계에 걸친 문장을 잃지 않도록 CHUNK_OVERLAP만큼 겹치게 한다."""
    text = " ".join(text.split())
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + CHUNK_SIZE // 2, end)
            if cut != -1:
                end = cut
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def retrieve_evidence(sources: list[dict], queries: list[str], k: int = 4) -> list[list[dict]]:
    """sources(Tavily 결과)를 이번 실행 전용 벡터DB에 넣고, 각 query마다
    가장 비슷한 조각 k개를 {"source": 출처 번호, "text": 조각} 형태로 돌려준다."""
    texts, metadatas = [], []
    for i, r in enumerate(sources):
        body = (r.get("raw_content") or r["content"])[:MAX_CHARS_PER_SOURCE]
        for chunk in split_text(body):
            texts.append(chunk)
            metadatas.append({"source": i + 1})
    if not texts:
        return [[] for _ in queries]

    # 질문 캐시(./chroma_db)와 섞이지 않게, 디스크에 저장하지 않는 임시 컬렉션을 쓴다
    store = Chroma(
        collection_name=f"run-{uuid.uuid4().hex}",
        embedding_function=embeddings,
        collection_metadata={"hnsw:space": "cosine"},
    )
    try:
        store.add_texts(texts=texts, metadatas=metadatas)
        print(f"[rag] 출처 {len(sources)}개 → 조각 {len(texts)}개 임베딩", file=sys.stderr)
        # 단순 유사도 top-k는 한 출처의 비슷한 조각만 연달아 뽑는 경향이 있어서,
        # MMR로 관련성은 유지하되 이미 고른 조각과 겹치지 않는 조각을 우선한다
        return [
            [
                {"source": doc.metadata["source"], "text": doc.page_content}
                for doc in store.max_marginal_relevance_search(query, k=k, fetch_k=20)
            ]
            for query in queries
        ]
    finally:
        store.delete_collection()
