import importlib
import sys
from pathlib import Path

# Ensure project root is on sys.path when running from scripts/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

modules = [
    "app.utils.events",
    "app.agents.shifu_v3.nodes",
    "app.agents.agent_langGraph.bigtools.workflow_bigtools",
    "app.workers.workflow_executor",
]

for m in modules:
    importlib.import_module(m)

print("SMOKE_IMPORTS_OK")
