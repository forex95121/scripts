import os
import subprocess
import sys
import argparse
import shutil
import math
from datetime import datetime, timedelta

# ----------------------------- LOG DIRECTORY -----------------------------
LOG_DIR = r"G:\script"

if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
        print(f"Created log directory: {LOG_DIR}")
    except Exception as e:
        print(f"Error: Cannot create log directory '{LOG_DIR}': {e}")
        print("Make sure the G: drive is mounted and accessible.")
        sys.exit(1)

SKIP_LOG_PATH = os.path.join(LOG_DIR, "split_with_ffmpeg_skiplog.txt")
DETAILS_LOG_PATH = os.path.join(LOG_DIR, "split_with_ffmpeg_log_details.txt")
# -------------------------------------------------------------------------

def parse_size_limit(size_str):
    """Parse '500MB', '1024MB', '2.5GB' etc. into bytes."""
    size_str = size_str.strip().upper()
    if size_str.endswith('GB'):
        try:
            return float(size_str[:-2]) * 1024 * 1024 * 1024
        except ValueError:
            pass
    elif size_str.endswith('MB'):
        try:
            return float(size_str[:-2]) * 1024 * 1024
        except ValueError:
            pass
    print(f"Error: Invalid --sizeLimit format '{size_str}'. Use e.g. 500MB, 1024MB, 2.5GB")
    sys.exit(1)

def parse_time_duration(time_str):
    if time_str.startswith(':'):
        time_str = '0' + time_str
    try:
        parts = time_str.split(':')
        seconds = 0.0
        if len(parts) == 1:
            seconds = float(parts[0])
        elif len(parts) == 2:
            seconds = float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        return seconds
    except ValueError:
        print(f"Error: Invalid time format '{time_str}'. Use hh:mm:ss, mm:ss, :mm:ss, or ss.")
        sys.exit(1)

