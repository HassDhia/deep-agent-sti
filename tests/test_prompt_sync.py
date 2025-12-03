from pathlib import Path
import re


PROMPT_PATH = Path("analysis_prompts.md")
SERVER_PATH = Path("servers/analysis_server.py")


def _extract_prompt_names(markdown_text: str) -> list[str]:
    return re.findall(r"##\s+(\w+)", markdown_text)


def test_analysis_prompts_match_runtime():
    markdown_text = PROMPT_PATH.read_text(encoding="utf-8")
    server_text = SERVER_PATH.read_text(encoding="utf-8")
    prompt_names = _extract_prompt_names(markdown_text)
    assert prompt_names, "No prompt sections found in analysis_prompts.md"
    for name in prompt_names:
        pattern = re.compile(rf"def\s+{name}\(.*?prompt\s*=\s*_styled_prompt", re.DOTALL)
        assert pattern.search(server_text), f"{name} prompt drift detected in analysis_server.py"
