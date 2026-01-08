import os
import sys
import subprocess
import glob
import re
import time
import msvcrt
import argparse
import json

SKIPPED_LIST_FILE = "skipped.txt"

def check_for_key():
    if msvcrt.kbhit():
        key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
        if key in ['s', 'q', 'o']:
            return key
    return None

def draw_progress_bar(percent, width=40):
    filled = int(width * percent / 100)
    bar = '█' * filled + ' ' * (width - filled)
    sys.stdout.write(f"\r [{bar}] {percent:3d}%")
    sys.stdout.flush()

def prompt_overwrite_action(target_name: str, existing_name: str, timeout_sec: int = 5):
    print(f"\nFile already exists:")
    print(f"  Existing: {existing_name}")
    print(f"  New file: {target_name}")
    print("Press [O] to overwrite, [S] to skip (auto-skip after 5s)")

    start = time.time()
    while time.time() - start < timeout_sec:
        if msvcrt.kbhit():
            key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
            if key == 'o':
                print(" → Overwrite\n")
                return "overwrite"
            elif key == 's':
                print(" → Skip\n")
                return "skip"
        time.sleep(0.05)
    print(" → Skipping (timeout)\n")
    return "skip"

def append_to_skipped_list(src_path: str):
    try:
        with open(SKIPPED_LIST_FILE, "a", encoding="utf-8") as f:
            f.write(os.path.abspath(src_path) + "\n")
    except OSError:
        pass

def safe_terminate_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

def remove_partial_file(path: str, reason: str = ""):
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"Partial file removed{'' if not reason else f' ({reason})'}.")
        except OSError:
            pass

def get_source_audio_info(input_file: str):
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_entries", "stream=codec_name,bit_rate,sample_rate,channels,profile,duration",
        "-select_streams", "a:0", input_file
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        if data["streams"]:
            s = data["streams"][0]
            codec = s.get("codec_name", "unknown")
            bitrate = s.get("bit_rate")
            if bitrate:
                bitrate = f"{int(bitrate)//1000} kbps"
            else:
                bitrate = "unknown"
            profile = s.get("profile", "")
            sr = s.get("sample_rate", "unknown")
            ch = s.get("channels", "unknown")
            duration = float(s.get("duration", 0))
            return codec, bitrate, f"{sr} Hz, {ch} ch, {profile}", duration
        return "none", "none", "", 0.0
    except Exception:
        return "error", "error", "", 0.0

def get_ffmpeg_audio_args(target_format: str, bitrate: str = None, copy_mode: bool = False):
    if copy_mode:
        args = ["-c:a", "copy"]
        if target_format in ["m4a", "aac"]:
            args += ["-movflags", "+faststart"]
        return args

    target_format = target_format.lower()
    if bitrate and not bitrate.lower().endswith('k'):
        raise ValueError("Bitrate must end with 'k'")

    if target_format == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", bitrate] if bitrate else ["-c:a", "libmp3lame", "-q:a", "2"]
    elif target_format in ["m4a", "aac"]:
        return ["-c:a", "aac", "-b:a", bitrate or "128k", "-movflags", "+faststart"]
    elif target_format == "opus":
        return ["-c:a", "libopus", "-b:a", bitrate or "64k", "-vbr", "on", "-application", "audio"]
    elif target_format == "ogg":
        return ["-c:a", "libvorbis", "-b:a", bitrate or "128k"]
    elif target_format == "flac":
        return ["-c:a", "flac", "-compression_level", "8"]
    elif target_format == "wav":
        return ["-c:a", "pcm_s16le"]
    else:
        raise ValueError(f"Unsupported format: {target_format}")

def should_use_copy(source_codec: str, source_bitrate: int, target_format: str, target_bitrate: str = None):
    target_format = target_format.lower()
    codec_map = {
        "mp3": "mp3",
        "m4a": "aac",
        "aac": "aac",
        "opus": "opus",
        "ogg": "vorbis",
        "flac": "flac",
        "wav": "pcm_s16le"
    }
    expected_codec = codec_map.get(target_format)
    if not expected_codec or source_codec != expected_codec:
        return False

    if target_format in {"flac", "wav"}:
        return True

    if not target_bitrate:
        return True

    target_kbps = int(target_bitrate[:-1])
    if source_bitrate is None:
        return False
    tolerance = 0.20
    return source_bitrate >= target_kbps * (1 - tolerance)

