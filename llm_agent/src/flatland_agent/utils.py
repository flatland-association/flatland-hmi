def context_to_markdown(context: list) -> str:
    """
    Converts a list of ContextMessage objects to a Markdown string for better LLM readability.

    Args:
        context (list): List of ContextMessage objects with 'role' and 'text' attributes.

    Returns:
        str: Markdown-formatted conversation.
    """
    md_lines = []
    for msg in context:
        role = getattr(msg, "role", "unknown").capitalize()
        text = getattr(msg, "text", "").strip()
        md_lines.append(f"**{role}:** {text}\n")
    return "\n".join(md_lines)
