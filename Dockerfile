FROM python:3.12-slim
WORKDIR /app
COPY app ./app
COPY web ./web
RUN mkdir -p /app/data /app/evidence
ENV HOST=0.0.0.0 PORT=10000 PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["python", "app/server.py", "--no-browser"]