def clean_youtube_filename(base_name: str):
    """Remove everything after the 11-char YouTube ID in double underscore pattern."""
    match = re.search(r'_([a-zA-Z0-9]{11})_', base_name)
    if match:
        vid_id_start = match.start()
        return base_name[:vid_id_start + 12]
    return base_name

def clean_resolution_bitrate_tags(base_name: str):
    """
    Remove:
    - _1080p, _720p, _2160p, etc.
    - _128k, _320k, etc.
    - _001, _002, _123 (exactly 3 digits after underscore)
    """
    # Remove _XXX (exactly 3 digits)
    cleaned = re.sub(r'_\d{3}\b', '', base_name)
    # Remove _XXXp patterns
    cleaned = re.sub(r'(?i)_\d+p\b', '', cleaned)
    # Remove _XXXk patterns
    cleaned = re.sub(r'(?i)_\d+k\b', '', cleaned)
    # Clean up trailing/duplicate underscores
    cleaned = re.sub(r'_+$', '', cleaned)
    cleaned = re.sub(r'_+', '_', cleaned)
    return cleaned.strip('_')

def cleanup_old_dirty_files(dest_folder: str, clean_base: str, bitrate_suffix: str, target_ext: str):
    target_name = f"{clean_base}{bitrate_suffix}.{target_ext}"
    target_path = os.path.join(dest_folder, target_name)

    if os.path.exists(target_path):
        return target_path

    try:
        for old_file in os.listdir(dest_folder):
            if old_file.lower().endswith(f".{target_ext.lower()}") and clean_base in old_file and bitrate_suffix in old_file:
                old_path = os.path.join(dest_folder, old_file)
                if old_path != target_path:
                    print(f"Cleaning old filename: {old_file} → {target_name}")
                    try:
                        os.rename(old_path, target_path)
                        return target_path
                    except OSError as e:
                        print(f"Failed to rename {old_file}: {e}")
        return None
    except Exception:
        return None

def is_incomplete_output(out_path: str, expected_duration: float, target_bitrate_kbps: int = None):
    if not os.path.exists(out_path):
        return False

    actual_size = os.path.getsize(out_path)
    if expected_duration <= 0:
        return False

    if target_bitrate_kbps:
        expected_bits = target_bitrate_kbps * 1000 * expected_duration
    else:
        expected_bits = 128 * 1000 * expected_duration

    expected_bytes = expected_bits / 8
    min_expected = expected_bytes * 0.7

    return actual_size < min_expected

def convert_with_progress(input_file: str, output_file: str, target_format: str,
                          bitrate: str = None, force: bool = False, use_copy: bool = False):
    audio_args = get_ffmpeg_audio_args(target_format, bitrate, use_copy)

    cmd = ["ffmpeg"]
    if force:
        cmd.append("-y")
    cmd += ["-i", input_file, "-vn"] + audio_args + [output_file]

    action = "Copying (instant)" if use_copy else "Converting"
    print(f"{action}: {os.path.basename(input_file)} → {os.path.basename(output_file)}")

    if not use_copy:
        print("Press [S] to skip, [Q] to quit")

    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
        universal_newlines=True, bufsize=1
    )

    if use_copy:
        sys.stdout.write("Working")
        sys.stdout.flush()
        dot_count = 0
        while process.poll() is None:
            line = process.stderr.readline()
            if line:
                pass
            dot_count = (dot_count % 3) + 1
            sys.stdout.write("\rWorking" + "." * dot_count + "   ")
            sys.stdout.flush()
            time.sleep(0.2)
        print("\nCompleted instantly (stream copy)")
        
        if process.returncode != 0:
            print("Copy failed")
            return False
        return True

    duration = None
    time_re = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
    percent = 0

    try:
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break

            if duration is None and "Duration:" in line:
                dur_part = line.split("Duration:")[1].split(",")[0].strip()
                if dur_part != "N/A":
                    try:
                        h, m, s_ms = dur_part.split(":")
                        s, ms = s_ms.split(".")
                        duration = int(h)*3600 + int(m)*60 + int(s) + int(ms)/100
                    except:
                        pass

            match = time_re.search(line)
            if match:
                h, m, s, ms = map(int, match.groups())
                current = h*3600 + m*60 + s + ms/100
                if duration and duration > 0:
                    percent = min(100, int(100 * current / duration))
                    draw_progress_bar(percent)

            key = check_for_key()
            if key == 's':
                print("\n>>> Skipping this file (pressed [S])...")
                safe_terminate_process(process)
                remove_partial_file(output_file, "user skip")
                return "skipped_by_user"
            elif key == 'q':
                print("\n>>> Quitting (pressed [Q])...")
                safe_terminate_process(process)
                remove_partial_file(output_file, "user quit")
                raise KeyboardInterrupt

        process.wait()
        rc = process.returncode

    except KeyboardInterrupt:
        safe_terminate_process(process)
        remove_partial_file(output_file, "interrupt")
        raise
    except Exception:
        safe_terminate_process(process)
        remove_partial_file(output_file, "error")
        return False

    if rc != 0:
        print("\nConversion failed")
        remove_partial_file(output_file, "failed")
        return False

    print("\nCompleted: 100%")
    return True

