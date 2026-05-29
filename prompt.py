from pathlib import Path


def _load_system_prompt() -> str:
    prompt_file = Path(__file__).parent / "system_prompt.md"
    content = prompt_file.read_text()

    # Extract only the ## Prompt section (exclude ## Test Cases)
    lines = content.split("\n")
    in_prompt_section = False
    prompt_lines = []

    for line in lines:
        if line.startswith("## Prompt"):
            in_prompt_section = True
            continue
        elif line.startswith("## ") and in_prompt_section:
            break
        elif in_prompt_section:
            prompt_lines.append(line)

    return "\n".join(prompt_lines).strip()


SYSTEM_PROMPT = _load_system_prompt()
