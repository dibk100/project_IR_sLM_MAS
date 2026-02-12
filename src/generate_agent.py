import os
import re
from openai import OpenAI
from typing import Optional

class GenerateAgent:
    def __init__(self, model_name: str, config: dict):
        self.model = model_name
        self.config = config
        
        # Check provider to ensure we are using vLLM as requested
        if config.get("provider") == "vllm":
            print(f"[GenerateAgent] Connecting to vLLM server at {config.get('base_url')}...")
            
        # vLLM is OpenAI-compatible, so we use the standard OpenAI client
        self.client = OpenAI(
            base_url=config.get("base_url", "http://localhost:8000/v1"),
            api_key=config.get("api_key", "EMPTY")
        )
        
    def generate(self, task: dict) -> str:
        """
        Generates a unified diff for the given task using the configured LLM.
        """
        issue_text = task.get("problem_statement", "")
        repo_context = self._get_repo_context(task) # Placeholder or simple context
        
        system_prompt = (
            "You are an expert software engineer. You will be given an issue description and a repository context.\n"
            "Your goal is to provide a single unified diff to fix the issue.\n"
            "Constraints:\n"
            "1. Output ONLY the unified diff. Do not include any explanation or markdown formatting (like ```diff).\n"
            "2. Do not modify more than 2 files.\n"
            "3. Keep the changes minimal (under 40 lines if possible).\n"
            "4. Do not introduce new dependencies.\n"
            "5. Ensure the diff header is correct (--- a/file +++ b/file)."
        )
        
        user_prompt = f"Issue:\n{issue_text}\n\nContext:\n{repo_context}\n\nGenerate the unified diff now."
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.config.get("temperature", 0.0),
                max_tokens=self.config.get("max_tokens", 4096),
                stop=None
            )
            content = response.choices[0].message.content if response and response.choices else ""
            cleaned = self._clean_diff(content or "")

            # NOTE: empty output is a "model/output" failure, not an infra failure.
            # # main_exp1.py will treat empty string as GEN_FAIL/empty_diff.
            return cleaned
            
        except Exception as e:
            base_url = self.config.get("base_url", "http://localhost:8000/v1")
            msg = f"LLM call failed (provider={self.config.get('provider')}, base_url={base_url}, model={self.model}): {e}"
            raise RuntimeError(msg) from e
            

    def _get_repo_context(self, task: dict) -> str:
        # For Exp1, we might just use the filenames mentioned in the issue or hints if available.
        # Or just return a generic listing if we don't have better context retrieval yet.
        hints = task.get("hints_text", "")
        return f"Structure hint: {hints}" if hints else "No specific context provided."

    def _clean_diff(self, content: str) -> str:
        # Remove markdown code blocks if present
        content = re.sub(r'^```diff\s*', '', content)
        content = re.sub(r'^```\s*', '', content)
        content = re.sub(r'```$', '', content)
        return content.strip()
