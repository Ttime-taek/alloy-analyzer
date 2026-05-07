# phase.py
"""
간단한 Phase Diagram 기반 상변태 및 융점 경향 예측 엔진
- Sn을 기반으로 한 대표 2원/3원계 경향 반영
- 정확한 CALPHAD 수준은 아니지만 보고서용 트렌드 출력을 목표로 함
"""

try:
    from .melting_predictor import _classify as _melting_classify_family
except ImportError:
    from test7.melting_predictor import _classify as _melting_classify_family


class PhasePredictor:
    def __init__(self):
        pass

    # -------------------------------------------------------------------
    # 상변태 추론 로직
    # -------------------------------------------------------------------
    def predict(self, norm):
        txt = []

        # ------------------------------
        # Sn Base Majority
        # ------------------------------
        if norm.get("Sn", 0) >= 40:
            txt.append("본 합금은 Sn 기반 합금으로 판단되며, β-Sn 매트릭스를 중심으로 상변태가 진행됨.")

        # ------------------------------
        # Sn–Ag Binary 경향
        # ------------------------------
        if "Sn" in norm and "Ag" in norm:
            if norm["Ag"] >= 2:
                txt.append(
                    "Sn–Ag 계 특성이 강함: Ag₃Sn IMC가 공정 중 초기에 석출되며, "
                    "냉각이 빠를 경우 판상(plate) Ag₃Sn이 늘어 박리 위험이 있을 수 있음."
                )
            else:
                txt.append("Ag 함량이 낮아 Ag₃Sn IMC의 영향은 제한적임.")

        # ------------------------------
        # Sn–Cu Binary 경향
        # ------------------------------
        if "Sn" in norm and "Cu" in norm:
            if norm["Cu"] >= 0.7:
                txt.append(
                    "Sn–Cu 계: Cu₆Sn₅(η상) IMC 형성이 주요 상변태이며, "
                    "고온·장시간 노출 시 Cu₃Sn으로 성장해 전기이동(EM) 신뢰성에 영향을 줄 수 있음."
                )
            else:
                txt.append("Cu 함량이 낮아 Cu₆Sn₅ 형성량은 제한적임.")

        # ------------------------------
        # Sn–Bi Binary 경향
        # ------------------------------
        if "Bi" in norm:
            if norm["Bi"] >= 5:
                txt.append(
                    "Sn–Bi 계 영향: Bi 첨가로 고상선이 큰 폭으로 낮아지며, "
                    "고상선–액상선 간격이 좁아지는 경향이 있음. "
                    "취성 증가에 유의."
                )
            else:
                txt.append("Bi 함량이 낮아 융점 저하 효과는 제한적임.")

        # ------------------------------
        # Sn–Sb Binary
        # ------------------------------
        if "Sb" in norm:
            if norm["Sb"] >= 5:
                txt.append(
                    "Sb 첨가로 β-Sn의 격자 경화(lattice hardening)가 강해져 "
                    "고온 강도는 오르지만 취성도 함께 증가하는 경향이 있음."
                )
            else:
                txt.append("Sb 함량이 낮아 고온 강도 향상 효과는 제한적임.")

        # ------------------------------
        # Sn–Ag–Cu SAC 삼원계 (melting_predictor._classify 의 SAC 분기와 동일 조건)
        #   Sn>80, Ag>0, Cu>0, Bi≤5, In≤8 — 키 존재 여부만으로 SAC 서술 금지.
        # ------------------------------
        if _melting_classify_family(norm) == "SAC":
            txt.append(
                "Sn–Ag–Cu 삼원계(SAC) 특성 보유: Ag₃Sn과 Cu₆Sn₅가 공존하며, "
                "냉각 속도에 따라 미세조직 조절 가능. "
                "범용 고신뢰성 솔더 계열과 유사한 미세조직·상 구성으로 볼 수 있음."
            )

        # ------------------------------
        # 결과 정리
        # ------------------------------
        if not txt:
            return "특징적인 상변태 경향을 특정하기 어려움."

        return "\n- ".join([""] + txt)


# -------------------------------------------------------------------
# analyzer.py에서 요구하는 analyze_phase 함수 (★ 새로 추가)
# -------------------------------------------------------------------
def analyze_phase(comp, solidus, liquidus):
    """
    analyzer.py가 필요로 하는 외부 함수.
    내부적으로 PhasePredictor를 실행해 문자열 형태로 phase 분석 리턴.
    """
    norm = {}

    # 조성 비율 환산 (normalize 없이 단순 비율)
    total = sum(comp.values()) if comp else 1
    for k, v in comp.items():
        norm[k] = (v / total) * 100

    predictor = PhasePredictor()
    txt = predictor.predict(norm)

    # 출력 형식 유지
    return f"[Phase 분석]\n{txt}"
