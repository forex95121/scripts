import os
import subprocess
import sys
import argparse
import shutil
import math
from datetime import datetime, timedelta

# --- Color Setup ---
from colorama import init, Fore, Style
init(autoreset=True)

YELLOW = Fore.YELLOW + Style.BRIGHT
GREEN = Fore.GREEN + Style.BRIGHT
RED = Fore.RED + Style.BRIGHT
RESET = Style.RESET_ALL

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

def parse_maxtargetsize(size_str):
    """Parse --maxtargetsize argument (e.g. 500MB, 2.5GB) into bytes."""
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
    print(f"Error: Invalid --maxtargetsize format '{size_str}'. Use e.g. 500MB, 1024MB, 2.5GB")
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
            return datetime.strptime(date_str, "%Y%m%d%H%M%SS")
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

def calculate_parts_from_target_size(file_size_bytes, max_target_bytes):
    """Calculate minimum number of parts >1 so each ≤ max_target_bytes."""
    if file_size_bytes <= max_target_bytes:
        return 1  # Would not split, but caller will skip if <=
    safe_target = max_target_bytes * 0.98
    n_parts = math.ceil(file_size_bytes / safe_target)
    return max(n_parts, 2)

def is_already_a_part(filename, pattern):
    if '#' not in pattern:
        return False
    name_no_ext = os.path.splitext(filename)[0]
    for total_parts in range(2, 100):
        width = len(str(total_parts)) if total_parts >= 10 else 0
        for part_num in range(1, total_parts + 1):
            part_str = f"{part_num:0{width}d}" if width > 0 else str(part_num)
            total_str = f"{total_parts:0{width}d}" if width > 0 else str(total_parts)
            expected_suffix = pattern.replace("##", total_str).replace("#", part_str)
            if name_no_ext.endswith(expected_suffix):
                return True
    return False

def get_base_name_without_suffix(filename, pattern):
    name_no_ext = os.path.splitext(filename)[0]
    for total_parts in range(2, 100):
        width = len(str(total_parts)) if total_parts >= 10 else 0
        for part_num in range(1, total_parts + 1):
            part_str = f"{part_num:0{width}d}" if width > 0 else str(part_num)
            total_str = f"{total_parts:0{width}d}" if width > 0 else str(total_parts)
            expected_suffix = pattern.replace("##", total_str).replace("#", part_str)
            if name_no_ext.endswith(expected_suffix):
                return name_no_ext[:-len(expected_suffix)]
    return None

def move_processed_source(source_file, source_dir):
    current_folder_name = os.path.basename(os.path.normpath(source_dir))
    parent_dir = os.path.dirname(source_dir)
    archive_folder_name = f"{current_folder_name} source"
    archive_path = os.path.join(parent_dir, archive_folder_name)

    try:
        os.makedirs(archive_path, exist_ok=True)
        dest = os.path.join(archive_path, os.path.basename(source_file))
        if os.path.exists(dest):
            base, ext = os.path.splitext(os.path.basename(source_file))
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(archive_path, f"{base}_{counter}{ext}")
                counter += 1
        shutil.move(source_file, dest)
        print(f"   {GREEN}MOVED original →{RESET} {archive_folder_name}/{os.path.basename(dest)}")
        log_action(source_file, "MOVED", f"processed → {archive_path}")
    except Exception as e:
        print(f"   {RED}FAILED to move original:{RESET} {e}")
        log_action(source_file, "MOVE FAILED", str(e))

