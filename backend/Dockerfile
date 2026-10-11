FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
CMD ["uvicorn", "serve6:build", "--factory", "--host", "0.0.0.0", "--port", "18770"]
