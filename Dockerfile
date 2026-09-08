# Root Dockerfile so hosts that build from the repo root (Render "Web Service" without a root directory) get the backend API.
# Equivalent to backend/Dockerfile; the frontend is deployed separately (Vercel).
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
RUN chmod +x docker-entrypoint.sh
EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
