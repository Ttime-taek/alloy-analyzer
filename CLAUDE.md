## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review (local UI: `start_all.bat` or `run_api_server.bat`, URL `http://127.0.0.1:8000/`; Windows prep: `scripts/prep_design_review.ps1`)
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health

## 개발 환경

- Python API/엔진 테스트: `py -3 -m pip install -r requirements-dev.txt` 후 `py -3 -m pytest tests -q`
- API 런타임 의존성: `requirements-fastapi.txt`
- **Windows UI 실행:** `start_all.bat` — API+빌드 UI 모두 `http://localhost:8000/` (창 닫기/Ctrl+C = API 종료). `frontend/src`가 `dist`보다 새면 start_all이 자동 `npm run build`
- **테스트:** `py -3 -m pytest tests -q` (HTTP 스모크: `tests/test_api_static.py`)
- 진단: `scripts\diag_stack.ps1`
- API만: `run_api_server.bat`
