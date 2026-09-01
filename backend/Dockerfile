FROM python:3.11-slim

WORKDIR /app

# System dependencies for psycopg
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy root requirements (if any) and backend requirements
COPY requirements.txt /app/requirements.txt
COPY backend/requirements.txt /app/backend/requirements.txt

# Install both
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy only the backend and modules (needed for API)
COPY backend/ /app/backend/
COPY modules/ /app/modules/

# Set PYTHONPATH so modules can be imported
ENV PYTHONPATH=/app

# Switch to backend dir
WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]