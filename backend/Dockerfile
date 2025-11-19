FROM python:3.12-slim

RUN apt-get update && apt-get install gcc build-essential wget zip git -y

# Use non-root user
RUN useradd appuser --home-dir /app --create-home
USER appuser
WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY ./app ./app
COPY main.py ./main.py
RUN python -m pip install -U -r requirements.txt
RUN python --version && python -m pip list

EXPOSE 8000

ENTRYPOINT ["python", "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000", "--log-level", "debug"]
