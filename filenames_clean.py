import os
import argparse
import re
import sys
import subprocess
import json
from collections import defaultdict
from typing import List, Tuple, Dict, Optional

# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RED_BG = '\033[41m'
GREEN_BG = '\033[42m'
RESET = '\033[0m'

def get_audio_bitrate_kbps(filepath: str) -> Optional[int]:
    """Extract audio bitrate in kbps using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=bit_rate", "-of", "json", filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if streams and "bit_rate" in streams[0]:
            bitrate_bps = int(streams[0]["bit_rate"])
            return bitrate_bps // 1000
        return None
    except Exception:
        return None

def compute_base_name(filename: str, clean_option_info: bool, clean_bitrate_info: bool, 
                     clean_resolution_info: bool) -> Tuple[str, str]:
    """Compute base name and extension after cleaning tags."""
    name, ext = os.path.splitext(filename)
    
    if clean_option_info:
        name = re.sub(r'_\d{3}.*', '', name)
    
    if clean_bitrate_info:
        name = re.sub(r'_?\d{2,4}k.*', '', name, flags=re.IGNORECASE)
    
    if clean_resolution_info:
        name = re.sub(r'_\d+p.*', '', name, flags=re.IGNORECASE)
    
    # Final cleanup
    name = re.sub(r'_+', '_', name)
    name = name.strip('_')
    if not name:
        name = "unnamed_file"
    
    return name, ext

def has_bitrate_tag(filename: str) -> bool:
    """Check if filename already contains bitrate tag."""
    return bool(re.search(r'_?\d{2,4}k(?=\.[^.]*$)', filename, re.IGNORECASE))

def highlight_diff(old: str, new: str) -> str:
    """Simple removal-focused diff: removed parts in red background."""
    if old == new:
        return new

    i = j = 0
    result = ""
    while i < len(old) or j < len(new):
        if i < len(old) and j < len(new) and old[i] == new[j]:
            result += old[i]
            i += 1
            j += 1
        elif i < len(old):
            # Removal
            start = i
            while i < len(old) and (j >= len(new) or old[i] != new[j]):
                i += 1
            result += RED_BG + old[start:i] + RESET
        else:
            # Rare addition
            start = j
            while j < len(new):
                j += 1
            result += GREEN_BG + new[start:j] + RESET

    return result

def main():
    parser = argparse.ArgumentParser(
        description="Media filename cleaner with bitrate-based deduplication.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    path_group = parser.add_mutually_exclusive_group()
    path_group.add_argument("-p", "--path", action="append", default=[],
                           help="Directory path to process (can be used multiple times)")
    path_group.add_argument("-l", "--path-list", help="Text file with directory paths (one per line)")

    parser.add_argument("-r", "--recursive", action="store_true",
                       help="Process recursively (all subdirectories). Default: top-level only.")

    parser.add_argument("--cleanOptionInfo", action="store_true",
                       help="Remove _xxx (exactly 3 digits, e.g. _128, _144)")
    parser.add_argument("--cleanBitRateInfo", action="store_true",
                       help="Remove _xxk / _xxxk bitrate tags")
    parser.add_argument("--cleanResolutionInfo", action="store_true",
                       help="Remove resolution tags like _144p, _720p, _33kp, _144p33k etc.")

    parser.add_argument("--dry-run", action="store_true",
                       help="Preview only – no changes")

    args = parser.parse_args()

    # Determine directories
    if args.path_list:
        if not os.path.isfile(args.path_list):
            print(f"Error: Path list '{args.path_list}' not found.")
            sys.exit(1)
        with open(args.path_list, 'r', encoding='utf-8') as f:
            paths = [line.strip() for line in f if line.strip()]
    else:
        paths = args.path if args.path else ["."]

    directories = []
    for p in paths:
        absp = os.path.abspath(p)
        if os.path.isdir(absp):
            directories.append(absp)
        else:
            print(f"Warning: Skipping invalid path '{p}'")

    if not directories:
        print("Error: No valid directories.")
        sys.exit(1)

    print("Active rules:")
    if args.cleanOptionInfo:
        print(f"  Remove _xxx (3 digits)")
    if args.cleanBitRateInfo:
        print(f"  Remove _xxk / _xxxk bitrate")
    if args.cleanResolutionInfo:
        print(f"  Remove _xxxp resolution tags (any digits)")
    print(f"  Mode: {'Recursive' if args.recursive else 'Top-level only'}")
    print(f"  Directories: {len(directories)}")
    if args.dry_run:
        print(f"\n*** DRY RUN – No changes will be made ***")
    print()

    # Collect and analyze files
    files_to_process = []
    for base_dir in directories:
        if args.recursive:
            for root, _, files in os.walk(base_dir):
                for f in files:
                    if f.startswith('.'):
                        continue
                    files_to_process.append(os.path.join(root, f))
        else:
            for f in os.listdir(base_dir):
                full = os.path.join(base_dir, f)
                if os.path.isfile(full) and not f.startswith('.'):
                    files_to_process.append(full)

    if not files_to_process:
        print("No files found.")
        return

    print("Analyzing audio bitrates...")
    
    # Group files by (directory, base_name, extension)
    groups: Dict[Tuple[str, str, str], List[Dict]] = defaultdict(list)
    
    for filepath in files_to_process:
        base_name, ext = compute_base_name(
            os.path.basename(filepath),
            args.cleanOptionInfo,
            args.cleanBitRateInfo,
            args.cleanResolutionInfo
        )
        bitrate_k = get_audio_bitrate_kbps(filepath)
        if bitrate_k is None:
            print(f"Warning: Could not read bitrate for {filepath}")
            continue
            
        groups[(os.path.dirname(filepath), base_name, ext)].append({
            'filepath': filepath,
            'orig_name': os.path.basename(filepath),
            'base_name': base_name,
            'ext': ext,
            'bitrate_k': bitrate_k,
            'has_bitrate_tag': has_bitrate_tag(os.path.basename(filepath)),
            'clean_name': base_name + ext
        })

    # Plan actions
    actions = []  # ("rename"/"delete"/"skip"/"keep", full_path, old_name, new_name)

    for group_key, files in groups.items():
        dir_path, base_name, ext = group_key
        
        # Group by bitrate
        bitrate_groups = defaultdict(list)
        for file_info in files:
            bitrate_groups[file_info['bitrate_k']].append(file_info)
        
        for bitrate_k, bitrate_files in bitrate_groups.items():
            target_name = f"{base_name}_{bitrate_k}k{ext}"
            target_path = os.path.join(dir_path, target_name)
            
            if len(bitrate_files) == 1:
                # Single file - rename to target
                file_info = bitrate_files[0]
                if file_info['orig_name'] != target_name:
                    actions.append(("rename", file_info['filepath'], file_info['orig_name'], target_name))
                else:
                    actions.append(("keep", file_info['filepath'], file_info['orig_name'], target_name))
            else:
                # Multiple files with same bitrate - pick shortest clean name
                candidates = [f for f in bitrate_files if not f['has_bitrate_tag']]
                if not candidates:
                    candidates = bitrate_files  # fallback to any
                
                # Pick shortest clean_name, then lexicographically smallest
                best_file = min(candidates, 
                              key=lambda f: (len(f['clean_name']), f['clean_name']))
                
                # Rename best file
                if best_file['orig_name'] != target_name:
                    actions.append(("rename", best_file['filepath'], best_file['orig_name'], target_name))
                else:
                    actions.append(("keep", best_file['filepath'], best_file['orig_name'], target_name))
                
                # Delete others
                for other_file in bitrate_files:
                    if other_file != best_file:
                        actions.append(("delete", other_file['filepath'], other_file['orig_name'], target_name))

    if not actions:
        print("No changes needed.")
        return

    # Preview
    print(f"{len(actions)} planned change(s):\n")
    for act, full_old, old_name, new_name in actions:
        diff = highlight_diff(old_name, new_name)
        if act == "rename":
            print(f"  {full_old} → {diff}{RESET}")
        elif act == "delete":
            print(f"  {YELLOW}DELETE (duplicate):{RESET} {full_old} → {new_name}")
        elif act == "skip":
            print(f"  {full_old} (larger than existing → kept)")
        elif act == "keep":
            print(f"  {full_old} (already correct)")

    print()

    if args.dry_run:
        print("Dry run complete.")
        return

    # Confirm
    while True:
        ans = input("Proceed? [y/n]: ").lower().strip()
        if ans in ('y', 'n'):
            break
    if ans == 'n':
        print("Cancelled.")
        return

    # Execute
    renamed = deleted = skipped = kept = 0

    for act, full_old, old_name, new_name in actions:
        dir_path = os.path.dirname(full_old)
        new_path = os.path.join(dir_path, new_name)

        try:
            if act == "rename":
                os.rename(full_old, new_path)
                diff = highlight_diff(old_name, new_name)
                print(f"  {GREEN}Renamed:{RESET} {full_old} → {diff}{RESET}")
                renamed += 1
            elif act == "delete":
                os.remove(full_old)
                print(f"  {YELLOW}Deleted (duplicate):{RESET} {full_old}")
                deleted += 1
            elif act == "skip":
                print(f"  {full_old} (kept – better quality)")
                skipped += 1
            elif act == "keep":
                print(f"  {full_old} (already correct)")
                kept += 1
        except Exception as e:
            print(f"  {RED}Error:{RESET} {full_old}: {e}")

    print("\n" + "="*50)
    print(f"Renamed:  {renamed}")
    print(f"Deleted:  {deleted} (duplicates)")
    print(f"Skipped:  {skipped}")
    print(f"Kept:     {kept}")
    print("="*50)

if __name__ == "__main__":
    main()
