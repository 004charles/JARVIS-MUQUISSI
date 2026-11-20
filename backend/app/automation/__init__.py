"""Desktop, project analysis, and web research automation package."""

from app.automation.project_analyzer import analyze_project_directory
from app.automation.web_research import is_safe_public_url, search_web

__all__ = ["analyze_project_directory", "is_safe_public_url", "search_web"]
