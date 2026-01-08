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

def format_duration(seconds):
    td = timedelta(seconds=float(seconds))
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def log_action(path, action, reason):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SKIP_LOG_PATH, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {action} ({reason}): {os.path.abspath(path)}\n")

def log_detailed_completion(source_file, output_parts):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_abs = os.path.abspath(source_file)
    with open(DETAILS_LOG_PATH, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] COMPLETED SPLIT: {source_abs}\n")
        log.write(f" Source duration: {format_duration(get_duration(source_file))}\n")
        log.write(f" Parts: {len(output_parts)}\n")
        for part_path in output_parts:
            if os.path.exists(part_path):
                dur = get_duration(part_path)
                log.write(f" • {os.path.basename(part_path)} | {format_duration(dur)}\n")
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
Advanced FFmpeg Video Splitter

--minlength  : Files SHORTER than this → MOVED to target
--maxlength  : Files LONGER than this  → IGNORED
Suitable      → SPLIT into parts

Use --dry-run first to preview all actions!
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("parts", type=int, help="Number of parts to split suitable files into")
    parser.add_argument("-k", "--keyword", type=str, default=None, help="Keyword filter")
    parser.add_argument("-p", "--path", type=str, default=".", help="Source directory")
    parser.add_argument("-t", "--target", type=str, required=True, help="Target directory (for parts & moved shorts)")
    parser.add_argument("--dateafter", type=str, default=None, help="Files created after date")
    parser.add_argument("-e", "--exists-pattern", type=str, default="_part_#_of_##", help="Part naming pattern")
    parser.add_argument("--minlength", type=str, default=None, help="Move if SHORTER than this")
    parser.add_argument("--maxlength", type=str, default=None, help="Ignore if LONGER than this")
    parser.add_argument("--dry-run", action="store_true", help="Preview operations only — no changes made")

    args = parser.parse_args()

    if args.dry_run:
        print("DRY-RUN MODE: No files will be moved or split.\n")

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
    print(f"Logs   → {LOG_DIR}")
    if args.dry_run:
        print("\n=== PREVIEW OF PLANNED OPERATIONS ===\n")
    else:
        print()

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

    # Preview / Action collections
    to_move = []
    to_ignore = []
    to_split_new = []
    to_split_resume = []
    to_skip_existing = []

    for video_file in candidates:
        duration = get_duration(video_file)
        base_name = os.path.basename(video_file)
        dur_str = format_duration(duration)

        # Too long → ignore
        if max_seconds is not None and duration > max_seconds:
            to_ignore.append((base_name, dur_str))
            continue

        # Too short → move
        if min_seconds is not None and duration < min_seconds:
            dest_path = os.path.join(target_dir, base_name)
            if os.path.exists(dest_path):
                print(f"[DRY] Short file already in target: {base_name}")
            else:
                to_move.append((base_name, dur_str))
            continue

        # Suitable → check split status
        base, ext = os.path.splitext(base_name)
        expected = generate_expected_parts(base, ext, target_dir, args.parts, args.exists_pattern)
        existing = get_existing_parts(expected)

        if len(existing) == args.parts:
            to_skip_existing.append((base_name, dur_str))
        elif len(existing) > 0:
            to_split_resume.append((base_name, dur_str, len(existing)))
        else:
            to_split_new.append((base_name, dur_str))

    # === DISPLAY PREVIEW ===
    if to_move:
        print("MOVED (short):")
        for name, dur in to_move:
            print(f" • {name} ({dur}) → {target_dir}")
        print()

    if to_ignore:
        print("IGNORED (too long):")
        for name, dur in to_ignore:
            print(f" • {name} ({dur})")
        print()

    if to_split_new or to_split_resume or to_skip_existing:
        print(f"SPLIT into {args.parts} parts → pattern: {args.exists_pattern}")
        if to_split_new:
            for name, dur in to_split_new:
                print(f" • {name} ({dur}) → new split")
        if to_split_resume:
            for name, dur, exist in to_split_resume:
                print(f" • {name} ({dur}) → resume ({exist}/{args.parts} parts exist)")
        if to_skip_existing:
            for name, dur in to_skip_existing:
                print(f" • {name} ({dur}) → skipped (all parts exist)")
        print()

    # Summary
    print("Summary:")
    print(f"  To be MOVED     : {len(to_move)}")
    print(f"  To be IGNORED   : {len(to_ignore)}")
    print(f"  To be SPLIT     : {len(to_split_new) + len(to_split_resume)} (new: {len(to_split_new)}, resume: {len(to_split_resume)})")
    print(f"  To be SKIPPED   : {len(to_skip_existing)}")

    if args.dry_run:
        print("\n--dry-run complete. Remove --dry-run to execute.")
        sys.exit(0)

    # === ACTUAL EXECUTION ===
    print("\n=== EXECUTING ===")
    moved_count = ignored_count = processed = resumed = redone = 0

    # Move short files
    for video_file in candidates:
        duration = get_duration(video_file)
        base_name = os.path.basename(video_file)

        if max_seconds is not None and duration > max_seconds:
            log_action(video_file, "IGNORED", f"duration > {args.maxlength}")
            ignored_count += 1
            continue

        if min_seconds is not None and duration < min_seconds:
            dest_path = os.path.join(target_dir, base_name)
            if os.path.exists(dest_path):
                log_action(video_file, "SKIPPED", "short, already in target")
            else:
                try:
                    shutil.move(video_file, dest_path)
                    print(f"MOVED: {base_name}")
                    log_action(video_file, "MOVED", f"duration < {args.minlength}")
                    moved_count += 1
                except Exception as e:
                    print(f"Move failed: {e}")
            continue

        # Split suitable files
        base, ext = os.path.splitext(base_name)
        expected = generate_expected_parts(base, ext, target_dir, args.parts, args.exists_pattern)
        existing = get_existing_parts(expected)

        if len(existing) == args.parts:
            print(f"SKIPPED: {base_name} (all parts exist)")
            log_action(video_file, "SKIPPED", "all parts exist")
            continue

        final_parts, status = split_with_ffmpeg(video_file, args.parts, target_dir, args.exists_pattern)

        if status == "completed_partial":
            resumed += 1
            processed += 1
        elif status == "redone":
            redone += 1
            processed += 1
        else:
            processed += 1

    print(f"\n=== Finished ===")
    print(f" Moved (short)   : {moved_count}")
    print(f" Ignored (long)  : {ignored_count}")
    print(f" Split processed : {processed} (resumed: {resumed}, redone: {redone})")
    print(f" Skipped (exist) : {len(to_skip_existing)}")
    print(f" Target          : {target_dir}")
    print(f" Logs            : {LOG_DIR}")

if __name__ == "__main__":
    main()