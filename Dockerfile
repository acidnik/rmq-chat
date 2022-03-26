FROM debian:testing-slim

RUN apt update && apt install -y pip

RUN mkdir /code
COPY pyproject.toml /code

WORKDIR /code

RUN pip3 install poetry
RUN poetry config virtualenvs.create false
RUN poetry install

COPY . /code/

EXPOSE 8000
EXPOSE 8001