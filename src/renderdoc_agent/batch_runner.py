"""Batch analysis helpers."""

import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .analysis_runner import quick_report
from .config import Config


def collect_rdc_files(input_dir: str, recursive: bool) -> list[Path]:
    root = Path(input_dir)
    pattern = "**/*.rdc" if recursive else "*.rdc"
    return sorted(root.glob(pattern), key=lambda path: path.name.lower())


def safe_stem(path: Path) -> str:
    stem = path.stem.strip()
    safe = "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in stem)
    return safe or "capture"


def write_summary_csv(rows: list[dict], output_dir: Path) -> Path:
    summary_path = output_dir / "summary.csv"
    fields = [
        "file_name",
        "mode",
        "status",
        "draw_calls",
        "triangles",
        "texture_memory_mb",
        "frame_time_ms",
        "fps_estimate",
        "overdraw_ratio",
        "total_ms",
        "cache_hit",
        "error",
    ]
    with open(summary_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return summary_path


def batch_analyze(
    files: list[Path],
    platform: str,
    mode: str,
    config: Config,
    output_dir: Path,
    jobs: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(files)
    started = time.perf_counter()
    rows = []

    def run_one(index: int, file_path: Path) -> dict:
        subdir = output_dir / f"{index:03d}_{safe_stem(file_path)}"
        try:
            print(f"[{index}/{total}] analyzing {file_path.name}")
            return quick_report(str(file_path), platform, config, mode, str(subdir))
        except Exception as exc:
            return {
                "file_name": file_path.name,
                "mode": mode,
                "status": "ERROR",
                "draw_calls": "",
                "triangles": "",
                "texture_memory_mb": "",
                "frame_time_ms": "",
                "fps_estimate": "",
                "overdraw_ratio": "",
                "total_ms": "",
                "cache_hit": "",
                "error": str(exc),
            }

    indexed_files = list(enumerate(files, start=1))
    if jobs <= 1:
        for index, file_path in indexed_files:
            rows.append(run_one(index, file_path))
    else:
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            future_map = {
                executor.submit(run_one, index, file_path): index
                for index, file_path in indexed_files
            }
            for future in as_completed(future_map):
                rows.append(future.result())

    rows.sort(key=lambda row: row.get("file_name", ""))
    summary_path = write_summary_csv(rows, output_dir)
    success = sum(1 for row in rows if not row.get("error"))
    failed = len(rows) - success
    elapsed = round(time.perf_counter() - started, 2)
    print(f"批量完成: success={success}, failed={failed}, total={len(rows)}, elapsed={elapsed}s")
    print(f"汇总文件: {summary_path}")
