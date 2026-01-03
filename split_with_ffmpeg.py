import os
import subprocess
import sys

def get_duration(input_file):
    cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', input_file]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=True)
    return float(result.stdout.strip())

def split_with_ffmpeg(input_file, n_parts):
    if n_parts < 1:
        raise ValueError("Number of parts must be >= 1")
    
    dir_name = os.path.dirname(input_file) or '.'
    base_name, ext = os.path.splitext(os.path.basename(input_file))
    
    print(f"Splitting {input_file} into {n_parts} parts...")
    total_duration = get_duration(input_file)
    part_duration = total_duration / n_parts
    print(f"Total: {total_duration:.1f}s, each part: {part_duration:.1f}s")
    
    for i in range(n_parts):
        start_time = part_duration * i
        out_file = os.path.join(dir_name, f"{base_name} part {i+1} of {n_parts}{ext}")
        
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_time),
            '-i', input_file,
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero'
        ]
        if i < n_parts - 1:
            cmd.extend(['-t', str(part_duration)])
        cmd.append(out_file)
        
        print(f"\n--- Creating {os.path.basename(out_file)} (start {start_time:.1f}s) ---")
        result = subprocess.run(cmd, text=True, shell=True)  # NO capture_output!
        if result.returncode != 0:
            print("FAILED! Check FFmpeg install/PATH.")
            sys.exit(1)
        print("✓ Done")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python split_with_ffmpeg.py <video.mp4> <parts>")
        sys.exit(1)
    split_with_ffmpeg(sys.argv[1], int(sys.argv[2]))
