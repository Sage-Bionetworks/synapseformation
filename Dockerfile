FROM python:3.9-slim-buster

WORKDIR /root/synapseformation
COPY . ./
RUN pip install --no-cache-dir .

ENTRYPOINT ["synapseformation"]
