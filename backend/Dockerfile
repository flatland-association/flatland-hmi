FROM continuumio/miniconda3

RUN apt-get update && apt-get install gcc build-essential wget zip -y

# Use non-root user
RUN useradd conda --home-dir /home/conda --create-home
RUN chown -R conda /opt/conda
USER conda
WORKDIR /home/conda

COPY requirements.txt ./requirements.txt
COPY ./app ./app
COPY main.py ./main.py
RUN python --version && python -m pip install -r requirements.txt && python --version && python -m pip list

EXPOSE 8000

ENTRYPOINT ["uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000", "--log-level", "debug"]
