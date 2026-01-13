#!/usr/bin/env python3

"""
split_with_ffmpeg.py

A Python script to split large audio/video files into smaller parts using ffmpeg,
with each part kept just below a specified size limit (in MB).

Features:
- Processes multiple source files or directories.
- Supports a list of source paths from a text file.
- Multiple target directories (one per source, or cycled).
- Skips files smaller than the size limit.
- Optional filename keyword filter.
- Skips if existing split parts match the pattern.
- Optional file type filtering.
- New: Filter files by creation date range using --dateFrom and --dateTo.

The splitting uses stream copy (-c copy) for speed and no quality loss.
Parts are named: originalname_part_1_of_N.ext, part_2_of_N.ext, etc.

Usage examples:
    python split_with_ffmpeg.py --sourcePaths "/path/to/file1.mp4,/path/to/dir" \
                                --targetPath "/output/dir" \
                                --sizeLimit 500MB

    python split_with_ffmpeg.py --sourcePaths sources.txt \
                                --targetPath "/out1,/out2" \
                                --sizeLimit 1000MB \
                                --keyword "vacation" \
                                --type "mp4,mkv" \
                                --exists-pattern "_part_#_of_#" \
                                --dateFrom 260101 --dateTo "260115-14:30:00"

When run without arguments, prints full usage information.
"""

import argparse
import os
import sys
import subprocess
import re
import datetime
import math

def parse_size_limit(size_str: str) -> int:
    """Parse size limit like '500MB' to bytes."""
    match = re.match(r"^(\d+)(MB|GB)?$", size_str.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid sizeLimit format: {size_str}. Use e.g. 500MB")
    num = int(match.group(1))
    unit = match.group(2).upper() if match.group(2) else "MB"
    if unit == "GB":
        return num * 1024 * 1024 * 1024
    return num * 1024 * 1024

def parse_date(date_str: str):
    """Parse date in yyymmdd[-hh:mm:ss] format. Time part optional."""
    if not date_str:
        return None
    try:
        if len(date_str) == 6:
            return datetime.datetime.strptime(date_str, "%y%m%d")
        elif "-" in date_str:
            return datetime.datetime.strptime(date_str, "%y%m%d-%H:%M:%S")
        else:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_str}. Use yyymmdd or yyymmdd-hh:mm:ss")

def get_file_creation_time(path: str) -> datetime.datetime:
    """Get file creation time (birth time on Unix, creation on Windows)."""
    if sys.platform.startswith("win"):
        return datetime.datetime.fromtimestamp(os.stat(path).st_ctime)
    else:
        return datetime.datetime.fromtimestamp(os.stat(path).st_birthtime)

