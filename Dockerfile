FROM python:3.8.6-slim-buster

WORKDIR /root/synapseformation
COPY . ./
RUN pip install --no-cache-dir .

ENTRYPOINT ["synapseformation"]
