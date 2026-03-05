#!/bin/bash

# Check if model name is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <model_name>"
    echo "Example: $0 Qwen/Qwen2.5-Coder-7B-Instruct"
    exit 1
fi

# Configuration
MODEL="$1"
PORT=8000
GPU_MEMORY_UTILIZATION=0.8
MAX_MODEL_LEN=32768          # 4096 8192 32768

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
