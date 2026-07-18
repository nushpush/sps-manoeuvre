"""Change preview — returns raw file contents for Bob to reason over.

No LLM calls here. Bob receives the file contents and generates the diff itself.
"""

from __future__ import annotations


def build_file_context(file_contents: dict[str, str]) -> str:
    """Format file contents into a readable block for Bob to analyse."""
    if not file_contents:
        return "No matching files found."
    sections = []
    for path, content in file_contents.items():
        sections.append(f"=== {path} ===\n{content}")
    return "\n\n".join(sections)
