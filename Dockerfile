FROM python:3.12-slim

WORKDIR /app

# Install the package with API dependencies.
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e ".[api]"

# Expose the API port.
EXPOSE 8000

# Run the API server.
CMD ["python", "-m", "crucible.cli", "--serve", "0.0.0.0:8000"]
