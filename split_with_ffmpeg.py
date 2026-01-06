import os
import subprocess
import sys
import argparse
from datetime import datetime, timedelta


def get_duration(input_file):
    """Get duration of video file using ffprobe in seconds."""
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
    """Return file size in KB."""
    try:
        return os.path.getsize(file_path) // 1024
    except OSError:
        return 0


def format_duration(seconds):
    """Convert seconds to HH:MM:SS"""
    td = timedelta(seconds=float(seconds))
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def log_skipped(source_path, reason):
    """Log only skipped files cleanly — no example paths."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("split_with_ffmpeg_skiplog.txt", "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] SKIPPED ({reason}): {os.path.abspath(source_path)}\n")


def log_detailed_completion(source_file, output_parts):
    """Log full details of completed split to split_with_ffmpeg_log_details.txt"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_abs = os.path.abspath(source_file)
    total_size_kb = sum(get_file_size_kb(p) for p in output_parts)

    with open("split_with_ffmpeg_log_details.txt", "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] COMPLETED: {source_abs}\n")
        log.write(f"   Source duration: {format_duration(get_duration(source_file))}\n")
        log.write(f"   Parts created: {len(output_parts)}\n")
        for part_path in output_parts:
            if os.path.exists(part_path):
                dur = get_duration(part_path)
                size_kb = get_file_size_kb(part_path)
                log.write(f"     • {os.path.basename(part_path)}\n")
                log.write(f"       Duration: {format_duration(dur)} | Size: {size_kb:,} KB\n")
            else:
                log.write(f"     • {os.path.basename(part_path)}  [MISSING AFTER RUN!]\n")
        log.write(f"   Total output size: {total_size_kb:,} KB\n")
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
    """Return list of expected parts that already exist on disk."""
    return [p for p in expected_parts if os.path.exists(p)]


def split_with_ffmpeg(input_file, n_parts, target_dir, pattern):
    """Split video, creating only missing parts."""
    os.makedirs(target_dir, exist_ok=True)
    base_name, ext = os.path.splitext(os.path.basename(input_file))
    expected_parts = generate_expected_parts(base_name, ext, target_dir, n_parts, pattern)

    existing_parts = get_existing_parts(expected_parts)
    missing_indices = [i for i, p in enumerate(expected_parts) if p not in existing_parts]

    if not missing_indices:
        # All parts already exist — should not reach here due to pre-check
        return existing_parts, "already_complete"

    print(f"\nSplitting {os.path.basename(input_file)} into {n_parts} parts...")
    total_duration = get_duration(input_file)
    part_duration = total_duration / n_parts
    print(f"Total duration: {format_duration(total_duration)} → Each part ~{format_duration(part_duration)}")

    if len(existing_parts) > 0:
        print(f"   Found {len(existing_parts)} existing part(s) → skipping them")
        if len(missing_indices) == n_parts:
            print("   Warning: No parts found — redoing all")
            status = "redone"
        else:
            print(f"   Creating {len(missing_indices)} missing part(s)")
            status = "completed_partial"
    else:
        print(f"   No existing parts → creating all {n_parts}")
        status = "new"

    created_parts = []

    for i in missing_indices:
        start_time = part_duration * i
        out_file = expected_parts[i]

        cmd = [
            'ffmpeg', '-y',
            '-ss', f"{start_time}",
            '-i', input_file,
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero'
        ]
        if i < n_parts - 1:
            cmd += ['-t', f"{part_duration}"]
        cmd.append(out_file)

        print(f" → Creating: {os.path.basename(out_file)} (start: {format_duration(start_time)})")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("   Done")
            created_parts.append(out_file)
        except subprocess.CalledProcessError:
            print("   FAILED!")
            sys.exit(1)

    # Final list of all parts (existing + newly created)
    final_parts = get_existing_parts(expected_parts)
    all_complete = len(final_parts) == n_parts

    if all_complete:
        log_detailed_completion(input_file, final_parts)
        return final_parts, status
    else:
        print("   Warning: Split incomplete — some parts failed or missing.")
        return final_parts, "incomplete"


