import sys
from pathlib import Path

# Ensure `market` is importable as a top-level package regardless of how
# pytest is invoked (with or without an editable `uv sync` install).
sys.path.insert(0, str(Path(__file__).parent))
