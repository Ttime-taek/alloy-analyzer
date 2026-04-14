# main.py

import os
from pathlib import Path


def _ensure_gemini_key_from_file() -> None:
    """GEMINI_API_KEY가 없으면 test7 폴더의 .gemini_api_key(주석 줄 제외 첫 줄)를 환경변수에 넣는다."""
    if (os.getenv("GEMINI_API_KEY") or "").strip():
        return
    root = Path(__file__).resolve().parent
    for name in (".gemini_api_key", "gemini_api_key.txt"):
        path = root / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            key = line.strip()
            if not key or key.startswith("#"):
                continue
            os.environ["GEMINI_API_KEY"] = key
            return


_ensure_gemini_key_from_file()

# Support both:
# - package run:   python -m test7.main
# - direct run:    python test7/main.py
if __package__ in (None, ""):
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from test7.gui import AlloyGUI
else:
    from .gui import AlloyGUI

if __name__ == "__main__":
    try:
        app = AlloyGUI(api_key=os.getenv("GEMINI_API_KEY", ""))
        app.run()
    except Exception as e:
        try:
            if __package__ in (None, ""):
                from test7.utils import save_error
            else:
                from .utils import save_error
            save_error(e)
        except Exception:
            pass
        raise

