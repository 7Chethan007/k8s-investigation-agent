FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY k8s_agent/ ./k8s_agent/
COPY main.py ./
COPY samples/ ./samples/

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["k8s-investigate"]
CMD ["analyze", "samples/crashloop_db_exhaustion.log"]
