from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

llm = ChatAnthropic(model="claude-sonnet-4-5-20250929")

response = llm.invoke("한 문장으로 너 자신을 소개해줘.")
print(response.content)
