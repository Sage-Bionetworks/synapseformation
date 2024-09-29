FROM python:3.11

WORKDIR /root/synapseformation
COPY . ./
RUN pip install --no-cache-dir .

ENTRYPOINT ["synapseformation"]
