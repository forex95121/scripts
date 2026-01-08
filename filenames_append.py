import argparse
import os


def green(text: str) -> str:
    return f"\033[92m{text}\033[0m"


def append_after_keyword(directory: str, keyword: str, append_str: str, recursive: bool) -> None:
    """
    Inserts append_str immediately after every occurrence of keyword,
    but ensures that after each keyword there is exactly one append_str
    (removes extra repetitions like '$ $ ' → '$ ').
    Files without the keyword are silent.
    """
    if not keyword:
        raise ValueError("Keyword cannot be empty.")

    if recursive:
        walker = os.walk(directory)
    else:
        walker = [(directory, [], [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])]

    for root, _, files in walker:
        for filename in files:
            file_path = os.path.join(root, filename)
            name, ext = os.path.splitext(filename)

            # Process the name by scanning for keyword and fixing/normalizing append_str after it
            new_name = ""
            i = 0
            changed = False

            while i < len(name):
                if name[i:].startswith(keyword):
                    # Append the keyword itself
                    new_name += keyword
                    i += len(keyword)

                    # Skip over any existing sequence of append_str repetitions
                    repeat_count = 0
                    while name[i:i + len(append_str)] == append_str:
                        i += len(append_str)
                        repeat_count += 1

                    # Decide what to append:
                    if repeat_count == 0:
                        # None present → add one
                        new_name += append_str
                        changed = True
                    elif repeat_count == 1:
                        # Already exactly one → keep it
                        new_name += append_str
                    else:
                        # More than one → keep exactly one (fix repetition)
                        new_name += append_str
                        changed = True
                else:
                    new_name += name[i]
                    i += 1

            if not changed:
                continue  # No keyword or already correct → silent

            new_filename = f"{new_name}{ext}"
            new_file_path = os.path.join(root, new_filename)

            if os.path.exists(new_file_path):
                print(f"Skipping '{file_path}' -> '{new_file_path}' (target already exists)")
                continue

            os.rename(file_path, new_file_path)
            print(f"{green('Renamed:')} '{filename}' -> '{new_filename}' (in {root})")


def normalize_filenames_trailing(directory: str, append_str: str, recursive: bool) -> None:
    """
    Ensures exactly one trailing append_str at the end of the filename (before extension).
    Removes duplicates like '_HD_HD' → '_HD'.
    """
    if recursive:
        walker = os.walk(directory)
    else:
        walker = [(directory, [], [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])]

    for root, _, files in walker:
        for filename in files:
            file_path = os.path.join(root, filename)
            name, ext = os.path.splitext(filename)

            normalized_name = name
            while normalized_name.endswith(append_str):
                normalized_name = normalized_name[:-len(append_str)]

            new_name = f"{normalized_name}{append_str}"
            new_filename = f"{new_name}{ext}"
            new_file_path = os.path.join(root, new_filename)

            if new_filename == filename:
                continue

            if os.path.exists(new_file_path):
                print(f"Skipping '{file_path}' -> '{new_file_path}' (target already exists)")
                continue

            os.rename(file_path, new_file_path)
            print(f"{green('Renamed:')} '{filename}' -> '{new_filename}' (in {root})")


def process_directories(directories: list[str], mode_args, recursive: bool):
    if mode_args.string:
        append_str = mode_args.string
        mode_desc = f"Ensuring exactly one trailing '{append_str}'"
        func = normalize_filenames_trailing
        func_args = (append_str,)
    else:
        keyword, append_str = mode_args.append_after_keyword
        mode_desc = f"Inserting '{append_str}' after every '{keyword}' (fixing repetitions)"
        func = append_after_keyword
        func_args = (keyword, append_str)

    print(f"{mode_desc} {'recursively' if recursive else 'in top-level only'} across {len(directories)} director(ies)...\n")

    for dir_path in directories:
        if not os.path.isdir(dir_path):
            print(f"Warning: Skipping invalid directory '{dir_path}'\n")
            continue
        func(dir_path, *func_args, recursive)

    print("\nOperation completed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename files with smart string appending rules. "
                    "For --append-after-keyword: ensures exactly one append_str after each keyword, removing duplicates like '$ $ '."
    )

    path_group = parser.add_mutually_exclusive_group(required=False)
    path_group.add_argument(
        '-p', '--path',
        help="Single directory path to process. If omitted, uses current working directory."
    )
    path_group.add_argument(
        '-l', '--path-list',
        help="Path to a text file containing directory paths (one per line)."
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help="Process directories recursively. Default: top-level only."
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '-s', '--string',
        help="Ensure this string appears exactly once at the end (before extension)."
    )
    mode_group.add_argument(
        '-k', '--append-after-keyword',
        nargs=2,
        metavar=('KEYWORD', 'APPEND_STR'),
        help="Ensure APPEND_STR appears exactly once after every occurrence of KEYWORD (fixes repetitions)."
    )

    args = parser.parse_args()

    recursive = args.recursive

    if args.path:
        directories = [args.path]
    elif args.path_list:
        list_path = args.path_list
        if not os.path.isfile(list_path):
            print(f"Error: The path list file '{list_path}' does not exist or is not a file.")
            return
        try:
            with open(list_path, 'r', encoding='utf-8') as f:
                directories = [line.strip() for line in f if line.strip()]
            if not directories:
                print(f"Error: The path list file '{list_path}' is empty or contains only blank lines.")
                return
        except Exception as e:
            print(f"Error reading path list file: {e}")
            return
    else:
        directories = [os.getcwd()]

    try:
        process_directories(directories, args, recursive)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()