def check_and_move_original_if_parts_complete(video_file, target_dir, pattern, source_dir, move_processed):
    base_name_no_suffix = get_base_name_without_suffix(os.path.basename(video_file), pattern)
    if base_name_no_suffix is None:
        return False

    possible_n_parts = set()
    target_files = [f for f in os.listdir(target_dir) if f.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts'))]
    for f in target_files:
        base = get_base_name_without_suffix(f, pattern)
        if base == base_name_no_suffix:
            name_no_ext = os.path.splitext(f)[0]
            for total_parts in range(2, 100):
                width = len(str(total_parts)) if total_parts >= 10 else 0
                for part_num in range(1, total_parts + 1):
                    part_str = f"{part_num:0{width}d}" if width > 0 else str(part_num)
                    total_str = f"{total_parts:0{width}d}" if width > 0 else str(total_parts)
                    suffix = pattern.replace("##", total_str).replace("#", part_str)
                    if name_no_ext.endswith(suffix):
                        possible_n_parts.add(total_parts)
                        break

    if not possible_n_parts:
        return False

    n_parts = max(possible_n_parts)
    ext = os.path.splitext(video_file)[1]
    expected_parts = generate_expected_parts(base_name_no_suffix, ext, target_dir, n_parts, pattern)
    existing_parts = get_existing_parts(expected_parts)
    if len(existing_parts) == n_parts:
        print(f"{YELLOW}All {n_parts} parts found for:{RESET} {os.path.basename(video_file)}")
        if move_processed:
            move_processed_source(video_file, source_dir)
        return True
    return False

def split_with_ffmpeg(input_file, n_parts, target_dir, pattern, source_dir, move_processed):
    os.makedirs(target_dir, exist_ok=True)
    base_name, ext = os.path.splitext(os.path.basename(input_file))

    if is_already_a_part(os.path.basename(input_file), pattern):
        print(f"{YELLOW}SKIPPED:{RESET} {os.path.basename(input_file)} (detected as existing split part)")
        log_action(input_file, "SKIPPED", "filename matches part pattern")
        return [], "already_part"

    expected_parts = generate_expected_parts(base_name, ext, target_dir, n_parts, pattern)
    existing_parts = get_existing_parts(expected_parts)
    missing_indices = [i for i, p in enumerate(expected_parts) if p not in existing_parts]

    if not missing_indices:
        return existing_parts, "already_complete"

    total_duration = get_duration(input_file)
    part_duration = total_duration / n_parts

    print(f"\n{YELLOW}Splitting{RESET} {os.path.basename(input_file)} into {n_parts} parts...")
    print(f"Source: {format_size(get_file_size_bytes(input_file))} | Duration: {format_duration(total_duration)}")
    print(f"Each part ~{format_duration(part_duration)}")

    status = "new"
    if len(existing_parts) > 0:
        print(f" Found {len(existing_parts)} existing part(s) → resuming")
        status = "resume"

    for i in missing_indices:
        start_time = part_duration * i
        out_file = expected_parts[i]
        cmd = ['ffmpeg', '-y', '-ss', f"{start_time}", '-i', input_file, '-c', 'copy', '-avoid_negative_ts', 'make_zero']
        if i < n_parts - 1:
            cmd += ['-t', f"{part_duration}"]
        cmd.append(out_file)

        print(f"{YELLOW}→ Creating:{RESET} {os.path.basename(out_file)}", end="")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f" {GREEN}✓{RESET}")
        except subprocess.CalledProcessError:
            print(f" {RED}FAILED!{RESET}")
            sys.exit(1)

    final_parts = get_existing_parts(expected_parts)
    if len(final_parts) == n_parts:
        log_detailed_completion(input_file, final_parts, n_parts)
        if move_processed:
            move_processed_source(input_file, source_dir)
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

