ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY main.py /app/main.py
COPY k8s_port_audit /app/k8s_port_audit
COPY config/scanner-config.yaml /app/config/scanner-config.yaml
COPY web /app/web
COPY ziti /app/ziti

ENTRYPOINT ["python", "-m", "k8s_port_audit"]
CMD ["--config", "/app/config/scanner-config.yaml"]