def get_duration(input_file):
    cmd = [
        'ffprobe', '-v', 'quiet', '-show_entries',
        'format=duration', '-of', 'csv=p=0', input_file
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except subprocess.CalledProcessError:
        print(f"Error: ffprobe failed on {input_file}")
        sys.exit(1)
    except ValueError:
        print(f"Error: Invalid duration for {input_file}")
        sys.exit(1)

def get_file_size_bytes(file_path):
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0

def format_duration(seconds):
    td = timedelta(seconds=float(seconds))
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def format_size(bytes_size):
    if bytes_size >= 1024 * 1024 * 1024:
        return f"{bytes_size / (1024**3):.2f} GB"
    else:
        return f"{bytes_size / (1024**2):.2f} MB"

def log_action(path, action, reason):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SKIP_LOG_PATH, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {action} ({reason}): {os.path.abspath(path)}\n")

def log_detailed_completion(source_file, output_parts, n_parts):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_abs = os.path.abspath(source_file)
    source_size = get_file_size_bytes(source_file)
    with open(DETAILS_LOG_PATH, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] COMPLETED SPLIT ({n_parts} parts): {source_abs}\n")
        log.write(f" Source size: {format_size(source_size)} | Duration: {format_duration(get_duration(source_file))}\n")
        log.write(f" Parts:\n")
        for part_path in output_parts:
            if os.path.exists(part_path):
                size_kb = get_file_size_bytes(part_path) // 1024
                dur = get_duration(part_path)
                log.write(f" • {os.path.basename(part_path)} | {format_size(get_file_size_bytes(part_path))} | {format_duration(dur)}\n")
            else:
                log.write(f" • {os.path.basename(part_path)} [MISSING]\n")
        log.write("\n")

def parse_dateafter(date_str):
    try:
        if len(date_str) == 8:
            return datetime.strptime(date_str, "%Y%m%d")
        elif len(date_str) == 14:
            return datetime.strptime(date_str, "%Y%m%d%H%M%S")
        else:
            raise ValueError
    except ValueError:
        print(f"Error: Invalid --dateafter format '{date_str}'.")
        sys.exit(1)

def format_part_filename(base_name, ext, part_num, total_parts, pattern):
    width = len(str(total_parts)) if total_parts >= 10 else 0
    part_str = f"{part_num:0{width}d}" if width > 0 else str(part_num)
    total_str = f"{total_parts:0{width}d}" if width > 0 else str(total_parts)
    filename = pattern.replace("##", total_str).replace("#", part_str)
    return f"{base_name}{filename}{ext}"

def generate_expected_parts(base_name, ext, target_dir, n_parts, pattern):
    return [
        os.path.join(target_dir, format_part_filename(base_name, ext, i + 1, n_parts, pattern))
        for i in range(n_parts)
    ]

def get_existing_parts(expected_parts):
    return [p for p in expected_parts if os.path.exists(p)]

def calculate_parts_from_size(file_size_bytes, size_limit_bytes):
    """Calculate how many parts needed to keep each under size_limit_bytes."""
    if file_size_bytes <= size_limit_bytes:
        return 1
    # Add small buffer to avoid edge-case overflow
    safe_limit = size_limit_bytes * 0.98
    n_parts = math.ceil(file_size_bytes / safe_limit)
    return max(n_parts, 2)  # At least 2 parts if splitting

def split_with_ffmpeg(input_file, n_parts, target_dir, pattern):
    os.makedirs(target_dir, exist_ok=True)
    base_name, ext = os.path.splitext(os.path.basename(input_file))
    expected_parts = generate_expected_parts(base_name, ext, target_dir, n_parts, pattern)
    existing_parts = get_existing_parts(expected_parts)
    missing_indices = [i for i, p in enumerate(expected_parts) if p not in existing_parts]

    if not missing_indices:
        return existing_parts, "already_complete"

    total_duration = get_duration(input_file)
    part_duration = total_duration / n_parts

    print(f"\nSplitting {os.path.basename(input_file)} into {n_parts} parts...")
    print(f"Source: {format_size(get_file_size_bytes(input_file))} | Duration: {format_duration(total_duration)}")
    print(f"Each part ~{format_duration(part_duration)}")

    status = "new"
    if len(existing_parts) > 0:
        print(f" Found {len(existing_parts)} existing part(s) → resuming")
        status = "completed_partial" if missing_indices else "already_complete"
        if len(missing_indices) == n_parts:
            status = "redone"

    for i in missing_indices:
        start_time = part_duration * i
        out_file = expected_parts[i]
        cmd = ['ffmpeg', '-y', '-ss', f"{start_time}", '-i', input_file, '-c', 'copy', '-avoid_negative_ts', 'make_zero']
        if i < n_parts - 1:
            cmd += ['-t', f"{part_duration}"]
        cmd.append(out_file)

        print(f" → Creating: {os.path.basename(out_file)}")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("   Done")
        except subprocess.CalledProcessError:
            print("   FAILED!")
            sys.exit(1)

    final_parts = get_existing_parts(expected_parts)
    if len(final_parts) == n_parts:
        log_detailed_completion(input_file, final_parts, n_parts)
        return final_parts, status
    else:
        print(" Warning: Split incomplete.")
        return final_parts, "incomplete"

def expand_source_paths(args):
    source_paths = []
    for p in args.path:
        abs_p = os.path.abspath(p)
        if os.path.isdir(abs_p):
            source_paths.append(abs_p)
        else:
            print(f"Warning: Source path not found: {abs_p}")

    if args.sourcePaths:
        for src in args.sourcePaths:
            if os.path.isfile(src) and src.lower().endswith('.txt'):
                try:
                    with open(src, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                abs_line = os.path.abspath(line)
                                if os.path.isdir(abs_line):
                                    source_paths.append(abs_line)
                except Exception as e:
                    print(f"Error reading sourcePaths file '{src}': {e}")
            else:
                for part in src.split(','):
                    part = part.strip()
                    if part:
                        abs_part = os.path.abspath(part)
                        if os.path.isdir(abs_part):
                            source_paths.append(abs_part)

    seen = set()
    unique_paths = [p for p in source_paths if not (p in seen or seen.add(p))]
    return unique_paths

def main():
    parser = argparse.ArgumentParser(
        description="""
Advanced FFmpeg Video Splitter

--sizeLimit "500MB" → Auto-calculate number of parts so each is < limit
Otherwise → Use fixed number of parts from first argument

Supports multiple sources via -p or --sourcePaths
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("parts", type=int, nargs='?', default=2,
                        help="Fixed number of parts (ignored if --sizeLimit used)")
    parser.add_argument("-k", "--keyword", type=str, default=None, help="Keyword filter")
    parser.add_argument("-p", "--path", action="append", default=[], help="Source directory (multiple allowed)")
    parser.add_argument("--sourcePaths", action="append", default=[], 
                        help="paths.txt or 'path1,path2'")
    parser.add_argument("--targetPath", type=str, required=True, help="Target directory for parts & moved files")
    parser.add_argument("--dateafter", type=str, default=None, help="Files created after date")
    parser.add_argument("-e", "--exists-pattern", type=str, default="_part_#_of_##", help="Part naming pattern")
    parser.add_argument("--minlength", type=str, default=None, help="Move if SHORTER than this")
    parser.add_argument("--maxlength", type=str, default=None, help="Ignore if LONGER than this")
    parser.add_argument("--sizeLimit", type=str, default=None, help="Max size per part: 500MB, 1024MB, 2.5GB etc.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")

    args = parser.parse_args()

    if args.dry_run:
        print("DRY-RUN MODE: No changes will be made.\n")

    if "#" not in args.exists_pattern:
        print("Warning: Pattern has no '#' → part numbers may not appear.")

    if not args.path and not args.sourcePaths:
        args.path = ["."]

    source_paths = expand_source_paths(args)
    if not source_paths:
        print("Error: No valid source directories.")
        sys.exit(1)

    target_dir = os.path.abspath(args.targetPath)
    os.makedirs(target_dir, exist_ok=True)

    min_creation_dt = parse_dateafter(args.dateafter) if args.dateafter else None
    min_seconds = parse_time_duration(args.minlength) if args.minlength else None
    max_seconds = parse_time_duration(args.maxlength) if args.maxlength else None
    size_limit_bytes = parse_size_limit(args.sizeLimit) if args.sizeLimit else None

    print(f"TargetPath     : {target_dir}")
    if size_limit_bytes:
        print(f"Size limit/part: {args.sizeLimit} ({format_size(size_limit_bytes)})")
        print(f"→ Number of parts calculated automatically per file")
    else:
        print(f"Fixed parts    : {args.parts}")
    print(f"Pattern        : {args.exists_pattern}")
    if args.minlength:
        print(f"Move if shorter: {args.minlength}")
    if args.maxlength:
        print(f"Ignore if longer: {args.maxlength}")
    print(f"Sources ({len(source_paths)}):")
    for sp in source_paths:
        print(f" • {sp}")
    print(f"Logs → {LOG_DIR}")
    if args.dry_run:
        print("\n=== PREVIEW ===\n")
    else:
        print()

    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts'}
    candidates = []

    for source_path in source_paths:
        for entry in os.listdir(source_path):
            fp = os.path.join(source_path, entry)
            if not os.path.isfile(fp):
                continue
            _, ext = os.path.splitext(entry.lower())
            if ext not in video_extensions:
                continue
            if args.keyword and args.keyword.lower() not in entry.lower():
                continue
            if min_creation_dt:
                try:
                    if datetime.fromtimestamp(os.path.getctime(fp)) <= min_creation_dt:
                        continue
                except OSError:
                    pass
            candidates.append(fp)

    if not candidates:
        print("No candidate video files found.")
        sys.exit(0)

    to_move = []
    to_ignore = []
    to_split = []  # Will store (file, calculated_parts)

    for video_file in candidates:
        duration = get_duration(video_file)
        size_bytes = get_file_size_bytes(video_file)
        base_name = os.path.basename(video_file)
        dur_str = format_duration(duration)

        if max_seconds is not None and duration > max_seconds:
            to_ignore.append((base_name, dur_str, format_size(size_bytes)))
            continue

        if min_seconds is not None and duration < min_seconds:
            to_move.append((base_name, dur_str, format_size(size_bytes)))
            continue

        if size_limit_bytes:
            n_parts = calculate_parts_from_size(size_bytes, size_limit_bytes)
        else:
            n_parts = args.parts

        base, ext = os.path.splitext(base_name)
        expected = generate_expected_parts(base, ext, target_dir, n_parts, args.exists_pattern)
        existing = get_existing_parts(expected)

        if len(existing) == n_parts:
            to_ignore.append((base_name, dur_str, format_size(size_bytes)))  # treat as skipped
        else:
            status = "resume" if existing else "new"
            to_split.append((video_file, n_parts, status, base_name, dur_str, format_size(size_bytes)))

    # Preview
    if to_move:
        print("MOVED (too short):")
        for name, dur, sz in to_move:
            print(f" • {name} ({dur}, {sz})")
        print()

    if to_ignore:
        print("SKIPPED / IGNORED:")
        for name, dur, sz in to_ignore:
            print(f" • {name} ({dur}, {sz})")
        print()

    if to_split:
        print("TO BE SPLIT:")
        for _, n_parts, status, name, dur, sz in to_split:
            print(f" • {name} ({dur}, {sz}) → {n_parts} parts ({status})")
        print()

    print("Summary:")
    print(f"  Move (short) : {len(to_move)}")
    print(f"  Skip/Ignored : {len(to_ignore)}")
    print(f"  Split        : {len(to_split)}")

    if args.dry_run:
        print("\nDry-run complete. Remove --dry-run to execute.")
        sys.exit(0)

    # Execution
    print("\n=== EXECUTING ===")
    moved = ignored = processed = 0

    for video_file in candidates:
        duration = get_duration(video_file)
        size_bytes = get_file_size_bytes(video_file)
        base_name = os.path.basename(video_file)

        if max_seconds is not None and duration > max_seconds:
            log_action(video_file, "IGNORED", "too long")
            ignored += 1
            continue

        if min_seconds is not None and duration < min_seconds:
            dest = os.path.join(target_dir, base_name)
            if os.path.exists(dest):
                log_action(video_file, "SKIPPED", "short, already moved")
            else:
                try:
                    shutil.move(video_file, dest)
                    print(f"MOVED: {base_name}")
                    log_action(video_file, "MOVED", "too short")
                    moved += 1
                except Exception as e:
                    print(f"Move failed: {e}")
            continue

        n_parts = calculate_parts_from_size(size_bytes, size_limit_bytes) if size_limit_bytes else args.parts
        base, ext = os.path.splitext(base_name)
        expected = generate_expected_parts(base, ext, target_dir, n_parts, args.exists_pattern)
        if len(get_existing_parts(expected)) == n_parts:
            print(f"SKIPPED: {base_name} (all {n_parts} parts exist)")
            log_action(video_file, "SKIPPED", "all parts exist")
            ignored += 1
            continue

        _, status = split_with_ffmpeg(video_file, n_parts, target_dir, args.exists_pattern)
        processed += 1

    print(f"\n=== Finished ===")
    print(f" Moved (short)   : {moved}")
    print(f" Skipped/Ignored : {ignored}")
    print(f" Split processed : {processed}")
    print(f" TargetPath      : {target_dir}")
    print(f" Logs            : {LOG_DIR}")

if __name__ == "__main__":
    main()