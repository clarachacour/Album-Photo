import sys
from pathlib import Path

# Let tests `import security` (and later the other backend modules) no matter
# which folder pytest is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
