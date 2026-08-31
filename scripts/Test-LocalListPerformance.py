from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from stt_desktop.storage import ProjectWorkspace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark bounded local entity list reads with 100,000 synthetic rows."
    )
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--budget-ms", type=float, default=300.0)
    arguments = parser.parse_args()
    if arguments.rows < 1:
        parser.error("--rows must be positive")
    if not 1 <= arguments.page_size <= 500:
        parser.error("--page-size must be between 1 and 500")

    measurements: list[float] = []
    with tempfile.TemporaryDirectory(prefix="stt-list-performance-") as temporary:
        workspace = ProjectWorkspace(Path(temporary) / "workspace")
        with workspace.create_project("十万条分页性能") as project:
            now = "2026-08-31T00:00:00.000Z"
            project.connection.execute("BEGIN IMMEDIATE")
            try:
                project.connection.executemany(
                    "INSERT INTO teachers(id, employee_no, name, department, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'active', ?, ?)",
                    (
                        (
                            f"teacher-{index:06d}",
                            f"T-{index:06d}",
                            f"教师 {index:06d}",
                            "合成数据",
                            now,
                            now,
                        )
                        for index in range(arguments.rows)
                    ),
                )
                project.connection.execute("COMMIT")
            except Exception:
                project.connection.execute("ROLLBACK")
                raise

            offsets = [
                0,
                max(0, arguments.rows // 4),
                max(0, arguments.rows // 2),
                max(0, arguments.rows - arguments.page_size),
                0,
            ]
            for offset in offsets:
                started = time.perf_counter()
                items, total = project.list_entities_page(
                    "teacher", limit=arguments.page_size, offset=offset
                )
                encoded = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
                elapsed_ms = (time.perf_counter() - started) * 1_000
                if total != arguments.rows or len(items) != arguments.page_size or not encoded:
                    raise RuntimeError("分页结果数量或 JSON 序列化结果无效")
                measurements.append(elapsed_ms)

    result = {
        "rows": arguments.rows,
        "pageSize": arguments.page_size,
        "budgetMilliseconds": arguments.budget_ms,
        "samplesMilliseconds": [round(value, 3) for value in measurements],
        "medianMilliseconds": round(statistics.median(measurements), 3),
        "maximumMilliseconds": round(max(measurements), 3),
        "passed": max(measurements) <= arguments.budget_ms,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
