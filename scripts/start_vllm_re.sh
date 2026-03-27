#!/bin/bash

# Configuration
MODEL=/mnt/hdd/hf_cache/models--mistralai--Mistral-7B-Instruct-v0.3/snapshots/c170c708c41dac9275d15a8fff4eca08d52bab71
# MODEL=/mnt/hdd/models/llama3.1_8b_instruct
PORT=8000
GPU_MEMORY_UTILIZATION=0.8
MAX_MODEL_LEN=4096          # 8192

echo "Starting vLLM server with model: $MODEL"
echo "Port: $PORT"

PYTHON="$(command -v python)"
echo "Using python: $PYTHON"

# Run vLLM
"$PYTHON" -m vllm.entrypoints.openai.api_server \
    --model $MODEL \
    --port $PORT \
    --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
    --max-model-len $MAX_MODEL_LEN \
    --dtype float16 \
     --disable-log-requests \
    --trust-remote-code
