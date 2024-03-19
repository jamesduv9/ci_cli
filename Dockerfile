FROM ubuntu:20.04

# Set the working directory where our commands will run
WORKDIR /e-pipeline

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Update system and install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg \
    curl \
    wget \
    git \
    bash \
    jq \
    unzip \
    ssh \
    telnet \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends python3.10 python3.10-distutils python3.10-venv python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Update alternatives to use python3.10 as the default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 && \
    update-alternatives --set python3 /usr/bin/python3.10

# Copy the current directory contents into the container at /e-pipeline
COPY . /e-pipeline

#get pip
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10


# Install Python library dependencies for our automation
RUN python3 -m pip install --no-cache-dir -r requirements.txt