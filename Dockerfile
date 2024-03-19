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
    python3 \
    python3-pip \
    bash \
    jq \
    unzip \
    ssh \
    telnet \
    && rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container at /e-pipeline
COPY . /e-pipeline

# Install Python library dependencies for our automation
RUN python3 -m pip install --no-cache-dir -r requirements.txt

