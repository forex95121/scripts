#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from mutagen import File as MutagenFile

# ANSI colors
GREEN = "\033[92m"
RESET = "\033[0m"

SUPPORTED_TYPES = {"mp3", "mp4", "m4a", "opus"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Modify metadata for audio/video files"
    )

    parser.add_argument(
        "--type",
        help='Comma-separated file types: "mp3,mp4,m4a,opus"',
        required=True,
    )

    parser.add_argument(
        "--bitrate",
        help='Target bitrate (e.g. "128k")',
    )

    parser.add_argument(
        "--datemodified",
        help='Set file modified time: yyyymmdd-hh:mm',
    )

    parser.add_argument(
        "-k", "--keyword",
        help="Only process files whose names contain this keyword",
    )

    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Process directories recursively",
    )

    parser.add_argument(
        "-p", "--path",
        help="Directory path to process",
    )

    parser.add_argument(
        "-l", "--path-list",
        help="Text file containing list of directory paths",
    )

    return parser.parse_args()


def parse_datetime(dt_str):
    try:
        return datetime.strptime(dt_str, "%Y%m%d-%H:%M")
    except ValueError:
        sys.exit("❌ Invalid --datemodified format. Use yyyymmdd-hh:mm")


def iter_files(base_path, recursive):
    if recursive:
        for root, _, files in os.walk(base_path):
            for f in files:
                yield Path(root) / f
    else:
        for f in base_path.iterdir():
            if f.is_file():
                yield f


def should_process(file_path, types, keyword):
    if file_path.suffix.lower().lstrip(".") not in types:
        return False
    if keyword and keyword not in file_path.name:
        return False
    return True


def modify_metadata(file_path, bitrate):
    try:
        audio = MutagenFile(file_path, easy=True)
        if audio is None:
            return False

        if bitrate:
            audio["bitrate"] = bitrate

        audio.save()
        return True
    except Exception:
        return False


def set_file_mtime(file_path, dt):
    ts = dt.timestamp()
    os.utime(file_path, (ts, ts))


def process_directory(path, args, types, dt):
    for file_path in iter_files(path, args.recursive):
        if not should_process(file_path, types, args.keyword):
            continue

        modified = False

        if args.bitrate:
            if modify_metadata(file_path, args.bitrate):
                modified = True

        if dt:
            set_file_mtime(file_path, dt)
            modified = True

        if modified:
            print(f"{GREEN}→ {file_path}{RESET}")


def load_paths(args):
    if args.path and args.path_list:
        sys.exit("❌ --path and --path-list are mutually exclusive")

    if args.path_list:
        try:
            with open(args.path_list, "r", encoding="utf-8") as f:
                return [Path(line.strip()) for line in f if line.strip()]
        except FileNotFoundError:
            sys.exit("❌ Path list file not found")

    if args.path:
        return [Path(args.path)]

    return [Path.cwd()]


def main():
    args = parse_args()

    types = {t.strip().lower() for t in args.type.split(",")}
    invalid = types - SUPPORTED_TYPES
    if invalid:
        sys.exit(f"❌ Unsupported file types: {', '.join(invalid)}")

    dt = parse_datetime(args.datemodified) if args.datemodified else None

    paths = load_paths(args)

    for path in paths:
        if not path.exists() or not path.is_dir():
            print(f"⚠ Skipping invalid directory: {path}")
            continue

        process_directory(path, args, types, dt)


if __name__ == "__main__":
    main()