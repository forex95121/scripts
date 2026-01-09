import os
import subprocess
import sys
import argparse
import shutil
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

def parse_time_duration(time_str):
    """Parse hh:mm:ss, mm:ss, :mm:ss, or ss into seconds."""
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
        else:
            raise ValueError
        return seconds
    except ValueError:
        print(f"Error: Invalid time format '{time_str}'. Use hh:mm:ss, mm:ss, :mm:ss, or ss.")
        sys.exit(1)

def get_duration(input_file):
    """Get duration using ffprobe."""
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

def get_file_size_kb(file_path):
    try:
        return os.path.getsize(file_path) // 1024
    except OSError:
        return 0

def format_duration(seconds):
    td = timedelta(seconds=float(seconds))
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def log_action(path, action, reason):
    """Unified logging for skipped/moved/ignored."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SKIP_LOG_PATH, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {action} ({reason}): {os.path.abspath(path)}\n")

def log_detailed_completion(source_file, output_parts):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_abs = os.path.abspath(source_file)
    total_size_kb = sum(get_file_size_kb(p) for p in output_parts)
    with open(DETAILS_LOG_PATH, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] COMPLETED SPLIT: {source_abs}\n")
        log.write(f" Source duration: {format_duration(get_duration(source_file))}\n")
        log.write(f" Parts created: {len(output_parts)}\n")
        for part_path in output_parts:
            if os.path.exists(part_path):
                dur = get_duration(part_path)
                size_kb = get_file_size_kb(part_path)
                log.write(f" • {os.path.basename(part_path)}\n")
                log.write(f"   Duration: {format_duration(dur)} | Size: {size_kb:,} KB\n")
            else:
                log.write(f" • {os.path.basename(part_path)} [MISSING]\n")
        log.write(f" Total output size: {total_size_kb:,} KB\n")
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
        print(f"Error: Invalid --dateafter format '{date_str}'. Use yyyymmdd or yyyymmddhhmmss")
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

def split_with_ffmpeg(input_file, n_parts, target_dir, pattern):
    os.makedirs(target_dir, exist_ok=True)
    base_name, ext = os.path.splitext(os.path.basename(input_file))
    expected_parts = generate_expected_parts(base_name, ext, target_dir, n_parts, pattern)
    existing_parts = get_existing_parts(expected_parts)
    missing_indices = [i for i, p in enumerate(expected_parts) if p not in existing_parts]

    if not missing_indices:
        return existing_parts, "already_complete"

    print(f"\nSplitting {os.path.basename(input_file)} into {n_parts} parts...")
    total_duration = get_duration(input_file)
    part_duration = total_duration / n_parts
    print(f"Duration: {format_duration(total_duration)} → Each ~{format_duration(part_duration)}")

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
        log_detailed_completion(input_file, final_parts)
        return final_parts, status
    else:
        print(" Warning: Split incomplete.")
        return final_parts, "incomplete"

def main():
    parser = argparse.ArgumentParser(
        description="""
Advanced FFmpeg Video Splitter - Corrected Logic

--minlength  : Files SHORTER than this → MOVED to target folder
--maxlength  : Files LONGER than this  → IGNORED (skipped)
Suitable length → SPLIT into parts

