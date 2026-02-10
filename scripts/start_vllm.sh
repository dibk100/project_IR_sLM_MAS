#!/bin/bash

# Configuration
MODEL="Qwen/Qwen2.5-Coder-7B-Instruct"
PORT=8000
GPU_MEMORY_UTILIZATION=0.9
MAX_MODEL_LEN=4096          # 8192

echo "Starting vLLM server with model: $MODEL"
echo "Port: $PORT"

# Run vLLM
/home/dibaeck/miniconda3/envs/amla/bin/python3 -m vllm.entrypoints.openai.api_server \
    --model $MODEL \
    --port $PORT \
    --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
    --max-model-len $MAX_MODEL_LEN \
    --dtype float16 \              
    --disable-log-requests \
    --trust-remote-code