def get_duration(file_path: str) -> float:
    """Get duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def get_file_size(file_path: str) -> int:
    return os.path.getsize(file_path)

def check_existing_parts(base_name: str, ext: str, target_dir: str, total_parts: int, pattern: str) -> bool:
    """Check if all expected parts already exist."""
    for i in range(1, total_parts + 1):
        part_name = pattern.replace("#", str(i)).replace("#", str(total_parts), 1)  # rough, but works for _part_#_of_#
        filename = f"{base_name}{part_name}{ext}"
        if not os.path.exists(os.path.join(target_dir, filename)):
            return False
    return True

def split_file(source_path: str, target_dir: str, size_limit_bytes: int, exists_pattern: str):
    """Split a single file using the -fs loop method."""
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    file_size = get_file_size(source_path)
    if file_size < size_limit_bytes:
        print(f"Skipping (smaller than limit): {source_path}")
        return

    duration = get_duration(source_path)
    estimated_bitrate = file_size * 8 / duration  # bits per second
    estimated_part_duration = (size_limit_bytes * 8) / estimated_bitrate * 0.95  # safety margin

    num_parts = math.ceil(file_size / size_limit_bytes)
    print(f"Splitting {source_path} into ~{num_parts} parts (target < {size_limit_bytes // (1024*1024)} MB each)")

    base_name = os.path.basename(source_path)
    name, ext = os.path.splitext(base_name)

    # Rough check for existing
    if check_existing_parts(name, ext, target_dir, num_parts, exists_pattern):
        print(f"Skipping (parts exist): {source_path}")
        return

    current_start = 0.0
    part_index = 1

    while current_start < duration:
        output_file = os.path.join(target_dir, f"{name}_part_{part_index}_of_{num_parts}{ext}")

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(current_start),
            "-i", source_path,
            "-fs", str(size_limit_bytes),
            "-c", "copy",
            output_file
        ]

        print(f"Creating part {part_index}/{num_parts}: {os.path.basename(output_file)}")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Get duration of created part
        part_duration = get_duration(output_file)
        current_start += part_duration
        part_index += 1

    print(f"Finished splitting: {source_path}")

def main():
    parser = argparse.ArgumentParser(description="Split media files with ffmpeg by size limit.", add_help=False)
    parser.add_argument("--sourcePaths", required=False, help='Comma-separated paths or "file.txt" with one path per line.')
    parser.add_argument("--targetPath", required=False, help="Comma-separated target directories.")
    parser.add_argument("--sizeLimit", required=False, help="Size limit per part, e.g. 500MB or 2GB.")
    parser.add_argument("-k", "--keyword", required=False, help="Only process files containing this keyword in name.")
    parser.add_argument("-e", "--exists-pattern", default="_part_#_of_#", help="Pattern to detect existing splits (default: '_part_#_of_#')")
    parser.add_argument("--type", required=False, help="Comma-separated file extensions to process, e.g. mp4,mkv,avi")
    parser.add_argument("--dateFrom", type=parse_date, help="Process files created on/after this date (yyymmdd or yyymmdd-hh:mm:ss)")
    parser.add_argument("--dateTo", type=parse_date, help="Process files created before this date (yyymmdd or yyymmdd-hh:mm:ss)")

    parser.add_argument("-h", "--help", action="help", help="Show this help message and exit.")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if not args.sourcePaths or not args.targetPath or not args.sizeLimit:
        print("Error: --sourcePaths, --targetPath and --sizeLimit are required.")
        parser.print_help()
        sys.exit(1)

    size_limit_bytes = parse_size_limit(args.sizeLimit)

    # Load source paths
    sources = []
    if args.sourcePaths.endswith(".txt"):
        with open(args.sourcePaths, "r", encoding="utf-8") as f:
            for line in f:
                path = line.strip()
                if path:
                    sources.append(path)
    else:
        sources = [p.strip() for p in args.sourcePaths.split(",") if p.strip()]

    # Target directories
    targets = [t.strip() for t in args.targetPath.split(",") if t.strip()]

    # Allowed extensions
    allowed_ext = None
    if args.type:
        allowed_ext = {e.lower().lstrip(".") for e in args.type.split(",")}

    # Date range
    date_from = args.dateFrom
    date_to = args.dateTo

    file_list = []
    for src in sources:
        if os.path.isfile(src):
            file_list.append(src)
        elif os.path.isdir(src):
            for root, _, files in os.walk(src):
                for f in files:
                    file_list.append(os.path.join(root, f))
        else:
            print(f"Warning: Source not found: {src}")

    for file_path in file_list:
        if allowed_ext:
            ext = os.path.splitext(file_path)[1].lstrip(".").lower()
            if ext not in allowed_ext:
                continue

        if args.keyword and args.keyword.lower() not in os.path.basename(file_path).lower():
            continue

        # Date filter
        try:
            ctime = get_file_creation_time(file_path)
            if date_from and ctime < date_from:
                continue
            if date_to and ctime >= date_to:
                continue
        except Exception:
            pass  # Skip date check if unavailable

        # Choose target dir (cycle if fewer than sources)
        target_idx = sources.index(next(s for s in sources if file_path.startswith(s))) if any(file_path.startswith(s) for s in sources) else 0
        target_dir = targets[target_idx % len(targets)]

        split_file(file_path, target_dir, size_limit_bytes, args.exists_pattern)

if __name__ == "__main__":
    main()