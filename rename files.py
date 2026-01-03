import os
import argparse
import sys

def parse_replace(arg):
    """
    Parse replacement argument.
    Accepts: 'old/new'  or  old/new  (recommended with single quotes in shell)
    Also accepts "old/new" or old-new if no / is used.
    """
    if arg.startswith("'") and arg.endswith("'"):
        arg = arg[1:-1]
    elif arg.startswith('"') and arg.endswith('"'):
        arg = arg[1:-1]
    
    if '/' not in arg and '-' not in arg:
        raise argparse.ArgumentTypeError("Replacement must contain either '/' or '-' as separator")
    if arg.count('/') + arg.count('-') != 1:
        raise argparse.ArgumentTypeError("Replacement must have exactly one separator ('/' or '-')")
    
    if '/' in arg:
        old, new = arg.split('/', 1)
    else:
        old, new = arg.split('-', 1)
    
    return old, new

parser = argparse.ArgumentParser(
    description="Batch rename files with prefix, suffix, or substring replacement.",
    epilog="""
Examples:
  python rename_files.py -r '16k/33k'                  # Replace '16k' with '33k' in filenames
  python rename_files.py -p 'OLD_/NEW_'               # Change prefix using /
  python rename_files.py -r "bad-good" -t "mp4,mp3"   # Works with - and double quotes
    """
)

parser.add_argument('-p', type=parse_replace, metavar="'old/new'", 
                    help="Replace prefix: files starting with 'old' → 'new'")
parser.add_argument('-s', type=parse_replace, metavar="'old/new'", 
                    help="Replace suffix: files ending with 'old' → 'new'")
parser.add_argument('-r', type=parse_replace, metavar="'old/new'", 
                    help="Replace substring: all occurrences of 'old' → 'new'")
parser.add_argument('-t', metavar="ext1,ext2,...", 
                    help="Only process these extensions (no dot, comma-separated)")
parser.add_argument('directory', nargs='?', default='.', 
                    help="Directory to process (default: current directory)")

args = parser.parse_args()

dir_path = args.directory

if not os.path.isdir(dir_path):
    print(f"Error: '{dir_path}' is not a valid directory.")
    sys.exit(1)

# Parse extensions
extensions = None
if args.t:
    extensions = {ext.strip().lower() for ext in args.t.split(',') if ext.strip()}

# Collect and display rules
replacements = []
print("Replacement rules applied:\n")

if args.p:
    old, new = args.p
    print(f"  Prefix:  '{old}'  →  '{new}'")
    replacements.append(('prefix', old, new))

if args.s:
    old, new = args.s
    print(f"  Suffix:  '{old}'  →  '{new}'")
    replacements.append(('suffix', old, new))

if args.r:
    old, new = args.r
    print(f"  Contain: '{old}'  →  '{new}'  (all occurrences)")
    replacements.append(('contain', old, new))

if not replacements:
    print("Error: No replacement option (-p, -s, or -r) provided.")
    parser.print_help()
    sys.exit(1)

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
    print(f"Processing only extensions: {', '.join(sorted(extensions))}\n")

if not files:
    print("No matching files found.")
    sys.exit(0)

# Compute proposed renames
renames = []
skipped = []

for filename in files:
    new_name = filename
    changed = False
    for typ, old, new in replacements:
        if typ == 'prefix' and new_name.startswith(old):
            new_name = new + new_name[len(old):]
            changed = True
        elif typ == 'suffix' and new_name.endswith(old):
            new_name = new_name[:-len(old)] + new
            changed = True
        elif typ == 'contain':
            if old in new_name:
                new_name = new_name.replace(old, new)
                changed = True
    
    if changed and new_name != filename:
        target_path = os.path.join(dir_path, new_name)
        if os.path.exists(target_path):
            skipped.append((filename, new_name, "target exists"))
        else:
            renames.append((filename, new_name))
    # If no change, do nothing

# Show skips first
if skipped:
    print(f"{len(skipped)} file(s) skipped (target name already exists):\n")
    for old, new, reason in skipped:
        print(f"  {old}  →  {new}  ({reason})")
    print()

# Show actual renames
if not renames:
    print("No files need renaming.")
    sys.exit(0)

print(f"{len(renames)} file(s) will be renamed:\n")
for old, new in renames:
    print(f"  {old}  →  {new}")
print()

# Confirmation with total count clearly shown
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