from openai import OpenAI
import sys

def check_vllm():
    client = OpenAI(
        base_url="http://localhost:8000/v1",
        api_key="EMPTY"
    )
    try:
        models = client.models.list()
        print("Successfully connected to vLLM!")
        print("Available models:", [m.id for m in models.data])
        return 0
    except Exception as e:
        print(f"Failed to connect to vLLM: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_vllm())
