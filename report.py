# report.py

from datetime import datetime
from .utils import normalize_subscript


class ReportBuilder:
    def __init__(self):
        pass

    def header(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return (
            f"1. 작성 시각: {now}\n"
            f"2. 작성 시스템: AI 합금 분석기\n"
            f"3. 프로젝트: 금속 합금 분석 로그\n"
            f"------------------------------------------------------------\n\n"
        )

    def lab_output(self, ai_text):
        return normalize_subscript(self.header() + ai_text)

    def eng_output(self, ai_text):
        return normalize_subscript(self.header() + ai_text)
