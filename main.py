# main.py

import os

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

