"""
generate_agent의 step2 버전.
- repair prompt 받아서 수정 patch 생성
- exp1/step1의 generate_agent.py와 인터페이스를 맞춰서 재사용 예정
"""
import logging
import time

from openai import OpenAI

logger = logging.getLogger(__name__)


class RepairAgent:
    def __init__(self, model_name: str, config: dict):
        self.model = model_name
        self.config = config

        if config.get("provider") == "vllm":
            logger.info(
                "[RepairAgent] vLLM 서버 연결 base_url=%s",
                config.get("base_url"),
            )

        self.client = OpenAI(
            base_url=config.get("base_url", "http://localhost:8000/v1"),
            api_key=config.get("api_key", "EMPTY"),
            timeout=config.get("timeout", 300),
            max_retries=config.get("max_retries", 0),
        )

        logger.info(
            "[RepairAgent] init model=%s timeout=%s max_retries=%s max_tokens=%s",
            self.model,
            config.get("timeout", 300),
            config.get("max_retries", 0),
            config.get("max_tokens", 4096),
        )

    def generate_repair_patch(self, task: dict, system_prompt: str, user_prompt: str) -> str:
        """
        post-harness semantic repair용 raw 출력을 생성한다.

        역할:
        - 모델 호출
        - raw text 반환
        - 로깅

        주의:
        - markdown fence 제거, diff 추출, unified diff 검증은
          모두 repair/patch_parser.py에서 수행한다.
        """
        task_id = task.get("instance_id", task.get("task_id", "unknown"))
        t0 = time.perf_counter()
        t_req_start = None

        timeout = self.config.get("timeout", 300)
        max_tokens = self.config.get("max_tokens", 4096)
        max_retries = self.config.get("max_retries", 0)
        temperature = self.config.get("temperature", 0.0)

        total_prompt_chars = len(system_prompt or "") + len(user_prompt or "")

        logger.info(
            "[RepairAgent] task=%s prompt_ready total_prompt_chars=%d timeout=%s max_tokens=%s max_retries=%s temperature=%s",
            task_id,
            total_prompt_chars,
            timeout,
            max_tokens,
            max_retries,
            temperature,
        )

        try:
            t_req_start = time.perf_counter()
            logger.info(
                "[RepairAgent] task=%s sending request to model=%s",
                task_id,
                self.model,
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stop=None,
            )

            t_req_end = time.perf_counter()
            content = response.choices[0].message.content if response and response.choices else ""

            logger.info(
                "[RepairAgent] task=%s request_done api_elapsed=%.2fs total_elapsed=%.2fs raw_chars=%d",
                task_id,
                t_req_end - t_req_start,
                t_req_end - t0,
                len(content or ""),
            )

            if not (content or "").strip():
                task["_repair_warn_reason"] = "empty_output"
                logger.warning(
                    "[RepairAgent] task=%s empty raw output from model",
                    task_id,
                )

            return content or ""

        except Exception as e:
            t_err = time.perf_counter()
            base_url = self.config.get("base_url", "http://localhost:8000/v1")
            api_elapsed = (t_err - t_req_start) if t_req_start is not None else -1.0

            logger.exception(
                "[RepairAgent] task=%s request_failed api_elapsed=%.2fs total_elapsed=%.2fs exc_type=%s base_url=%s model=%s",
                task_id,
                api_elapsed,
                t_err - t0,
                type(e).__name__,
                base_url,
                self.model,
            )

            msg = (
                f"semantic repair call failed (provider={self.config.get('provider')}, "
                f"base_url={base_url}, model={self.model}): {e}"
            )
            raise RuntimeError(msg) from e