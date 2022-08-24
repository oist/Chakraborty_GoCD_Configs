FROM python:3.10.6-windowsservercore-1809

LABEL maintainer="Christian Butcher <christian.butcher@oist.jp>"

ENV LISTEN_PORT "80"
EXPOSE 80

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .
#  "--host", "127.0.0.1",
CMD ["waitress-serve", "main:app"]