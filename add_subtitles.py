import sys
import os
import subprocess

def print_usage():
    print("Usage: python add_subtitles_ffmpeg.py <input_video.mp4> <subtitles.srt>")
    print("")
    print("Example:")
    print("    python add_subtitles_ffmpeg.py my_video.mp4 my_subs.srt")
    print("")
    print("Output: my_video_with_subs.mp4")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print_usage()
        sys.exit(1)

    video_path = sys.argv[1]
    srt_path = sys.argv[2]

    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    if not os.path.exists(srt_path):
        print(f"Error: SRT file not found: {srt_path}")
        sys.exit(1)

    output_path = video_path.rsplit('.', 1)[0] + '_with_subs.mp4'

    print(f"Adding subtitles from {srt_path} to {video_path}")
    print(f"Output: {output_path}")

    # FFmpeg command: burns subtitles at bottom, good styling, fast copy where possible
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vf', f"subtitles='{srt_path}':force_style='Alignment=10,OutlineColour=&H80000000,BorderStyle=3,Outline=2,Shadow=1,MarginV=30'",
        '-c:v', 'libx264', '-crf', '23', '-preset', 'medium',
        '-c:a', 'copy',
        '-y', output_path
    ]

    subprocess.run(cmd)

    print("Done!")