import os
import re
from openai import OpenAI
from typing import Optional, Tuple

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
        # Step2-1: allow main() to inject a lightweight repo context (existing file list).
        # If not provided, fallback to hints_text.
        injected = task.get("repo_context", "")
        if injected:
            repo_context = injected
        else:
            repo_context = self._get_repo_context(task)
        
        system_prompt = (
            "You are an expert software engineer. You will be given an issue description and a repository context.\n"
            "Your goal is to provide a single unified diff to fix the issue.\n"
            "Constraints:\n"
            "1. Output ONLY the unified diff. Do not include any explanation or markdown formatting (like ```diff).\n"
            "2. Do not modify more than 2 files.\n"
            "3. Keep the changes minimal (under 40 lines if possible).\n"
            "4. Do not introduce new dependencies.\n"
            "5. Ensure the diff header is correct (--- a/file +++ b/file).\n"
            "6. IMPORTANT: Only modify files that actually exist in the repository context list.\n"
            "7. IMPORTANT: Use unified diff format with correct file paths relative to repo root."
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
            
            # NOTE (Step2-2): do NOT drop invalid diffs to empty.
            # We want main_exp1.py to apply a formatter/normalizer 2nd call.
            ok, reason = self._is_valid_unified_diff(cleaned)
            if not ok:
                # Keep a hint for downstream logging/analytics, but preserve raw output.
                # main_exp1.py may choose to formatter-call based on validate_unified_diff().
                task["_gen_warn_reason"] = reason

            # NOTE: empty output is a "model/output" failure, not an infra failure.
            # # main_exp1.py will treat empty string as GEN_FAIL/empty_diff.
            return cleaned
            
        except Exception as e:
            base_url = self.config.get("base_url", "http://localhost:8000/v1")
            msg = f"LLM call failed (provider={self.config.get('provider')}, base_url={base_url}, model={self.model}): {e}"
            raise RuntimeError(msg) from e

    def format_diff(
        self,
        raw_diff: str,
        issue_text: str,
        repo_context: str,
        max_files: int = 2,
    ) -> str:
        """
        Step2-2: Diff formatter/normalizer (2nd call) using the SAME sLM endpoint.
        Goal: preserve intended edits but make output `git apply`-friendly unified diff.
        """
        raw_diff = raw_diff or ""
        system_prompt = (
            "You are a patch formatter.\n"
            "You will receive an issue description, repository context, and a candidate patch.\n"
            "Your ONLY job is to rewrite the candidate into a VALID unified diff that can be applied with `git apply`.\n"
            "Rules:\n"
            f"1. Output ONLY the unified diff (no explanation, no markdown, no ``` fences).\n"
            f"2. Do not change the semantic intent of the patch; keep edits as close as possible.\n"
            f"3. Ensure correct file headers: '--- a/<path>' and '+++ b/<path>'.\n"
            f"4. Ensure at least one hunk header '@@ ... @@' per modified file.\n"
            f"5. Only reference files that exist in the provided repository context.\n"
            f"6. Modify at most {max_files} files.\n"
            "7. Use paths relative to repo root, matching the repository context list.\n"
        )
        user_prompt = (
            f"Issue:\n{issue_text}\n\n"
            f"Repository context:\n{repo_context}\n\n"
            f"Candidate patch (may be invalid):\n{raw_diff}\n\n"
            "Rewrite the candidate into a valid unified diff now."
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=min(int(self.config.get("max_tokens", 4096)), 4096),
            stop=None,
        )
        content = response.choices[0].message.content if response and response.choices else ""
        return self._clean_diff(content or "")

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

    def _is_valid_unified_diff(self, diff_text: str) -> Tuple[bool, str]:
        """
        Minimal unified-diff sanity check to prevent git-apply corrupt patch failures.
        We keep this intentionally lightweight to avoid over-filtering.
        """
        if not diff_text:
            return False, "empty"

        # If any markdown fences remain, treat as invalid.
        if "```" in diff_text:
            return False, "contains_markdown_fence"

        lines = diff_text.splitlines()

        # Must contain --- and +++ headers (either plain or with a/ b/ prefix).
        has_old = any(l.startswith("--- ") for l in lines)
        has_new = any(l.startswith("+++ ") for l in lines)
        if not (has_old and has_new):
            return False, "missing_file_headers"

        # Must contain at least one hunk header @@ ... @@
        # (Some diffs may represent binary changes or file mode only, but those are rare here.)
        has_hunk = any(l.startswith("@@ ") for l in lines)
        if not has_hunk:
            return False, "missing_hunk_header"

        # Quick structural check: after a hunk header, there should be at least one edit line.
        # Edit lines start with ' ', '+', '-', or '\'
        for i, l in enumerate(lines):
            if l.startswith("@@ "):
                # look ahead a small window
                window = lines[i+1:i+40]
                if any(w.startswith((" ", "+", "-", "\\")) for w in window if w.strip() != ""):
                    return True, "ok"
                return False, "hunk_has_no_body"

        return False, "no_hunk_parsed"
