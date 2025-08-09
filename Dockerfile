FROM python:3.12.1-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create required directories
RUN mkdir -p data uploads logs

EXPOSE 8000

# Use PORT environment variable if available, otherwise default to 8000
CMD uvicorn app_distribution_server.app:app --host 0.0.0.0 --port ${PORT:-8000}
