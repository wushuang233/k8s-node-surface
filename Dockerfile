ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HTTP_PROXY= \
    HTTPS_PROXY= \
    ALL_PROXY= \
    http_proxy= \
    https_proxy= \
    all_proxy=

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY main.py /app/main.py
COPY k8s_port_audit /app/k8s_port_audit
COPY config/scanner-config.yaml /app/config/scanner-config.yaml
COPY web /app/web
COPY ziti /app/ziti

ENTRYPOINT ["python", "-m", "k8s_port_audit"]
CMD ["--config", "/app/config/scanner-config.yaml"]
