import os
import sys
import subprocess
import glob
import re
import time
import msvcrt


SKIPPED_LIST_FILE = "skipped.txt"


def check_for_key():
    if msvcrt.kbhit():
        key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
        if key in ['s', 'q']:
            return key
    return None


def draw_progress_bar(percent, width=40):
    filled = int(width * percent / 100)
    bar = '█' * filled + ' ' * (width - filled)
    sys.stdout.write(f"\r [{bar}] {percent:3d}%")
    sys.stdout.flush()


def filename_diff_chars(a: str, b: str) -> int:
    max_len = max(len(a), len(b))
    diff = 0
    for i in range(max_len):
        c1 = a[i] if i < len(a) else ''
        c2 = b[i] if i < len(b) else ''
        if c1 != c2:
            diff += 1
    return diff


def prompt_duplicate_action(target_name: str, existing_name: str, timeout_sec: int = 5):
    print(f"\nSimilar filename detected:")
    print(f"  To create: {target_name}")
    print(f"  Existing : {existing_name}")
    print("Press [O] to overwrite, [S] to skip (5s → '-dupli')")
    
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
    print(" → Using '-dupli'\n")
    return "dupli"


def append_to_skipped_list(src_path: str):
    try:
        with open(SKIPPED_LIST_FILE, "a", encoding="utf-8") as f:
            f.write(src_path + "\n")
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


def convert_with_progress(input_file: str, output_file: str, bitrate: str, force: bool = False):
    cmd = ["ffmpeg"]
    if force:
        cmd.append("-y")
    cmd += ["-i", input_file, "-vn", "-ar", "44100", "-ac", "2", "-b:a", bitrate, output_file]

    print(f"Converting: {os.path.basename(input_file)} → {os.path.basename(output_file)}")
    print("Press [s] to skip this file or [q] to quit")

    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
        universal_newlines=True, bufsize=1
    )

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
                try:
                    h, m, s, ms = map(int, match.groups())
                    current = h*3600 + m*60 + s + ms/100
                    if duration and duration > 0:
                        percent = min(100, int(100 * current / duration))
                        draw_progress_bar(percent)
                except:
                    pass

            key = check_for_key()
            if key:
                print(f"\n>>> {'Skipping file' if key=='s' else 'Quitting'} (pressed [{key}])...")
                safe_terminate_process(process)
                remove_partial_file(output_file, "user action")
                
                if key == 'q':
                    raise KeyboardInterrupt
                return "skipped_by_user"

        process.wait()
        rc = process.returncode

    except KeyboardInterrupt:
        safe_terminate_process(process)
        remove_partial_file(output_file, "interrupt")
        raise
    except:
        safe_terminate_process(process)
        remove_partial_file(output_file, "error")

    if rc != 0:
        print("\nConversion failed")
        return False

    print("\nCompleted: 100%")
    return True


def get_input_files(arg: str, keyword: str = None):
    files = []
    if os.path.isfile(arg):
        try:
            with open(arg, "r", encoding="utf-8") as f:
                files = [line.strip() for line in f if line.strip() and os.path.isfile(line.strip())]
        except:
            pass
    elif arg == "":
        exts = ["mp4","m4v","mkv","mov","avi","wmv","flv","webm","mp3","m4a","aac","wav","flac","ogg","wma"]
        for ext in exts:
            files.extend(glob.glob(f"*.{ext}"))
            files.extend(glob.glob(f"*.{ext.upper()}"))
        files = sorted(set(files))
    else:
        parts = [p.strip().lstrip(".") for p in arg.split(",") if p.strip()]
        for ext in parts:
            files.extend(glob.glob(f"*.{ext.lower()}"))
            files.extend(glob.glob(f"*.{ext.upper()}"))
        files = sorted(set(files))

    if keyword:
        files = [f for f in files if keyword.lower() in os.path.basename(f).lower()]
    return files


