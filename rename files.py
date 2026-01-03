import os
import argparse
import sys

parser = argparse.ArgumentParser(
    description="Batch rename files with flexible replacement options: substring, prefix, or suffix.",
    epilog="""
Examples:
  python rename_files.py -r -o "16k" -n "33k"                     # Replace all occurrences of '16k' with '33k'
  python rename_files.py -p -o "OLD_" -n "NEW_"                   # Replace prefix only
  python rename_files.py -s -o ".temp" -n ""                      # Remove suffix '.temp'
  python rename_files.py -r -o "(320)" -n "" -t "mp3,flac"        # Remove '(320)' from audio files
  python rename_files.py -p -o "TEMP-" -n "" .                    # Remove prefix 'TEMP-'
    """
)

# Mode selection (mutually exclusive group)
mode_group = parser.add_mutually_exclusive_group(required=True)
mode_group.add_argument('-r', '--replace', action='store_true',
                        help="Replace all occurrences of 'old' with 'new' in filename (default behavior if none specified)")
mode_group.add_argument('-p', '--prefix', action='store_true',
                        help="Replace only if 'old' is the prefix (start of filename)")
mode_group.add_argument('-s', '--suffix', action='store_true',
                        help="Replace only if 'old' is the suffix (end of filename)")

parser.add_argument('-o', '--old', required=True, metavar='"old"',
                    help="The string to find and remove/replace (required)")
parser.add_argument('-n', '--new', required=True, metavar='"new"',
                    help="The string to replace with (use empty quotes \"\" to remove)")
parser.add_argument('-t', metavar="ext1,ext2,...",
                    help="Only process files with these extensions (no dot, comma-separated, e.g. mp3,m4a,flac)")
parser.add_argument('directory', nargs='?', default='.',
                    help="Directory to process (default: current directory)")

args = parser.parse_args()

dir_path = args.directory

if not os.path.isdir(dir_path):
    print(f"Error: '{dir_path}' is not a valid directory.")
    sys.exit(1)

# Determine mode
if args.prefix:
    mode = 'prefix'
    mode_name = "Prefix"
elif args.suffix:
    mode = 'suffix'
    mode_name = "Suffix"
else:  # -r or default
    mode = 'replace'
    mode_name = "All occurrences (substring)"

# Parse extensions
extensions = None
if args.t:
    extensions = {ext.strip().lower() for ext in args.t.split(',') if ext.strip()}
    print(f"Processing only extensions: {', '.join(sorted(extensions))}\n")

# Display the operation
print("Replacement rule:\n")
print(f"  Mode:    {mode_name}")
print(f"  Find:    '{args.old}'")
print(f"  Replace: '{args.new}'")
if args.new == "":
    print("           (this will remove the string entirely)\n")
else:
    print()

# Get files
files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]

# Filter by extension
if extensions:
    filtered = []
    for f in files:
        _, ext = os.path.splitext(f)
        if ext[1:].lower() in extensions:
            filtered.append(f)
    files = filtered

if not files:
    print("No matching files found in the directory.")
    sys.exit(0)

# Compute proposed renames
renames = []
skipped = []

for filename in files:
    new_name = filename
    changed = False

    if mode == 'prefix' and filename.startswith(args.old):
        new_name = args.new + filename[len(args.old):]
        changed = True
    elif mode == 'suffix' and filename.endswith(args.old):
        new_name = filename[:-len(args.old)] + args.new
        changed = True
    elif mode == 'replace':
        if args.old in filename:
            new_name = filename.replace(args.old, args.new)
            changed = True

    if changed and new_name != filename:
        target_path = os.path.join(dir_path, new_name)
        if os.path.exists(target_path):
            skipped.append((filename, new_name, "target already exists"))
        else:
            renames.append((filename, new_name))

# Show skipped
if skipped:
    print(f"{len(skipped)} file(s) skipped (target name already exists):\n")
    for old, new, reason in skipped:
        print(f"  {old}  →  {new}  ({reason})")
    print()

# Show planned renames
if not renames:
    print("No files need renaming.")
    sys.exit(0)

print(f"{len(renames)} file(s) will be renamed:\n")
for old, new in renames:
    print(f"  {old}  →  {new}")
print()

# Confirmation with total count
total_to_rename = len(renames)
print(f"Total files to be renamed: {total_to_rename}\n")

while True:
    response = input(f"Proceed with renaming these {total_to_rename} files? [y]es / [n]o / [a]ll (no more prompts) / [c]ancel: ").strip().lower()
    if response in ('y', 'n', 'a', 'c', ''):
        break
    print("Invalid choice. Please enter y, n, a, or c.")

if response in ('n', 'c', ''):
    print("Operation cancelled.")
    sys.exit(0)

ask_each = (response != 'a')

# Perform renaming
renamed_count = 0
for old_name, new_name in renames:
    if ask_each:
        while True:
            ans = input(f"Rename '{old_name}' → '{new_name}'? [y/n/a/c]: ").strip().lower()
            if ans == 'y':
                break
            elif ans == 'n':
                print("  Skipped.")
                old_name = None
                break
            elif ans == 'a':
                ask_each = False
                break
            elif ans == 'c':
                print("Operation cancelled.")
                sys.exit(0)
            else:
                print("  Invalid choice.")
        if old_name is None:
            continue

    old_path = os.path.join(dir_path, old_name)
    new_path = os.path.join(dir_path, new_name)
    try:
        os.rename(old_path, new_path)
        print(f"Renamed: {old_name} → {new_name}")
        renamed_count += 1
    except Exception as e:
        print(f"ERROR renaming {old_name}: {e}")

print(f"\nAll done. {renamed_count} file(s) successfully renamed.")