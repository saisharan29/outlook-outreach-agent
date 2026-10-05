FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY outreach ./outreach
COPY scripts ./scripts
ENV PORT=8080 HOST=0.0.0.0
EXPOSE 8080
CMD ["python", "-m", "outreach.cli", "serve"]
