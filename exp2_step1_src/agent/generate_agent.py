import json
import logging
import re
import time

from openai import OpenAI

logger = logging.getLogger(__name__)


class GenerateAgent:
    def __init__(self, model_name: str, config: dict):
        self.model = model_name
        self.config = config

        if config.get("provider") == "vllm":
            logger.info(
                "[GenerateAgent] Connecting to vLLM server at %s",
                config.get("base_url"),
            )

        self.client = OpenAI(
            base_url=config.get("base_url", "http://localhost:8000/v1"),
            api_key=config.get("api_key", "EMPTY"),
            timeout=config.get("timeout", 300),
            max_retries=config.get("max_retries", 0),
        )

        logger.info(
            "[GenerateAgent] init model=%s timeout=%s max_retries=%s max_tokens=%s",
            self.model,
            config.get("timeout", 300),
            config.get("max_retries", 0),
            config.get("max_tokens", 4096),
        )

    def generate_edits(self, task: dict, max_files: int = 2, max_edits: int = 6) -> str:
        """
        Generate a strict JSON edit script.

        Expected schema:
        {
          "edits": [
            {"op":"replace_range","path":"...","start_line":1,"end_line":2,"text":"..."},
            {"op":"insert_after","path":"...","line":10,"text":"..."}
          ]
        }

        Notes:
        - Output must be JSON only.
        - Final structural validation is still performed downstream by DiffMaterializer.
        - Here we do lightweight sanity checks for logging/debugging only.
        """
        task_id = task.get("instance_id", task.get("task_id", "unknown"))
        t0 = time.perf_counter()
        t_req_start = None

        issue_text = task.get("problem_statement", "")
        injected = task.get("repo_context", "")
        repo_context = injected if injected else self._get_repo_context(task)

        system_prompt = (
            "You are an expert software engineer.\n"
            "You will be given an issue description and a repository context listing existing files.\n"
            "Your task is to output a STRICT JSON edit script to fix the issue.\n\n"
            "Output rules (MUST follow):\n"
            "1) Output ONLY valid JSON. No markdown fences. No explanation. No extra text.\n"
            "2) The JSON must be an object with a single key: \"edits\" (a non-empty list).\n"
            "3) Each edit must be one of:\n"
            "   - replace_range: {\"op\":\"replace_range\",\"path\":str,\"start_line\":int,\"end_line\":int,\"text\":str}\n"
            "   - insert_after:  {\"op\":\"insert_after\",\"path\":str,\"line\":int,\"text\":str}\n"
            f"4) Modify at most {max_files} files total.\n"
            f"5) Keep edits minimal; prefer a small number of edits (<= {max_edits}).\n"
            "6) IMPORTANT: \"path\" must match an existing file path from the repository context list (repo root relative).\n"
            "7) Use 1-indexed line numbers.\n"
        )

        user_prompt = (
            f"Issue:\n{issue_text}\n\n"
            f"Repository context (existing files):\n{repo_context}\n\n"
            "Now output the JSON edit script."
        )

        timeout = self.config.get("timeout", 300)
        max_tokens = self.config.get("max_tokens", 4096)
        max_retries = self.config.get("max_retries", 0)

        repo_ctx_lines = [x for x in str(repo_context).splitlines() if x.strip()]
        total_prompt_chars = len(system_prompt) + len(user_prompt)

        logger.info(
            "[GenerateAgent] task=%s prompt_ready issue_chars=%d repo_ctx_chars=%d repo_ctx_lines=%d total_prompt_chars=%d timeout=%s max_tokens=%s max_retries=%s",
            task_id,
            len(issue_text),
            len(str(repo_context)),
            len(repo_ctx_lines),
            total_prompt_chars,
            timeout,
            max_tokens,
            max_retries,
        )

        try:
            t_req_start = time.perf_counter()
            logger.info(
                "[GenerateAgent] task=%s sending request to model=%s",
                task_id,
                self.model,
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.get("temperature", 0.0),
                max_tokens=max_tokens,
                stop=None,
            )

            t_req_end = time.perf_counter()
            content = response.choices[0].message.content if response and response.choices else ""
            cleaned = self._clean_json(content or "")

            logger.info(
                "[GenerateAgent] task=%s request_done api_elapsed=%.2fs total_elapsed=%.2fs raw_chars=%d cleaned_chars=%d",
                task_id,
                t_req_end - t_req_start,
                t_req_end - t0,
                len(content or ""),
                len(cleaned),
            )

            self._annotate_generation_warning(task, cleaned, max_files=max_files, max_edits=max_edits)

            if not cleaned.startswith("{"):
                logger.warning(
                    "[GenerateAgent] task=%s cleaned output is not a JSON object",
                    task_id,
                )

            return cleaned

        except Exception as e:
            t_err = time.perf_counter()
            base_url = self.config.get("base_url", "http://localhost:8000/v1")
            api_elapsed = (t_err - t_req_start) if t_req_start is not None else -1.0

            logger.exception(
                "[GenerateAgent] task=%s request_failed api_elapsed=%.2fs total_elapsed=%.2fs exc_type=%s base_url=%s model=%s",
                task_id,
                api_elapsed,
                t_err - t0,
                type(e).__name__,
                base_url,
                self.model,
            )

            msg = (
                f"sLM call failed (provider={self.config.get('provider')}, "
                f"base_url={base_url}, model={self.model}): {e}"
            )
            raise RuntimeError(msg) from e

    def _get_repo_context(self, task: dict) -> str:
        hints = task.get("hints_text", "")
        return f"Structure hint: {hints}" if hints else "No specific context provided."

    def _clean_json(self, content: str) -> str:
        """
        Remove markdown fences and attempt minimal cleanup without modifying JSON structure.
        """
        if not content:
            return ""

        content = content.strip()
        content = re.sub(r"^```json\s*", "", content)
        content = re.sub(r"^```\s*", "", content)
        content = re.sub(r"```$", "", content)

        cleaned = content.strip()

        # Fallback: extract the first {...} block if extra text exists.
        m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if m:
            return m.group(0).strip()

        return cleaned

    def _annotate_generation_warning(
        self,
        task: dict,
        cleaned: str,
        max_files: int,
        max_edits: int,
    ) -> None:
        """
        Lightweight sanity checks for logging/debugging only.
        This does NOT replace downstream validation in DiffMaterializer.
        """
        if not cleaned:
            task["_gen_warn_reason"] = "empty_output"
            return

        try:
            obj = json.loads(cleaned)
        except Exception:
            task["_gen_warn_reason"] = "invalid_json_after_clean"
            return

        if not isinstance(obj, dict):
            task["_gen_warn_reason"] = "json_root_not_object"
            return

        edits = obj.get("edits")
        if not isinstance(edits, list) or not edits:
            task["_gen_warn_reason"] = "missing_or_empty_edits"
            return

        if len(edits) > max_edits:
            task["_gen_warn_reason"] = f"too_many_edits({len(edits)})"
            return

        file_set = set()
        for edit in edits:
            if not isinstance(edit, dict):
                task["_gen_warn_reason"] = "edit_not_object"
                return

            path = edit.get("path")
            if isinstance(path, str) and path.strip():
                file_set.add(path)
            else:
                task["_gen_warn_reason"] = "bad_or_missing_path"
                return

        if len(file_set) > max_files:
            task["_gen_warn_reason"] = f"too_many_files({len(file_set)})"
            return