When --maxtargetsize is used:
• Files ≤ target size → SKIPPED (no action)
• Files > target size → split into equal parts each ≤ target size
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("parts", type=int, nargs='?', default=2,
                        help="Fixed number of parts (ignored if --maxtargetsize is used)")
    parser.add_argument("-k", "--keyword", type=str, default=None, help="Keyword filter")
    parser.add_argument("-p", "--path", action="append", default=[], help="Source directory (multiple allowed)")
    parser.add_argument("--sourcePaths", action="append", default=[], help="paths.txt or 'path1,path2'")
    parser.add_argument("--targetPath", type=str, required=True, help="Target directory for split parts")
    parser.add_argument("--dateafter", type=str, default=None, help="Files created after date (YYYYMMDD or YYYYMMDDHHMMSS)")
    parser.add_argument("-e", "--exists-pattern", type=str, default="_part_#_of_##", help="Part naming pattern (use # and ##)")
    parser.add_argument("--maxtargetsize", type=str, default=None, help="Only split files LARGER than this size (e.g. 500MB, 2.5GB)")
    parser.add_argument("--moveprocessed", action="store_true", 
                        help="Move processed originals to sibling folder '<folder name> source'")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")

    args = parser.parse_args()

    if args.dry_run:
        print("DRY-RUN MODE: No changes will be made.\n")

    if "#" not in args.exists_pattern:
        print("Warning: Pattern has no '#' → part numbers may not appear correctly.")

    if not args.path and not args.sourcePaths:
        args.path = ["."]

    source_paths = expand_source_paths(args)
    if not source_paths:
        print("Error: No valid source directories.")
        sys.exit(1)

    target_dir = os.path.abspath(args.targetPath)
    os.makedirs(target_dir, exist_ok=True)

    min_creation_dt = parse_dateafter(args.dateafter) if args.dateafter else None
    max_target_bytes = parse_maxtargetsize(args.maxtargetsize) if args.maxtargetsize else None

    print(f"TargetPath     : {target_dir}")
    if max_target_bytes:
        print(f"Only split files > {args.maxtargetsize} ({format_size(max_target_bytes)})")
        print(f"→ Smaller files will be SKIPPED")
        print(f"→ Larger files split so each part ≤ {args.maxtargetsize}")
    else:
        print(f"Fixed parts    : {args.parts}")
    print(f"Pattern        : {args.exists_pattern}")
    if args.moveprocessed:
        print(f"{GREEN}Move processed originals: ENABLED{RESET}")
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
            candidates.append((fp, source_path))

    if not candidates:
        print("No candidate video files found.")
        sys.exit(0)

    to_skip_part = []
    to_skip_small = []
    to_skip_complete = []
    to_split = []
    to_auto_move = []

    for video_file, source_dir in candidates:
        base_name = os.path.basename(video_file)
        size_bytes = get_file_size_bytes(video_file)
        duration = get_duration(video_file)
        dur_str = format_duration(duration)
        sz_str = format_size(size_bytes)

        if is_already_a_part(base_name, args.exists_pattern):
            to_skip_part.append((base_name, dur_str, sz_str))
            continue

        if check_and_move_original_if_parts_complete(video_file, target_dir, args.exists_pattern, source_dir, args.moveprocessed and not args.dry_run):
            to_auto_move.append((base_name, dur_str, sz_str))
            continue

        if max_target_bytes:
            if size_bytes <= max_target_bytes:
                to_skip_small.append((base_name, dur_str, sz_str))
                continue
            n_parts = calculate_parts_from_target_size(size_bytes, max_target_bytes)
        else:
            n_parts = args.parts

        base, ext = os.path.splitext(base_name)
        expected = generate_expected_parts(base, ext, target_dir, n_parts, args.exists_pattern)
        existing = get_existing_parts(expected)

        if len(existing) == n_parts:
            to_skip_complete.append((base_name, dur_str, sz_str))
        else:
            status = "resume" if existing else "new"
            approx_part_size = format_size(size_bytes / n_parts)
            to_split.append((video_file, source_dir, n_parts, status, base_name, dur_str, sz_str, approx_part_size))

    # Preview
    if to_skip_part:
        print(f"{YELLOW}SKIPPED (already a split part):{RESET}")
        for name, dur, sz in to_skip_part:
            print(f" • {name} ({dur}, {sz})")
        print()

    if to_skip_small:
        print(f"{YELLOW}SKIPPED (≤ {args.maxtargetsize if max_target_bytes else 'N/A'}):{RESET}")
        for name, dur, sz in to_skip_small:
            print(f" • {name} ({dur}, {sz})")
        print()

    if to_auto_move:
        print(f"{GREEN}AUTO-MOVED (all parts already exist):{RESET}")
        for name, dur, sz in to_auto_move:
            print(f" • {name} ({dur}, {sz})")
        print()

    if to_skip_complete:
        print("SKIPPED (all parts already exist in target - no move):")
        for name, dur, sz in to_skip_complete:
            print(f" • {name} ({dur}, {sz})")
        print()

    if to_split:
        print("TO BE SPLIT:")
        for _, _, n_parts, status, name, dur, sz, approx in to_split:
            print(f" • {name} ({dur}, {sz}) → {n_parts} parts (~{approx} each, {status})")
        print()

    print("Summary:")
    print(f"  Skip (already a part)         : {len(to_skip_part)}")
    print(f"  Skip (too small)              : {len(to_skip_small)}")
    print(f"  Auto-moved (parts complete)   : {len(to_auto_move)}")
    print(f"  Skip (complete, no move)      : {len(to_skip_complete)}")
    print(f"  Will split                    : {len(to_split)}")

    if args.dry_run:
        print("\nDry-run complete. Remove --dry-run to execute.")
        sys.exit(0)

    # Execution
    print("\n=== EXECUTING ===")
    processed = moved_from_split = 0

    for video_file, source_dir, n_parts, _, base_name, _, _, _ in to_split:
        base, ext = os.path.splitext(base_name)
        expected = generate_expected_parts(base, ext, target_dir, n_parts, args.exists_pattern)

        if len(get_existing_parts(expected)) == n_parts:
            print(f"SKIPPED: {base_name} (all {n_parts} parts now exist)")
            log_action(video_file, "SKIPPED", "all parts exist")
            continue

        result_parts, _ = split_with_ffmpeg(
            video_file, n_parts, target_dir, args.exists_pattern,
            source_dir, args.moveprocessed
        )
        if len(result_parts) == n_parts:
            processed += 1
            if args.moveprocessed and not os.path.exists(video_file):
                moved_from_split += 1

    auto_moved = len(to_auto_move)

    print(f"\n=== Finished ===")
    print(f" Skipped (already a part)       : {len(to_skip_part)}")
    print(f" Skipped (too small)            : {len(to_skip_small)}")
    print(f" Auto-moved (parts complete)    : {auto_moved}")
    print(f" Skipped (complete, no move)    : {len(to_skip_complete)}")
    print(f" Split processed                : {processed}")
    if args.moveprocessed:
        print(f" Moved during/after split       : {moved_from_split + auto_moved}")
    print(f" TargetPath                     : {target_dir}")
    print(f" Logs                           : {LOG_DIR}")

if __name__ == "__main__":
    main()