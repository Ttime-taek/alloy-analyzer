# Regression: 2026-09-25 계산 로직 점검 — DB 범위 밖(out_of_domain) 판정에도 계열의 도메인 내
# 홀드아웃 잔차로 만든 90 % 범위가 붙었다. Sn43Pb43Bi14는 Pb 계열 잔차 ±0.3 ℃가 붙어
# "182.7–183.3 ℃"로 표시됐지만 실측(144 ℃)과 39 ℃ 차이였다.
# Found by 계산 로직 점검 (Claude) on 2026-09-25
from __future__ import annotations

from fastapi.testclient import TestClient

from test7.api_server import app


def test_out_of_domain_prediction_has_no_empirical_interval() -> None:
    client = TestClient(app)
    response = client.post("/api/analyze", json={"comp": {"Sn": 43, "Pb": 43, "Bi": 14}})
    assert response.status_code == 200, response.text
    props = response.json()["prediction_contract"]["properties"]
    for key in ("solidus_c", "liquidus_c"):
        assert props[key]["state"] == "out_of_domain"
        assert props[key]["interval"] is None
