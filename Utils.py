import os
import re
from collections import Counter


def resolve_file_name_conflict(output_path):
    """
    Resolve naming conflicts by appending a numeric suffix if the file already exists.
    """
    base, ext = os.path.splitext(output_path)
    counter = 1
    while os.path.exists(output_path):
        output_path = f"{base} ({counter}){ext}"
        counter += 1
    return output_path


def analyze_and_generate_filename(file_paths, upload_dir):
    """
    Analyze filenames to find common words and generate a merged filename.

    Args:
        file_paths (list of str): List of file paths to analyze.
        upload_dir (str): Directory to store the merged file.

    Returns:
        str: Generated filename for the merged PDF.
    """
    if not file_paths:
        return os.path.join(upload_dir, "merged.pdf")

    # Extract words from filenames
    words_list = []
    for file_path in file_paths:
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        words = re.findall(r'\b\w+\b', file_name.lower())  # Extract words, ignoring case
        words_list.extend(words)

    # Count word occurrences across all filenames
    word_counts = Counter(words_list)

    # Filter for common words appearing in all filenames
    common_words = [
        word for word, count in word_counts.items() if count == len(file_paths)
    ]

    # Create the merged filename
    if common_words:
        common_part = "_".join(common_words[:3])  # Limit to 3 common words for brevity
        merged_filename = f"{common_part}_merged.pdf"
    else:
        merged_filename = "merged.pdf"

    # Resolve naming conflicts
    merged_file_path = os.path.join(upload_dir, merged_filename)
    merged_file_path = resolve_file_name_conflict(merged_file_path)

    return merged_file_path
