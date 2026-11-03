"""Compile, verify and run the procedural prototype from any working directory."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(command):
    result = subprocess.run([str(p) for p in command], cwd=ROOT, text=True, encoding="utf-8",
                            capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip(), result.stderr.strip()


def main():
    javac = os.environ.get("JAVAC") or shutil.which("javac")
    if not javac:
        raise SystemExit("Install JDK 11+ or set JAVAC to its compiler path")
    java = Path(javac).resolve().with_name("java.exe" if os.name == "nt" else "java")
    if not java.exists():
        raise SystemExit("java must belong to the same JDK as javac")
    build = ROOT / "build"
    results = ROOT / "results"
    build.mkdir(exist_ok=True)
    results.mkdir(exist_ok=True)
    run([javac, "-encoding", "UTF-8", "--release", "11", "-d", build,
         ROOT / "backend/ProceduralAlgorithms.java", ROOT / "backend/AlgorithmChecks.java"])
    java_checks, _ = run([java, "-cp", build, "AlgorithmChecks"])
    python_checks, python_details = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    planning, _ = run([java, "-cp", build, "ProceduralAlgorithms", ROOT / "data/target.properties", ROOT / "data/schedule.csv"])
    (results / "planning.json").write_text(json.dumps(json.loads(planning), indent=2) + "\n", encoding="utf-8")
    clean = (ROOT / "data/target.properties").read_text(encoding="utf-8").replace(
        "T10:00:00+03:00", "T12:00:00+03:00").replace("T11:00:00+03:00", "T13:00:00+03:00")
    clean_path = results / "target_free.properties"
    clean_path.write_text(clean, encoding="utf-8")
    free, _ = run([java, "-cp", build, "ProceduralAlgorithms", clean_path, ROOT / "data/schedule.csv"])
    (results / "planning_free.json").write_text(json.dumps(json.loads(free), indent=2) + "\n", encoding="utf-8")
    analysis, _ = run([sys.executable, ROOT / "analytics/procedural.py", ROOT / "data/telemetry.csv",
                       ROOT / "data/limits.json", "--output", results / "protocol.json"])
    summary = {"java": java_checks, "python": python_details, "demo": analysis,
               "planning": json.loads(planning), "planning_free": json.loads(free)}
    (results / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(java_checks)
    print(python_details)
    print(planning)
    print(free)
    print(analysis)


if __name__ == "__main__":
    main()
