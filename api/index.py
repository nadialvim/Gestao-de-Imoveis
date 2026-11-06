import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gestao import create_app  # noqa: E402

app = create_app()
