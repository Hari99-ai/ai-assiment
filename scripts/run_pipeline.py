"""Workspace-root entry point for the OEE analytics project."""
from pathlib import Path
import runpy
import sys

project = Path(__file__).resolve().parents[1] / "oee-analytics"
sys.path.insert(0, str(project))
sys.argv[0] = str(project / "scripts" / "run_pipeline.py")
runpy.run_path(str(project / "scripts" / "run_pipeline.py"), run_name="__main__")
