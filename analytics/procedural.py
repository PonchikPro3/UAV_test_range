"""A3/A4: offline telemetry analysis and draft protocol, without third-party libraries."""
import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = ["time_s", "x_m", "y_m", "height_m", "speed_m_s", "battery_pct"]
LIMITS = ["x_min", "x_max", "y_min", "y_max", "height_max", "speed_max", "battery_min"]


def validate_limits(limits):
    if not isinstance(limits, dict):
        raise ValueError("Limits must be a JSON object")
    for name in LIMITS:
        if name not in limits or not isinstance(limits[name], (int, float)) or isinstance(limits[name], bool):
            raise ValueError(f"Missing or invalid limit: {name}")
        if not math.isfinite(float(limits[name])):
            raise ValueError(f"Non-finite limit: {name}")
    limits = {name: float(limits[name]) for name in LIMITS}
    if limits["x_min"] >= limits["x_max"] or limits["y_min"] >= limits["y_max"]:
        raise ValueError("Invalid zone rectangle")
    if limits["height_max"] < 0 or limits["speed_max"] < 0:
        raise ValueError("Negative maximum")
    if not 0 <= limits["battery_min"] <= 100:
        raise ValueError("Invalid battery minimum")
    return limits


def analyze_telemetry(path, limits):
    """One pass over n samples, O(n+k) time and O(k) result memory (k events)."""
    limits = validate_limits(limits)
    count = 0
    violations = []
    previous_time = None
    max_height = max_speed = min_battery = None
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        reader = csv.DictReader(hashed_lines(stream, digest), strict=True)
        if reader.fieldnames != COLUMNS:
            raise ValueError("Unexpected CSV columns or column order")
        for row_number, row in enumerate(reader, 2):
            if None in row or any(row.get(name) in (None, "") for name in COLUMNS):
                raise ValueError(f"Incomplete or extra fields at row {row_number}")
            try:
                t, x, y, height, speed, battery = [float(row[c]) for c in COLUMNS]
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Non-numeric data at row {row_number}") from exc
            if not all(math.isfinite(v) for v in (t, x, y, height, speed, battery)):
                raise ValueError(f"Non-finite data at row {row_number}")
            if t < 0 or height < 0 or speed < 0 or not 0 <= battery <= 100:
                raise ValueError(f"Invalid physical value at row {row_number}")
            if previous_time is not None and t <= previous_time:
                raise ValueError(f"Time must increase at row {row_number}")
            previous_time = t
            count += 1
            checks = [
                (not (limits["x_min"] <= x <= limits["x_max"]
                      and limits["y_min"] <= y <= limits["y_max"]), "OUTSIDE_ZONE",
                 math.hypot(max(limits["x_min"] - x, 0, x - limits["x_max"]),
                            max(limits["y_min"] - y, 0, y - limits["y_max"])), 0.0),
                (height > limits["height_max"], "HEIGHT_LIMIT", height, limits["height_max"]),
                (speed > limits["speed_max"], "SPEED_LIMIT", speed, limits["speed_max"]),
                (battery < limits["battery_min"], "LOW_BATTERY", battery, limits["battery_min"]),
            ]
            for failed, code, actual, limit in checks:
                if failed:
                    violations.append({"row": row_number, "seq_no": count, "time_s": t,
                                       "code": code, "actual_value": actual, "limit_value": limit})
            max_height = height if max_height is None else max(max_height, height)
            max_speed = speed if max_speed is None else max(max_speed, speed)
            min_battery = battery if min_battery is None else min(min_battery, battery)
    if count == 0:
        raise ValueError("Telemetry contains no samples")
    return {
        "samples": count, "limits": limits, "violation_count": len(violations),
        "violations": violations, "max_height_m": max_height,
        "max_speed_m_s": max_speed, "min_battery_pct": min_battery,
        "result": "PASSED" if not violations else "FAILED", "telemetry_sha256": digest.hexdigest(),
    }


def hashed_lines(stream, digest):
    first = True
    for line in stream:
        digest.update(line)
        yield line.decode("utf-8-sig" if first else "utf-8")
        first = False


def build_protocol(test_id, analysis):
    """Create a draft from analyzed data; this is not a signed flight clearance."""
    if not test_id or not all(c.isascii() and (c.isalnum() or c in "_-") for c in test_id):
        raise ValueError("Invalid test identifier")
    return {
        "test_id": test_id, "status": "DRAFT", "method": "DISCRETE_RECTANGLE_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "telemetry_sha256": analysis["telemetry_sha256"], "analysis": analysis,
    }


def render_text(protocol):
    a = protocol["analysis"]
    lines = ["ПРОЕКТ ПРОТОКОЛА ИСПЫТАНИЯ", f"Испытание: {protocol['test_id']}",
             "Данные: учебный демонстрационный набор", f"Отсчётов: {a['samples']}",
             f"Отклонений: {a['violation_count']}",
             "Результат: " + ("пройдено" if a["result"] == "PASSED" else "не пройдено"),
             f"SHA-256 телеметрии: {protocol['telemetry_sha256']}"]
    for v in a["violations"]:
        lines.append(f"Строка {v['row']}, t={v['time_s']:g} с: {v['code']}")
    lines.append("Результат относится к заданным порогам и дискретным отсчётам; требуется проверка инженером.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telemetry", type=Path)
    parser.add_argument("limits", type=Path)
    parser.add_argument("--test-id", default="T-DEMO")
    parser.add_argument("--output", type=Path, default=Path("results/protocol.json"))
    args = parser.parse_args()
    try:
        limits = json.loads(args.limits.read_text(encoding="utf-8"))
        analysis = analyze_telemetry(args.telemetry, limits)
        protocol = build_protocol(args.test_id, analysis)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(protocol, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        args.output.with_suffix(".txt").write_text(render_text(protocol), encoding="utf-8")
        print(f"samples={analysis['samples']}; violations={analysis['violation_count']}; result={analysis['result']}")
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"Ошибка входных данных: {exc}\n")


if __name__ == "__main__":
    main()
