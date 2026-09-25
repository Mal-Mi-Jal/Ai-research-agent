"""memory.py(질문 캐시)와 rag.py(원문 조각 검색)가 공유하는 임베딩 모델.

한 번만 로드해서 메모리를 아끼려고 따로 뺐다. torch를 import하므로
agent.py에서 MEMORY_ENABLED일 때만 (memory/rag를 통해) 불러온다.
"""
from langchain_huggingface import HuggingFaceEmbeddings

# all-MiniLM-L6-v2(영어 전용)는 한국어 문장 의미를 구분하지 못한다:
# "AI 엔지니어 연봉" 질의에 날씨 문장이 0.6, "신입 개발자 채용 트렌드"와
# "반도체 산업 전망"이 0.93으로 나왔다. 다국어 모델은 각각 -0.05, 0.57.
# 최대 128토큰까지만 임베딩한다 (한국어 약 300자) — rag.CHUNK_SIZE가 여기에 맞춰져 있다.
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
