"""PDF parsing package: extraction, paragraph merging and optional BabelDOC."""

from .extract import extract_document, parse_pdf

__all__ = ["extract_document", "parse_pdf"]
