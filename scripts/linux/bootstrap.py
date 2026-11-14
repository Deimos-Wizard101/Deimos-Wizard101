"""Start Deimos.py under pythonw.exe with stdout/stderr captured to a file.

A console-subsystem python.exe gets a Wine console window of its own, so
run.sh uses pythonw.exe, which has no standard streams at all. This gives it
some: everything printed, tracebacks included, lands in $DEIMOS_STDOUT_LOG.
"""
import os
import runpy
import sys

log = open(os.environ["DEIMOS_STDOUT_LOG"], "w", buffering=1, encoding="utf-8", errors="replace")
sys.stdout = sys.stderr = log
sys.path.insert(0, os.getcwd())
sys.argv = ["Deimos.py"]
runpy.run_path("Deimos.py", run_name="__main__")
