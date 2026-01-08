def process_srt(input_path, output_path):
    """
    Removes timing info, indices, and empty lines from an SRT file.
    Each subtitle text becomes one line in the output.
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split the SRT into subtitle blocks (separated by blank lines)
    blocks = content.strip().split('\n\n')

    cleaned_lines = []

    for block in blocks:
        if not block.strip():
            continue

        lines = block.strip().split('\n')

        # Skip the index number (first line if it's a digit)
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]

        # Skip the timing line (the one containing '-->')
        if lines and '-->' in lines[0]:
            lines = lines[1:]

        # Join multi-line subtitles into a single line
        subtitle_text = ' '.join(line.strip() for line in lines if line.strip())

        if subtitle_text:
            cleaned_lines.append(subtitle_text)

    # Write the result (one subtitle per line, no empty lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(cleaned_lines))

# Example usage:
# process_srt('input.srt', 'output.txt')