def get_source_files(source_path: str, keyword: str = None):
    files = []
    if not source_path:
        exts = ["mp4","mkv","mov","avi","webm","flv","wmv","mp3","m4a","aac","wav","flac","ogg","wma","m4v"]
        for ext in exts:
            files.extend(glob.glob(f"*.{ext}"))
            files.extend(glob.glob(f"*.{ext.upper()}"))
    elif os.path.isfile(source_path):
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                files = [line.strip() for line in f if line.strip() and os.path.isfile(line.strip())]
        except:
            print(f"Could not read source list file: {source_path}")
    elif os.path.isdir(source_path):
        exts = ["*.mp4","*.mkv","*.mov","*.avi","*.webm","*.flv","*.wmv",
                "*.mp3","*.m4a","*.aac","*.wav","*.flac","*.ogg","*.wma","*.m4v"]
        for pattern in exts:
            files.extend(glob.glob(os.path.join(source_path, pattern)))
            files.extend(glob.glob(os.path.join(source_path, pattern.upper())))
    else:
        print(f"Source not found: {source_path}")
        return []

    files = sorted(set(files))
    if keyword:
        files = [f for f in files if keyword.lower() in os.path.basename(f).lower()]

    return files

def load_skipped_file_list():
    if not os.path.isfile(SKIPPED_LIST_FILE):
        return []
    paths = []
    try:
        with open(SKIPPED_LIST_FILE, "r", encoding="utf-8") as f:
            for line in f:
                p = line.strip()
                if p and os.path.isfile(p):
                    paths.append(p)
    except:
        pass
    return paths

