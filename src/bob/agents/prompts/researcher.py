"""Researcher prompt template module for BF-2 (hide-the-ticket pattern).

Re-exports render_researcher_prompt from the parent package for convenience.
The canonical template text lives in researcher.txt in this directory.
"""

from bob.agents.researcher_prompt import render_researcher_prompt

__all__ = ["render_researcher_prompt"]
