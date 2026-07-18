"""Raw data structures returned to Bob for analysis.

All LLM reasoning is done by Bob itself — these are plain dataclasses
that the MCP tools populate and return as dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnnouncementAnalysis:
    """Structured representation of a parsed announcement — populated by Bob, not LLM."""
    category: str = ""
    summary: str = ""
    file_patterns: list[str] = field(default_factory=list)
    suggested_change: str = ""
    action_required: bool = True
    raw_message: str = ""
    channel: str = ""
    permalink: str = ""