def main():
    parser = argparse.ArgumentParser(
        description="Smart Generic Audio Converter (with advanced filename cleaning)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python converter.py -s .\\video\\ -d .\\video\\m4a -t m4a -b 128k --cleanName
        """
    )

    parser.add_argument("-s", "--source", default="",
                        help="Source: folder, file list, or empty for current dir")
    parser.add_argument("-d", "--destination", required=True,
                        help="Destination folder (required)")
    parser.add_argument("-t", "--targetFormat", required=True,
                        help="Target format: mp3, m4a, aac, opus, ogg, flac, wav")
    parser.add_argument("-b", "--bitrate",
                        help="Bitrate like '128k' (ignored for flac/wav)")
    parser.add_argument("-f", "--force", action="store_true",
                        help="Force overwrite all existing files")
    parser.add_argument("-c", "--check", action="store_true",
                        help="Process files from skipped.txt")
    parser.add_argument("-k", "--keyword",
                        help="Filter files containing this keyword in filename")
    parser.add_argument("--cleanName", action="store_true",
                        help="Remove _1080p, _720p, _128k, _001, _002 etc. tags from source filename")

    args = parser.parse_args()

    target_format = args.targetFormat.lstrip('.').lower()
    supported = {"mp3", "m4a", "aac", "opus", "ogg", "flac", "wav"}
    if target_format not in supported:
        print(f"Unsupported format: {target_format}")
        print(f"Supported: {', '.join(supported)}")
        return

    if target_format in {"flac", "wav"} and args.bitrate:
        print(f"Note: Bitrate ignored for lossless format '{target_format}'")
        args.bitrate = None

    target_bitrate_k = int(args.bitrate[:-1]) if args.bitrate else None
    bitrate_suffix = f"_{args.bitrate}" if args.bitrate else ""
    target_ext = target_format

    dest_folder = args.destination
    os.makedirs(dest_folder, exist_ok=True)

    if args.check:
        input_files = load_skipped_file_list()
        print(f"CHECK mode: Processing {len(input_files)} files from {SKIPPED_LIST_FILE}")
    else:
        input_files = get_source_files(args.source, args.keyword)

    if not input_files:
        print("No input files found.")
        return

    input_files.sort(key=lambda p: os.path.getctime(p), reverse=True)

    print(f"Found {len(input_files)} files → converting to .{target_format}")
    if args.bitrate:
        print(f"Requested bitrate: {args.bitrate}")
    if args.cleanName:
        print("Extra filename cleaning enabled (--cleanName): removing _1080p, _720p, _128k, _001, _002 etc.")
    print("Processing newest files first.\n")

    stats = {"converted": 0, "copied": 0, "resumed": 0, "renamed": 0, "skipped": 0, "existing": 0}

    try:
        for in_path in input_files:
            orig_base = os.path.splitext(os.path.basename(in_path))[0]

            # Apply cleanings
            base = clean_youtube_filename(orig_base)
            if args.cleanName:
                base = clean_resolution_bitrate_tags(base)

            out_name = f"{base}{bitrate_suffix}.{target_ext}"
            out_path = os.path.join(dest_folder, out_name)

            # Clean up old dirty versions
            cleaned_path = cleanup_old_dirty_files(dest_folder, base, bitrate_suffix, target_ext)
            if cleaned_path:
                out_path = cleaned_path
                stats["renamed"] += 1

            # Diagnostic + duration
            codec, bitrate_str, extra, duration = get_source_audio_info(in_path)
            print(f"Source audio: {codec.upper() if codec != 'error' else 'unknown'} {bitrate_str} ({extra})")

            source_bitrate_k = int(bitrate_str.split()[0]) if bitrate_str.replace(' kbps','').isdigit() else None
            use_copy = should_use_copy(codec, source_bitrate_k, target_format, args.bitrate)

            if use_copy:
                print("Source audio compatible → using instant stream copy (with faststart)")

            # Check existing/complete
            if os.path.exists(out_path) and not args.force:
                if is_incomplete_output(out_path, duration, target_bitrate_k):
                    print(f"Incomplete file detected → resuming conversion")
                else:
                    decision = prompt_overwrite_action(out_name, os.path.basename(out_path))
                    if decision == "skip":
                        if not args.check:
                            append_to_skipped_list(in_path)
                        stats["skipped"] += 1
                        continue
                    else:
                        stats["existing"] += 1
                        continue

            force_this = args.force or is_incomplete_output(out_path, duration, target_bitrate_k)

            result = convert_with_progress(in_path, out_path, target_format, args.bitrate, force_this, use_copy)
            if result == "skipped_by_user":
                if not args.check:
                    append_to_skipped_list(in_path)
                stats["skipped"] += 1
            elif result:
                if is_incomplete_output(out_path, duration, target_bitrate_k):
                    stats["resumed"] += 1
                elif use_copy:
                    stats["copied"] += 1
                else:
                    stats["converted"] += 1

    except KeyboardInterrupt:
        print("\n\nStopped by user.")

    print(f"\n=== Summary ===")
    print(f"Converted (re-encoded): {stats['converted']}")
    print(f"Copied (instant):       {stats['copied']}")
    print(f"Resumed (incomplete):   {stats['resumed']}")
    print(f"Renamed (cleaned up):   {stats['renamed']}")
    print(f"Skipped:                {stats['skipped']}")
    print(f"Existing (complete):    {stats['existing']}")

    if os.path.exists(SKIPPED_LIST_FILE) and not args.check:
        print(f"Skipped files logged to: {SKIPPED_LIST_FILE}")

if __name__ == "__main__":
    main()