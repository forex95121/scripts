import os
import argparse
import sys


def green(text: str) -> str:
    """Return text in green ANSI color."""
    return f"\033[92m{text}\033[0m"


parser = argparse.ArgumentParser(
    description="Simple batch rename: replace exact text in filenames with new text.\n"
                "Extension is preserved automatically.\n"
                "Supports recursive processing, path lists, and safe interactive renaming.",
    formatter_class=argparse.RawDescriptionHelpFormatter
)

path_group = parser.add_mutually_exclusive_group(required=False)
path_group.add_argument('-p', '--path', help="Single directory path to process. If omitted and no --path-list, uses current directory.")
path_group.add_argument('-l', '--path-list', help="Text file containing directory paths (one per line) to process.")

parser.add_argument('-r', '--recursive', action='store_true',
                    help="Process directories recursively (all subdirectories). Default: top-level files only.")

parser.add_argument('-o', '--old', required=True, help="Exact text to find in filename stem (case-sensitive)")
parser.add_argument('-n', '--new', required=True, help="Text to replace with")
parser.add_argument('-t', '--types', help="Optional: only process these extensions (no dot), comma-separated: mp3,mkv,txt")

args = parser.parse_args()

# Determine directories to process
if args.path:
    directories = [os.path.abspath(args.path)]
elif args.path_list:
    list_path = args.path_list
    if not os.path.isfile(list_path):
        print(f"Error: Path list file '{list_path}' does not exist.")
        sys.exit(1)
    try:
        with open(list_path, 'r', encoding='utf-8') as f:
            directories = [line.strip() for line in f if line.strip()]
        if not directories:
            print(f"Error: Path list file '{list_path}' is empty.")
            sys.exit(1)
        directories = [os.path.abspath(p) for p in directories]
    except Exception as e:
        print(f"Error reading path list: {e}")
        sys.exit(1)
else:
    directories = [os.getcwd()]

# Validate directories
valid_directories = []
for d in directories:
    if os.path.isdir(d):
        valid_directories.append(d)
    else:
        print(f"Warning: Skipping invalid directory '{d}'")

if not valid_directories:
    print("Error: No valid directories to process.")
    sys.exit(1)

extensions = None
if args.types:
    extensions = {e.strip().lower() for e in args.types.split(',') if e.strip()}

print("Simple rename rule:")
print(f" Find    : '{args.old}'")
print(f" Replace : '{args.new}'")
if extensions:
    print(f" Extensions: {', '.join(sorted(extensions))}")
print(f" Mode    : {'Recursive' if args.recursive else 'Top-level only'}")
print(f" Directories: {len(valid_directories)}")
print()

# Collect all matching files across all directories
all_files = []
for dir_path in valid_directories:
    if args.recursive:
        walker = os.walk(dir_path)
    else:
        walker = [(dir_path, [], os.listdir(dir_path))]

    for root, _, files in walker:
        for f in files:
            full_path = os.path.join(root, f)
            if os.path.isfile(full_path):
                all_files.append((root, f))

# Filter by extension if needed
if extensions:
    filtered = []
    for root, filename in all_files:
        ext = os.path.splitext(filename)[1][1:].lower()
        if ext in extensions:
            filtered.append((root, filename))
    all_files = filtered

if not all_files:
    print("No matching files found.")
    sys.exit(0)

# Collect renames (only files containing --old in stem)
renames = []
skipped = []
seen_targets = set()  # prevent conflicts globally

for root, filename in sorted(all_files, key=lambda x: (x[0], x[1])):
    stem, ext = os.path.splitext(filename)
    if args.old not in stem:
        continue  # silent if no match

    new_stem = stem.replace(args.old, args.new)
    new_filename = new_stem + ext

    if new_filename == filename:
        continue  # no change → silent

    target_path = os.path.join(root, new_filename)

    if os.path.exists(target_path) or new_filename in seen_targets:
        skipped.append((root, filename, new_filename))
    else:
        renames.append((root, filename, new_filename))
        seen_targets.add(new_filename)

# Show skipped due to conflict
if skipped:
    print(f"{len(skipped)} file(s) skipped due to name conflict:\n")
    for root, old, new in skipped:
        # Show full path relative to its own root directory
        rel_old = os.path.relpath(os.path.join(root, old), root)
        print(f"  {os.path.join(os.path.basename(root), rel_old)} → {new}  (target exists or conflict)")
    print()

if not renames:
    print("No files need renaming.")
    sys.exit(0)

# Preview renames – show path relative to each file's own directory for clarity
print(f"{len(renames)} file(s) will be renamed:\n")
for root, old, new in renames:
    rel_old = os.path.relpath(os.path.join(root, old), root)
    print(f"  {os.path.join(os.path.basename(root), rel_old)} → {new}")
print()

# Confirmation
while True:
    choice = input("Proceed with renaming? [y/n/all]: ").strip().lower()
    if choice in ('y', 'n', 'all', 'a', ''):
        break
    print("Please enter y, n, or all.")

if choice in ('n', ''):
    print("Operation cancelled.")
    sys.exit(0)

ask_each = choice not in ('all', 'a')
renamed_count = 0

for root, old_name, new_name in renames:
    if ask_each:
        rel_old = os.path.relpath(os.path.join(root, old_name), root)
        display_old = os.path.join(os.path.basename(root), rel_old)
        while True:
            ans = input(f"Rename '{display_old}' → '{new_name}'? [y/n/all/cancel]: ").strip().lower()
            if ans == 'y':
                break
            elif ans == 'n':
                print("  Skipped.")
                continue
            elif ans in ('all', 'a'):
                ask_each = False
                break
            elif ans == 'cancel':
                print("Operation cancelled.")
                sys.exit(0)
            else:
                print("  Invalid input.")
    
    src = os.path.join(root, old_name)
    dst = os.path.join(root, new_name)
    try:
        os.rename(src, dst)
        rel_old = os.path.relpath(src, root)
        display_old = os.path.join(os.path.basename(root), rel_old)
        print(f"  {green('Renamed:')} {display_old} → {new_name}")
        renamed_count += 1
    except Exception as e:
        rel_old = os.path.relpath(src, root)
        display_old = os.path.join(os.path.basename(root), rel_old)
        print(f"  ERROR: {display_old} → {new_name}: {e}")

print(f"\nDone! {renamed_count} file(s) renamed successfully.")