"""
cerebras_chat.py

Cerebras Cloud 기반 '일반 텍스트' 추론 클라이언트.
AIEngine(Gemini)가 쿼터(429)/연결 오류일 때 `ask()` 호출을 그대로 넘겨받는 용도.

- CEREBRAS_API_KEY는 .env(.env.local)에서 로드 (env_loader)
- SDK 미설치 또는 키 없음이면 `available=False` → 상위가 기존 폴백 메시지 유지

실측 물리 제약은 Melting 보정과 동일한 원칙만 '기본 system prompt'에 강하게 박아 둔다.
"""

from __future__ import annotations

from typing import Any

try:
    from .env_loader import load_env_key  # when imported as package (test7.cerebras_chat)
except Exception:  # pragma: no cover - direct-run fallback
    from env_loader import load_env_key  # type: ignore


_SYSTEM_PROMPT = (
    "너는 납땜·솔더 합금 분석 도우미다. 답변은 한국어로 간결하게 쓴다.\n"
    "\n"
    "강제 물리 제약(어기지 마라):\n"
    "1) liquidus < solidus 로 읽히는 설명을 하지 마라.\n"
    "2) 실측 앵커: Sn-1Ag-25Bi-0.7Cu 의 고상선은 137.81°C 이다.\n"
    "   Sn-Bi 고Bi 구간의 고상선을 이 앵커(≈138~139°C)에서 크게 벗어나게 '상향' 서술하지 마라.\n"
    "3) 숫자를 지어내지 마라. 특정 수치를 쓸 때는 '근사/추정' 라벨을 붙여라.\n"
    "\n"
    "사용자가 list를 요구(JSON [\"a\", \"b\", ...])하면 JSON 배열 한 개로만 답한다.\n"
)


class CerebrasChatEngine:
    """Minimal Cerebras chat completion wrapper used as an AIEngine fallback."""

    def __init__(self, *, model: str = "llama3.1-8b") -> None:
        self.model = model
        self.api_key = load_env_key("CEREBRAS_API_KEY").strip()
        self.available = False
        self._client = None
        self.last_error = ""

        if not self.api_key:
            self.last_error = "CEREBRAS_API_KEY 없음"
            return

        try:
            from cerebras.cloud.sdk import Cerebras  # type: ignore
        except Exception as e:
            self.last_error = f"cerebras SDK 미설치/로드 실패: {e}"
            return

        try:
            self._client = Cerebras(api_key=self.api_key)
            self.available = True
        except Exception as e:
            self._client = None
            self.available = False
            self.last_error = f"Cerebras 초기화 실패: {e}"

    def ask(self, prompt: str, *, max_tokens: int = 600, temperature: float = 0.2) -> str:
        """
        Return plain text from Cerebras chat completion.
        On failure, returns an empty string so the caller can keep its own fallback path.
        """
        if not self.available or self._client is None:
            return ""

        try:
            resp: Any = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": str(prompt or "")},
                ],
                temperature=float(temperature),
                max_tokens=int(max_tokens),
            )
            try:
                return resp.choices[0].message.content  # type: ignore[attr-defined]
            except Exception:
                return str(resp)
        except Exception as e:
            self.last_error = str(e)
            return ""
