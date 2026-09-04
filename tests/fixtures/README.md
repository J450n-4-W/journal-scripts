# Regression fixtures

Every case here is a real failure that shipped, not a hypothetical. These tools write
to a live Obsidian vault using regex parsers over free-form markdown, so a bad pattern
corrupts silently rather than crashing — which is exactly what happened four times on
2026-09-03 and again on 09-04.

Run: `python3 tests/run.py`
