FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY evoagent ./evoagent
COPY diffledger ./diffledger
COPY web ./web
COPY skills ./skills
COPY evaluation_data ./evaluation_data
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --no-deps .
EXPOSE 8080
CMD ["python", "-m", "diffledger"]