def get_output_folders(arg: str, num_inputs: int):
    if os.path.isfile(arg):
        try:
            with open(arg, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except:
            return []
    return [arg] * num_inputs


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


def should_skip_for_exact_bitrate(dest: str, base_name: str, bitrate: str):
    """
    Check if MP3 exists with source filename AND exact bitrate suffix like _24k.mp3
    bitrate param: "24k"
    """
    target_suffix = f"_{bitrate}.mp3"  # e.g., "_24k.mp3"
    
    for f in os.listdir(dest):
        if f.lower().endswith('.mp3') and base_name.lower() in f.lower():
            # Check if filename ends exactly with _24k.mp3 (full bitrate match)
            if f.endswith(target_suffix):
                return True
    return False


def main():
    if len(sys.argv) < 4:
        print('Usage: python script.py "mp4,m4a" "output_folder" "24k" [-c|--check] [-f|--force] [-k keyword]')
        return

    input_pat = sys.argv[1]
    output_folder = sys.argv[2]
    bitrate = sys.argv[3]
    
    # Validate bitrate format
    if not bitrate.endswith('k'):
        print(f"Error: Bitrate '{bitrate}' must end with 'k' (24k, 128k, 320k)")
        return

    force = '--force' in sys.argv or '-f' in sys.argv
    check_mode = '--check' in sys.argv or '-c' in sys.argv
    
    keyword = None
    if any(arg.startswith('-k') for arg in sys.argv):
        for i, arg in enumerate(sys.argv):
            if arg.startswith('-k') and len(arg) > 2:
                keyword = arg[2:]
                break
            elif arg == '-k' and i+1 < len(sys.argv):
                keyword = sys.argv[i+1]
                break
    
    # Use skipped.txt in check mode
    if check_mode:
        input_files = load_skipped_file_list()
        print(f"CHECK mode: {len(input_files)} files from {SKIPPED_LIST_FILE}")
    else:
        input_files = get_input_files(input_pat, keyword)
    
    if not input_files:
        print("No input files found")
        return

    input_files.sort(key=lambda p: os.path.getctime(p), reverse=True)
    
    print(f"Found {len(input_files)} files - newest first (bitrate: {bitrate})")
    print("Press [s] to skip file, [q] to quit\n")

    output_folders = get_output_folders(output_folder, len(input_files))
    stats = {"converted": 0, "skipped": 0, "existing_mp3": 0}

    try:
        for i, in_path in enumerate(input_files):
            if i >= len(output_folders):
                print(f"Skip (no folder): {os.path.basename(in_path)}")
                continue

            dest = output_folders[i]
            os.makedirs(dest, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(in_path))[0]
            name = f"{base_name}_{bitrate}.mp3"
            out_path = os.path.join(dest, name)

            # FIXED: Skip ONLY if MP3 exists with source name AND exact _24k.mp3 suffix
            if should_skip_for_exact_bitrate(dest, base_name, bitrate):
                print(f"Skip (exact {bitrate} MP3 exists): {os.path.basename(in_path)}")
                if not check_mode:  # Don't re-add in check mode
                    append_to_skipped_list(os.path.abspath(in_path))
                stats["existing_mp3"] += 1
                continue

            # Note other MP3s with source name but different bitrate
            other_mp3s = [f for f in os.listdir(dest) 
                         if f.lower().endswith('.mp3') and base_name.lower() in f.lower()]
            if other_mp3s and not any(f.endswith(f"_{bitrate}.mp3") for f in other_mp3s):
                print(f"Note: Found {len(other_mp3s)} MP3(s) with '{base_name}' but different bitrate")

            # Check for similar names (<5 char diff)
            similar = None
            n_base = os.path.splitext(name)[0]
            for f in os.listdir(dest):
                if f.lower().endswith('.mp3'):
                    f_base = os.path.splitext(f)[0]
                    if filename_diff_chars(n_base, f_base) < 5:
                        similar = f
                        break

            if similar:
                decision = prompt_duplicate_action(name, similar)
                if decision == "skip":
                    if not check_mode:
                        append_to_skipped_list(os.path.abspath(in_path))
                    stats["skipped"] += 1
                    continue
                elif decision == "overwrite":
                    out_path = os.path.join(dest, similar)
                else:  # dupli
                    dupli_name = f"{n_base}-dupli.mp3"
                    counter = 1
                    while os.path.exists(os.path.join(dest, dupli_name)):
                        dupli_name = f"{n_base}-dupli_{counter}.mp3"
                        counter += 1
                    out_path = os.path.join(dest, dupli_name)

            if os.path.exists(out_path) and not force:
                if not check_mode:
                    append_to_skipped_list(os.path.abspath(in_path))
                stats["skipped"] += 1
                continue

            result = convert_with_progress(in_path, out_path, bitrate, force)
            if result == "skipped_by_user":
                if not check_mode:
                    append_to_skipped_list(os.path.abspath(in_path))
                stats["skipped"] += 1
            elif result:
                stats["converted"] += 1

    except KeyboardInterrupt:
        print("\nStopped by user")

    print(f"\nComplete: {stats['converted']} converted, {stats['skipped']} skipped")
    if stats["existing_mp3"]:
        print(f"{stats['existing_mp3']} had exact {bitrate} MP3s")
    if os.path.exists(SKIPPED_LIST_FILE) and not check_mode:
        print(f"Skipped files saved to: {SKIPPED_LIST_FILE}")


if __name__ == "__main__":
    main()
