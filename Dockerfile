FROM python:3.11

ARG PULUMI_VERSION=3.276.0
RUN curl -fsSL https://get.pulumi.com | sh -s -- --version ${PULUMI_VERSION}
ENV PATH="/root/.pulumi/bin:${PATH}"

WORKDIR /root/synapseformation
COPY . ./
RUN pip install --no-cache-dir .

ENTRYPOINT ["synapseformation"]
