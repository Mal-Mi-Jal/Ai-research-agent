FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py memory.py api.py ./

EXPOSE 7860

# MEMORY_ENABLED=false skips importing torch/chromadb (memory.py) at
# runtime - they don't fit in Render's free 512MB instance. Set as a
# Render env var, not here, so local Docker runs can still opt in.
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-7860}"]
