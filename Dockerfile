FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001
EXPOSE 8002

ENV FRONTEND_AGENT_PORT=8002
ENV FRONTEND_AGENT_HOST=0.0.0.0
ENV LOG_LEVEL=info

CMD ["python", "main.py"]