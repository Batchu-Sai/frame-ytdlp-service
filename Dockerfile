FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir yt-dlp fastapi uvicorn

WORKDIR /app
COPY main.py .

CMD ["python", "main.py"]
