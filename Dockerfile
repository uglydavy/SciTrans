FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY scitrans/ ./scitrans/
COPY README.md ./

# Install SciTrans
RUN pip install --no-cache-dir -e ".[all]"

# Create directories
RUN mkdir -p /app/outputs /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV SCITRANS_OUTPUT_DIR=/app/outputs

# Expose GUI port
EXPOSE 7860

# Default command
CMD ["scitrans", "gui", "--port", "7860"]

