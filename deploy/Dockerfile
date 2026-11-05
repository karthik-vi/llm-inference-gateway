# NOT VERIFIED IN THIS ENVIRONMENT (no usable Docker daemon).
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY gateway gateway
COPY control control
COPY perfmodel perfmodel
COPY workloads workloads
COPY eval eval
COPY bench bench
COPY config.yaml ./
RUN pip install --no-cache-dir -e ".[cache,otel]"
ENV GATEWAY_CONFIG=/app/config.yaml
EXPOSE 8080
CMD ["python", "-m", "gateway.main"]
