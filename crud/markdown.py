"""Render DBML notes as Markdown, the way dbdiagram.io does.

Raw HTML in a note is escaped and unsafe link schemes (javascript: etc.) are refused,
so a note can format text but cannot inject markup or script.
"""

from markdown_it import MarkdownIt
from markupsafe import Markup

# breaks: a single newline in a note stays a line break, as authors expect from DBML notes
_md = MarkdownIt("commonmark", {"html": False, "breaks": True})


def render_markdown(text: str | None) -> Markup:
    return Markup(_md.render(text or ""))
