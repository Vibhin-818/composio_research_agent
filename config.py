from pathlib import Path

ROOT = Path(__file__).resolve().parent

APPS_FILE = ROOT / "apps.yaml"
STORE_DIR = ROOT / "store"
CACHE_DB = STORE_DIR / "cache.sqlite"

RESULTS = ROOT / "results.json"
PATTERNS = ROOT / "patterns.json"
VERIFICATION = ROOT / "verification.json"
SAMPLE_CSV = ROOT / "verification_sample.csv"

REPORT_DIR = ROOT / "report"
DIST = ROOT / "docs"

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
NVIDIA_MAX_TOKENS = 2000
NVIDIA_TIMEOUT = 90
MAX_CONCURRENCY = 6
