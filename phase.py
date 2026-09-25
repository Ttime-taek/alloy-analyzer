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
    def predict(self, norm, solidus=None, liquidus=None):
        # [2026-09-25 계산 로직 점검 P3] 서술이 계산 결과와 모순되던 문구 수정
        #   - "Bi 첨가로 고상선–액상선 간격이 좁아짐": Bi 5~40 %에서는 오히려 넓어진다(Sn80Bi20 = 139/199 ℃).
        #     좁아지는 건 공정(Bi 약 57~58 %) 부근뿐.
        #   - "Ag ≥ 2 %면 Ag₃Sn이 초기에 석출, 판상": 초정 판상 Ag₃Sn은 과공정(Ag > 3.5 %) 문제.
        #   - Pb·In·Zn 계열 서술이 없었음. 고상·액상을 받으면 실제 응고 구간도 함께 적는다.
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
            if norm["Ag"] > 3.5:
                txt.append(
                    "Sn–Ag 과공정(Ag > 3.5 %): Ag₃Sn이 초정으로 먼저 석출해 판상(plate)으로 크게 "
                    "자랄 수 있음. 냉각이 느리면 판상 Ag₃Sn이 커져 취성·박리 위험이 있음."
                )
            elif norm["Ag"] >= 2:
                txt.append(
                    "Sn–Ag 계 특성이 강함: Ag₃Sn IMC가 공정 조직 안에 미세하게 분산되어 "
                    "강도·크리프 저항을 높임."
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
            bi = float(norm["Bi"])
            if 50.0 <= bi <= 62.0:
                txt.append(
                    "Sn–Bi 공정(Bi 약 57~58 %, 139 ℃) 부근: 고상선–액상선 간격이 좁고 "
                    "한 온도에서 녹는 공정 거동에 가까움. Bi 상이 많아 취성 증가에 유의."
                )
            elif bi >= 5:
                txt.append(
                    "Sn–Bi 계 영향: Bi 첨가로 고상선이 크게 낮아지며(Bi 약 21 % 이상이면 139 ℃ 공정 반응), "
                    "공정 조성(Bi 약 57 %)에서 멀수록 고상선–액상선 간격이 넓어짐. 취성 증가에 유의."
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
        # Sn–Pb / Sn–In / Sn–Zn
        # ------------------------------
        if norm.get("Pb", 0) >= 1:
            txt.append(
                "Sn–Pb 계: Sn63Pb37 공정(183 ℃). 유연(有鉛) 솔더라 RoHS 등 무연 규제 적용 여부 확인 필요."
            )
            if norm.get("Bi", 0) >= 1:
                txt.append(
                    "Pb와 Bi가 함께 있어 Sn–Pb–Bi 3원 공정(약 96 ℃) 상이 생길 수 있음 — "
                    "SnBi 솔더와 SnPb 도금 부품을 섞을 때처럼 저온에서 부분 용융·접합부 약화 위험."
                )
        if norm.get("In", 0) >= 1:
            txt.append(
                "In 첨가로 융점이 낮아짐(In–Sn 공정 약 118 ℃). In이 많으면 저온에서도 크리프·강도 저하에 유의."
            )
        if norm.get("Zn", 0) >= 1:
            txt.append(
                "Sn–Zn 계: Sn91Zn9 공정(약 198 ℃). Zn은 산화되기 쉬워 젖음성이 떨어지므로 "
                "플럭스·분위기 관리가 필요함."
            )

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
        # 계산된 응고 구간
        # ------------------------------
        try:
            if solidus is not None and liquidus is not None:
                dt = float(liquidus) - float(solidus)
                if dt >= 0:
                    note = (
                        "간격이 넓어 응고 중 편석·필렛 들뜸(fillet lifting) 위험이 커질 수 있음."
                        if dt >= 30
                        else "간격이 좁아 공정에 가까운 용융 거동."
                        if dt < 5
                        else "중간 정도의 응고 구간."
                    )
                    txt.append(
                        f"예측 고상선–액상선 간격: {dt:.1f} ℃ ({float(solidus):.1f}→{float(liquidus):.1f} ℃). {note}"
                    )
        except (TypeError, ValueError):
            pass

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
    txt = predictor.predict(norm, solidus=solidus, liquidus=liquidus)

    # 출력 형식 유지
    return f"[Phase 분석]\n{txt}"
