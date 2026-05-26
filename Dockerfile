# ESG Carbon Analytics Dashboard
# Multi-stage build optimized for production

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required by Prophet and pyarrow
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching optimization
COPY esg_dashboard/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY esg_dashboard/ .

# Create cache directory
RUN mkdir -p cache

# Set Python environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBUG=False

# Expose port
EXPOSE 8050

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8050 || exit 1

# Run the application
CMD ["python", "app.py"]
