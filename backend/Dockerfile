FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
