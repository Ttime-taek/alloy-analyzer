"""
cerebras_melting.py

Cerebras Cloud 기반 고상선/액상선 델타 보정 엔진.
- `hybrid_melting_predict(..., ai_engine=...)`가 요구하는 `get_melting_data(norm)` 인터페이스 제공
- CEREBRAS_API_KEY는 .env(.env.local)에서 로드 가능 (env_loader 사용)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

from .env_loader import load_env_key


def _extract_json_object(text: str) -> dict[str, Any]:
    """
    LLM이 앞뒤로 말을 붙여도, 첫 번째 JSON object를 최대한 복구한다.
    실패 시 {} 반환.
    """
    t = str(text or "").strip()
    if not t:
        return {}
    # direct parse
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    # find {...} block
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return {}
    chunk = m.group(0)
    try:
        obj = json.loads(chunk)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


class CerebrasMeltingDeltaEngine:
    """
    Cerebras chat completions로 delta_solidus/delta_liquidus(°C)를 예측한다.

    Notes
    -----
    - 이 엔진은 "절대 온도"를 직접 예측하지 않는다. 하이브리드 물리 모델 출력에 대한
      작은 델타(보정값)만 제공한다.
    - 출력 델타는 [-12, +12] 범위로 클램프된다.
    """

    def __init__(self, *, model: str = "llama3.1-8b"):
        self.model = model
        self.api_key = load_env_key("CEREBRAS_API_KEY").strip()
        self.available = False
        self._client = None

        if not self.api_key:
            return

        try:
            from cerebras.cloud.sdk import Cerebras  # type: ignore
        except Exception:
            return

        try:
            self._client = Cerebras(api_key=self.api_key)
            self.available = True
        except Exception:
            self._client = None
            self.available = False

    @staticmethod
    def _heuristic_delta(norm: Dict[str, float]) -> Dict[str, float]:
        """
        Cerebras 사용 불가 시 폴백.
        (기존 AIEngine.get_melting_data와 동일 계열의 소규모 휴리스틱)
        """
        Ag = float(norm.get("Ag", 0) or 0.0)
        Cu = float(norm.get("Cu", 0) or 0.0)
        Bi = float(norm.get("Bi", 0) or 0.0)
        In = float(norm.get("In", 0) or 0.0)
        Sb = float(norm.get("Sb", 0) or 0.0)
        Ni = float(norm.get("Ni", 0) or 0.0)

        delta_solidus = 0.0
        delta_liquidus = 0.0

        if Ag > 0:
            delta_liquidus += 2.2 * Ag
            if 2.8 <= Ag <= 3.2 and 0.4 <= Cu <= 0.6:
                delta_solidus -= 2.0
                delta_liquidus -= 3.0
        if Cu > 0:
            delta_liquidus += 12.0 * Cu
            if Cu >= 0.7:
                delta_solidus += 2.0
        if Bi >= 40:
            delta_solidus = 139.0 - 200.0
            delta_liquidus = (139.0 + (Bi - 40.0) * 0.25) - 220.0
        delta_liquidus -= 3.0 * Bi
        delta_liquidus -= 1.5 * In
        if Sb >= 8:
            delta_solidus += 4.0
        if Ni > 0:
            delta_solidus += 0.6 * Ni

        max_correction = 12.0
        delta_liquidus = max(-max_correction, min(max_correction, delta_liquidus))
        delta_solidus = max(-max_correction, min(max_correction, delta_solidus))
        return {"delta_solidus": float(delta_solidus), "delta_liquidus": float(delta_liquidus)}

    @staticmethod
    def _system_prompt() -> str:
        # 요청: 실측값 기반 물리 제약을 시스템 프롬프트에 강제 포함
        return (
            "너는 납땜 합금의 고상선(solidus)/액상선(liquidus) 예측 보정 모델이다.\n"
            "너의 출력은 '기존 물리/상태도/DB 기반 하이브리드 예측'에 더해지는 작은 델타(°C)다.\n"
            "\n"
            "강제 물리 제약(반드시 준수):\n"
            "1) liquidus는 solidus보다 낮아지지 않는다. (delta를 제안하더라도 결과가 역전되게 만들지 마라)\n"
            "2) 델타의 목적은 과대/과소 추정을 0에 가깝게 줄이는 것이다. 과격한 수정(±12°C 초과)을 하지 마라.\n"
            "3) 실측 앵커: Sn-1Ag-25Bi-0.7Cu의 고상선 실측값은 137.81°C다.\n"
            "   이 데이터는 Sn-Bi 계열의 공정 반응 pinning(≈138~139°C)과 정합된다.\n"
            "   Sn-Bi 고Bi 구간에서 고상선을 150°C 이상으로 밀어올리는 보정은 물리적으로 부적절하다.\n"
            "\n"
            "출력은 반드시 JSON object 하나로만 반환한다.\n"
            "형식: {\"delta_solidus\": <float>, \"delta_liquidus\": <float>, \"reason\": \"...\"}\n"
            "reason은 1문장, 한국어로 짧게.\n"
        )

    def get_melting_data(self, norm: Dict[str, float]) -> Dict[str, float]:
        """
        Return dict with keys:
          - delta_solidus
          - delta_liquidus
        """
        if not isinstance(norm, dict) or not norm:
            return {"delta_solidus": 0.0, "delta_liquidus": 0.0}

        if not self.available or self._client is None:
            out = self._heuristic_delta(norm)
            return {"delta_solidus": float(out.get("delta_solidus", 0.0)), "delta_liquidus": float(out.get("delta_liquidus", 0.0))}

        user_prompt = (
            "입력(정규화 wt%):\n"
            f"{norm}\n\n"
            "위 조성의 고상선/액상선에 대해, 하이브리드 예측이 일반적으로 겪는 편향을 고려해\n"
            "작은 델타(°C)를 제안하라.\n"
            "반드시 JSON으로만 출력하라.\n"
        )

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=120,
            )
            # SDK 응답 구조 방어
            txt = ""
            try:
                txt = resp.choices[0].message.content  # type: ignore[attr-defined]
            except Exception:
                txt = str(resp)
        except Exception:
            out = self._heuristic_delta(norm)
            return {"delta_solidus": float(out.get("delta_solidus", 0.0)), "delta_liquidus": float(out.get("delta_liquidus", 0.0))}

        data = _extract_json_object(txt)
        try:
            ds = float(data.get("delta_solidus", 0.0))
        except Exception:
            ds = 0.0
        try:
            dl = float(data.get("delta_liquidus", 0.0))
        except Exception:
            dl = 0.0

        # hard clamp
        ds = max(-12.0, min(12.0, ds))
        dl = max(-12.0, min(12.0, dl))
        return {"delta_solidus": float(ds), "delta_liquidus": float(dl)}

