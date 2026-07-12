# structapi — deterministic IS-code structural design API (vendored).
# Source of truth: github.com/karthiknitt/structapi (see VENDORED.md).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY iscodes ./iscodes
COPY structapi ./structapi

ENV MPLBACKEND=Agg PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn structapi.main:app --host 0.0.0.0 --port ${PORT}"]
