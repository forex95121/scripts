import os
import argparse
import re

# Regular expression to match a YouTube video ID (exactly 11 alphanumeric/ -_ characters)
# surrounded by underscores: _11chars_
# This avoids matching shorter or longer sequences that might coincidentally be between underscores.
YT_ID_PATTERN = re.compile(r'_([A-Za-z0-9_-]{11})_(?![A-Za-z0-9_-])')

def process_path(path, dry_run=True):
    """Process a single file or directory path."""
    if os.path.isfile(path):
        rename_file(path, dry_run)
    elif os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file in files:
                filepath = os.path.join(root, file)
                rename_file(filepath, dry_run)
    else:
        print(f"Warning: Path does not exist or is not a file/directory: {path}")

def rename_file(filepath, dry_run=True):
    """Rename a single file by removing the YouTube ID pattern."""
    dirname = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    
    new_basename = YT_ID_PATTERN.sub('_', basename)
    
    if new_basename != basename:
        new_filepath = os.path.join(dirname, new_basename)
        print(f"{'[DRY-RUN] Would rename' if dry_run else 'Renaming'}:")
        print(f"  {filepath}")
        print(f"  -> {new_filepath}")
        print()
        
        if not dry_run:
            try:
                os.rename(filepath, new_filepath)
            except Exception as e:
                print(f"Error renaming {filepath}: {e}")
    # If no change, do nothing silently

def main():
    parser = argparse.ArgumentParser(
        description="Rename files by removing YouTube video IDs (11 characters) surrounded by underscores (_videoID_)."
    )
    parser.add_argument(
        '--paths',
        required=True,
        help='Comma-separated list of file/directory paths, or a .txt file containing one path per line.'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually perform the renames. Without this flag, it runs in dry-run mode (shows what would be renamed).'
    )
    
    args = parser.parse_args()
    
    paths_arg = args.paths.strip()
    
    paths_to_process = []
    
    if paths_arg.endswith('.txt'):
        # Treat as a text file containing paths
        if not os.path.isfile(paths_arg):
            print(f"Error: The specified .txt file does not exist: {paths_arg}")
            return
        with open(paths_arg, 'r', encoding='utf-8') as f:
            for line in f:
                path = line.strip()
                if path:
                    paths_to_process.append(path)
    else:
        # Comma-separated list
        paths_to_process = [p.strip() for p in paths_arg.split(',') if p.strip()]
    
    if not paths_to_process:
        print("No valid paths provided.")
        return
    
    dry_run = not args.execute
    
    if dry_run:
        print("DRY-RUN MODE: No files will be renamed.\n")
    
    for path in paths_to_process:
        process_path(path, dry_run)
    
    if dry_run:
        print("Dry-run complete. Use --execute to apply changes.")

if __name__ == '__main__':
    main()