import sys

from langchain_chroma import Chroma

from embedding import embeddings

# 임베딩 모델을 바꾸면 기존 벡터와 비교할 수 없으므로 컬렉션 이름도 바꾼다.
# (구 "research_reports"는 all-MiniLM-L6-v2 벡터였다)
vectorstore = Chroma(
    collection_name="research_questions_multilingual",
    embedding_function=embeddings,
    persist_directory="./chroma_db",
    collection_metadata={"hnsw:space": "cosine"},
)

# 한국어 질문 쌍으로 측정한 값 기준: 뜻이 같은 질문은 0.75~0.99, 다른 질문은
# 0.37~0.90 ("AI 개발자 채용 트렌드" vs "AI 개발자 연봉 수준"이 0.902).
# 두 분포가 겹쳐서 완벽한 값은 없다. 잘못 히트하면 엉뚱한 리포트를 돌려주지만
# 잘못 미스하면 API를 한 번 더 부를 뿐이라, 다른 질문의 최댓값보다 위로 잡는다.
SIMILARITY_THRESHOLD = 0.92


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
