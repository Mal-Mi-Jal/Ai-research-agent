from dotenv import load_dotenv
from langchain_tavily import TavilySearch

load_dotenv()

search = TavilySearch(max_results=3)

result = search.invoke("2026년 AI 채용 시장 트렌드")

for r in result["results"]:
    print(r["title"])
    print(r["url"])
    print(r["content"][:150])
    print("---")
