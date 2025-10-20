# services/api/Dockerfile
FROM python:3.12-slim

# Prevent python from writing .pyc files & enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Install Python deps separately to leverage Docker layer caching
COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY services/api ./services/api

# Drop privileges
RUN useradd -u 10001 -m appuser
USER 10001

# Expose & run
EXPOSE 8000
ENV PORT=8000
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
