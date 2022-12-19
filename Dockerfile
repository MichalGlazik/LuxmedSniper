FROM alpine:3.17.0
WORKDIR /usr/src/app
COPY . .
RUN apk add --no-cache python3 py3-pip
RUN pip install --upgrade pip setuptools==57.5.0
RUN pip install -r /usr/src/app/requirements.txt
ENTRYPOINT ["python", "/usr/src/app/luxmedSnip.py"]
