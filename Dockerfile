FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN pip install --no-cache-dir '.[server,postgres]' && \
    useradd -u 10001 -m -s /usr/sbin/nologin agentflow && \
    mkdir /data && chown 10001:10001 /data
USER 10001:10001
ENV PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["agentflow", "serve"]