def main():
    parser = argparse.ArgumentParser(
        description="""
Advanced FFmpeg Video Splitter (stream copy)

Now with:
• Partial resume support
• Detailed completion log with durations & sizes
• Clean skip log
• Flexible naming via # and ##
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("parts", type=int, help="Number of parts to split into")
    parser.add_argument("-k", "--keyword", type=str, default=None,
                        help="Keyword filter in filename (case-insensitive)")
    parser.add_argument("-p", "--path", type=str, default=".",
                        help="Source directory (default: current)")
    parser.add_argument("-t", "--target", type=str, default=None,
                        help="Target directory (default: same as source)")
    parser.add_argument("--dateafter", type=str, default=None,
                        help="Only files created after yyyymmdd or yyyymmddhhmmss")
    parser.add_argument("-e", "--exists-pattern", type=str, default="_part_#_of_##",
                        help="Naming pattern: # = part num, ## = total (e.g. \"_part#-##\", \"(第#集)\")")

    args = parser.parse_args()

    if "#" not in args.exists_pattern:
        print("Warning: Pattern has no '#' — part numbers may be missing.")

    source_path = os.path.abspath(args.path)
    if not os.path.isdir(source_path):
        print(f"Error: Source path not found: {source_path}")
        sys.exit(1)

    target_dir = os.path.abspath(args.target) if args.target else source_path

    min_creation_dt = None
    if args.dateafter:
        min_creation_dt = parse_dateafter(args.dateafter)

    print(f"Source: {source_path}")
    print(f"Target: {target_dir}")
    print(f"Parts: {args.parts}")
    print(f"Pattern: {args.exists_pattern}\n")

    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts'}

    video_files = []
    for entry in os.listdir(source_path):
        fp = os.path.join(source_path, entry)
        if os.path.isfile(fp):
            _, ext = os.path.splitext(entry.lower())
            if ext in video_extensions:
                if args.keyword and args.keyword.lower() not in entry.lower():
                    continue
                if min_creation_dt:
                    try:
                        if datetime.fromtimestamp(os.path.getctime(fp)) <= min_creation_dt:
                            continue
                    except OSError:
                        pass
                video_files.append(fp)

    if not video_files:
        print("No matching videos found.")
        sys.exit(0)

    print(f"Found {len(video_files)} video(s):\n" + "\n".join(f" • {os.path.basename(f)}" for f in video_files))
    print("\nProcessing...\n")

    processed = skipped = resumed = redone = 0

    for video_file in video_files:
        base_name, ext = os.path.splitext(os.path.basename(video_file))
        expected = generate_expected_parts(base_name, ext, target_dir, args.parts, args.exists_pattern)
        existing = get_existing_parts(expected)

        if len(existing) == args.parts:
            print(f"Skipping {os.path.basename(video_file)} – all {args.parts} parts already exist.")
            log_skipped(video_file, "all parts exist")
            skipped += 1
            continue

        # Proceed to split (will only create missing parts)
        final_parts, status = split_with_ffmpeg(video_file, args.parts, target_dir, args.exists_pattern)

        if status == "already_complete":
            skipped += 1
        elif status == "completed_partial":
            resumed += 1
            processed += 1
        elif status == "redone":
            redone += 1
            processed += 1
        elif status == "new":
            processed += 1

    print(f"\n=== Finished ===")
    print(f" Fully processed: {processed} (new: {processed - resumed - redone}, resumed: {resumed}, redone: {redone})")
    print(f" Skipped (already complete): {skipped}")
    print(f" Parts saved to: {target_dir}")
    print(f" Logs:")
    print(f"   • split_with_ffmpeg_skiplog.txt       → skipped files only")
    print(f"   • split_with_ffmpeg_log_details.txt   → full details of completed splits")


if __name__ == "__main__":
    main()