Examples:
  Short clips (<50min) → moved
  Too long (>1:30h)    → skipped
  50:00 ~ 1:30:00      → split into parts
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("parts", type=int, help="Number of parts to split suitable files into")
    parser.add_argument("-k", "--keyword", type=str, default=None, help="Keyword filter (case-insensitive)")
    parser.add_argument("-p", "--path", type=str, default=".", help="Source directory")
    parser.add_argument("-t", "--target", type=str, required=True, help="Target directory (REQUIRED for moving short files)")
    parser.add_argument("--dateafter", type=str, default=None, help="Only files created after yyyymmdd or yyyymmddhhmmss")
    parser.add_argument("-e", "--exists-pattern", type=str, default="_part_#_of_##", help="Part naming pattern")
    parser.add_argument("--minlength", type=str, default=None, help="Move files SHORTER than this (hh:mm:ss, mm:ss, ss)")
    parser.add_argument("--maxlength", type=str, default=None, help="Ignore files LONGER than this (hh:mm:ss, mm:ss, ss)")

    args = parser.parse_args()

    if "#" not in args.exists_pattern:
        print("Warning: Pattern has no '#' → part numbers may not appear.")

    source_path = os.path.abspath(args.path)
    if not os.path.isdir(source_path):
        print(f"Error: Source path not found: {source_path}")
        sys.exit(1)

    target_dir = os.path.abspath(args.target)
    os.makedirs(target_dir, exist_ok=True)

    min_creation_dt = parse_dateafter(args.dateafter) if args.dateafter else None
    min_seconds = parse_time_duration(args.minlength) if args.minlength else None
    max_seconds = parse_time_duration(args.maxlength) if args.maxlength else None

    print(f"Source : {source_path}")
    print(f"Target : {target_dir}")
    print(f"Parts  : {args.parts}")
    print(f"Pattern: {args.exists_pattern}")
    if args.minlength:
        print(f"Move if shorter than : {args.minlength}")
    if args.maxlength:
        print(f"Ignore if longer than: {args.maxlength}")
    print(f"Logs   → {LOG_DIR}\n")

    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts'}
    candidates = []

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

    print(f"Found {len(candidates)} candidate file(s). Checking durations...\n")

    to_split = []
    moved_count = 0
    ignored_count = 0
    processed = resumed = redone = 0

    for video_file in candidates:
        duration = get_duration(video_file)
        base_name = os.path.basename(video_file)

        # Too long → ignore
        if max_seconds is not None and duration > max_seconds:
            print(f"IGNORED (too long {format_duration(duration)}): {base_name}")
            log_action(video_file, "IGNORED", f"duration > {args.maxlength}")
            ignored_count += 1
            continue

        # Too short → move to target
        if min_seconds is not None and duration < min_seconds:
            dest_path = os.path.join(target_dir, base_name)
            if os.path.exists(dest_path):
                print(f"Short file already in target: {base_name}")
                log_action(video_file, "SKIPPED", "too short, already in target")
            else:
                try:
                    shutil.move(video_file, dest_path)
                    print(f"MOVED (short {format_duration(duration)}): {base_name} → target")
                    log_action(video_file, "MOVED", f"duration < {args.minlength}")
                    moved_count += 1
                except Exception as e:
                    print(f"Failed to move {base_name}: {e}")
            continue

        # Suitable length → will split
        to_split.append(video_file)

    if not to_split:
        print("No files qualify for splitting.")
    else:
        print(f"{len(to_split)} file(s) will be split:\n" + "\n".join(f" • {os.path.basename(f)}" for f in to_split))
        print("\nStarting split process...\n")

        for video_file in to_split:
            base_name, ext = os.path.splitext(os.path.basename(video_file))
            expected = generate_expected_parts(base_name, ext, target_dir, args.parts, args.exists_pattern)
            existing = get_existing_parts(expected)

            if len(existing) == args.parts:
                print(f"Skipping {base_name} – all parts already exist.")
                log_action(video_file, "SKIPPED", "all parts exist")
                continue

            final_parts, status = split_with_ffmpeg(video_file, args.parts, target_dir, args.exists_pattern)

            if status == "already_complete":
                pass
            elif status == "completed_partial":
                resumed += 1
                processed += 1
            elif status == "redone":
                redone += 1
                processed += 1
            else:  # new or incomplete
                processed += 1

    print(f"\n=== Finished ===")
    new_count = processed - resumed - redone
    print(f" Split processed : {processed} (new: {new_count}, resumed: {resumed}, redone: {redone})")
    print(f" Moved (short)   : {moved_count}")
    print(f" Ignored (long)  : {ignored_count}")
    print(f" Target folder   : {target_dir}")
    print(f" Logs in         : {LOG_DIR}")
    print(f" • {os.path.basename(SKIP_LOG_PATH)}")
    print(f" • {os.path.basename(DETAILS_LOG_PATH)}")

if __name__ == "__main__":
    main()