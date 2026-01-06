import os
import argparse
import sys
import re

parser = argparse.ArgumentParser(
    description="Batch rename files with powerful wildcards:\n"
                "  * = any text\n"
                "  # = one or more digits\n"
                "  In --new: #2 = pad captured number to 2 digits, #3 to 3, etc.\n"
                "            # alone = no padding (raw digits)",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
  python rename_files.py -r -o "part2-#" -n "part0#2-2"          # part2-1.mp4 → part01-2.mp4
  python rename_files.py -r -o "S#E#" -n "Season #2 - Episode #2" # S1E5 → Season 01 - Episode 05
  python rename_files.py -r -o "* - [*]" -n "* (*)"              # text wildcard
    """
)

mode_group = parser.add_mutually_exclusive_group(required=True)
mode_group.add_argument('-r', '--replace', action='store_true', help="Replace anywhere in filename")
mode_group.add_argument('-p', '--prefix', action='store_true', help="Match only at start")
mode_group.add_argument('-s', '--suffix', action='store_true', help="Match only at end")

parser.add_argument('-o', '--old', required=True, help="Pattern to match (* = text, # = digits)")
parser.add_argument('-n', '--new', required=True, help="Replacement pattern (use # or #N for padded digits)")
parser.add_argument('-t', '--types', metavar="ext1,ext2", help="Filter by extensions (no dot)")
parser.add_argument('directory', nargs='?', default='.', help="Directory to process")

args = parser.parse_args()

dir_path = args.directory
if not os.path.isdir(dir_path):
    print(f"Error: '{dir_path}' is not a valid directory.")
    sys.exit(1)

mode = 'prefix' if args.prefix else 'suffix' if args.suffix else 'replace'
mode_name = "Prefix" if args.prefix else "Suffix" if args.suffix else "Anywhere"

extensions = None
if args.types:
    extensions = {e.strip().lower() for e in args.types.split(',') if e.strip()}

print("Renaming rule:")
print(f"  Mode : {mode_name}")
print(f"  Find : '{args.old}'")
print(f"  →    : '{args.new}'")
print()

# Build regex from --old pattern
escaped = re.escape(args.old)
regex_str = escaped.replace('\\*', '(.*?)').replace('\\#', '(\\w)')

if mode == 'prefix':
    regex_str = '^' + regex_str
elif mode == 'suffix':
    regex_str = regex_str + '$'

pattern = re.compile(regex_str)

# Extract padding widths from --new (e.g., #2 → 2, # → None)
padding_requests = []
for m in re.finditer(r'#(\d*)', args.new):
    width = int(m.group(1)) if m.group(1) else None
    padding_requests.append(width)

def apply_replacement(filename):
    match = pattern.search(filename) if mode == 'replace' else pattern.fullmatch(filename)
    if not match:
        return filename, False

    groups = list(match.groups())
    new_name = args.new
    group_idx = 0

    # Replace * with captured text
    while '*' in new_name and group_idx < len(groups):
        new_name = new_name.replace('*', groups[group_idx], 1)
        group_idx += 1

    # Replace #N or # with captured/padded digits
    temp = new_name
    new_name = ''
    last_end = 0
    for m in re.finditer(r'#(\d*)', temp):
        width = int(m.group(1)) if m.group(1) else None
        if group_idx >= len(groups):
            break  # safety
        digit_str = groups[group_idx]
        if width is not None and width > 0:
            digit_str = digit_str.zfill(width)
        new_name += temp[last_end:m.start()] + digit_str
        last_end = m.end()
        group_idx += 1
    new_name += temp[last_end:]  # add remaining part

    return new_name, True

# Get files
files = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]

if extensions:
    files = [f for f in files if os.path.splitext(f)[1][1:].lower() in extensions]

if not files:
    print("No files found.")
    sys.exit(0)

# Preview
renames = []
skipped = []

for filename in files:
    new_name, changed = apply_replacement(filename)
    if changed and new_name != filename:
        target_path = os.path.join(dir_path, new_name)
        if os.path.exists(target_path):
            skipped.append((filename, new_name, "target exists"))
        else:
            renames.append((filename, new_name))

if skipped:
    print(f"{len(skipped)} file(s) skipped (name conflict):")
    for old, new, reason in skipped:
        print(f"  {old} → {new} ({reason})")
    print()

if not renames:
    print("No files need renaming.")
    sys.exit(0)

print(f"{len(renames)} file(s) will be renamed:\n")
for old, new in renames:
    print(f"  {old} → {new}")
print()

# Confirmation
while True:
    choice = input(f"Proceed with {len(renames)} rename(s)? [y/n/a/c]: ").strip().lower()
    if choice in ('y', 'n', 'a', 'c', ''):
        break
    print("Invalid input.")

if choice in ('n', 'c', ''):
    print("Cancelled.")
    sys.exit(0)

ask_each = choice != 'a'
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

    src = os.path.join(dir_path, old_name)
    dst = os.path.join(dir_path, new_name)
    try:
        os.rename(src, dst)
        print(f"  Renamed: {old_name} → {new_name}")
        renamed_count += 1
    except Exception as e:
        print(f"  ERROR: {old_name} → {new_name} : {e}")

print(f"\nDone! {renamed_count} file(s) successfully renamed.")