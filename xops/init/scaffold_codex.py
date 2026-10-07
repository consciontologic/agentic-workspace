#!/usr/bin/env python3
import argparse
import json
import shutil
from pathlib import Path


ROLE_GUIDANCE = {
    "planner": "Plan the requested scope with explicit tests and acceptance gates. Write planning documents only; do not implement code.",
    "implementer": "Implement the entire authorized plan with tests. Run reviewer then verifier at each phase boundary. Report changes to the parent for final tracking and staging.",
    "reviewer": "Review for correctness, regressions, security and missing tests. Return prioritized findings with file references. Do not edit or stage files.",
    "verifier": "Run tests and lint checks and report PASS or FAIL with exact evidence. Test artifacts and logs are allowed; do not edit source or stage files.",
}


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_file(target: Path, relative: str, content: str, dry_run: bool, force: bool) -> None:
    destination = target / relative
    if (destination.exists() or destination.is_symlink()) and not force:
        print(f"  kept user version: {relative}")
        return
    if destination.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink: {destination}")
    if dry_run:
        print(f"  would write: {relative}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    print(f"  wrote: {relative}")


def scaffold(source: Path, target: Path, codex: bool, mcp: bool, skills: bool,
             dry_run: bool, force: bool) -> None:
    def emit(relative: str, content: str) -> None:
        write_file(target, relative, content, dry_run, force)

    server = None
    if mcp:
        config = json.loads((source / ".mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["codegraph"]
        server["args"] += ["--path", str(target)]
        emit(".mcp.json", json.dumps(config, indent=2, ensure_ascii=False) + "\n")

    if not codex:
        return

    instructions = (
        "Read AGENTS.md, CONVENTIONS.md, docs/tracking/context.md and "
        "docs/guides/CODEX_SETUP.md before work. The Codex guide translates "
        "client-specific mechanics, not project policy. Read the instruction files "
        "listed below and apply each when its applyTo scope matches the work. "
        "Use the native tools available in this session, never invent VS Code tools. "
        "Do not commit or push. Use --agent=codex for tracking rows. "
        "Preserve existing human changes.\n"
    )
    instructions += "\n".join(
        str(path.relative_to(source))
        for path in sorted((source / ".github/instructions").glob("*.instructions.md"))
    )
    if not mcp:
        instructions += "\nMCP was explicitly disabled for this scaffold. Use local search/read tools; do not install or initialize CodeGraph automatically."
    if not skills:
        instructions += "\nSkills were explicitly disabled. Use the copied workflow documents directly; do not claim native skill availability."

    config_lines = [
        'approval_policy = "on-request"',
        'sandbox_mode = "workspace-write"',
        f"developer_instructions = {toml_string(instructions)}",
    ]
    if server is not None:
        command = shutil.which("codegraph")
        arguments = ["serve", "--mcp", "--path", str(target)] if command else server["args"]
        config_lines.extend([
            "", "[mcp_servers.codegraph]",
            f"command = {toml_string(command or server['command'])}",
            f"args = {json.dumps(arguments, ensure_ascii=False)}",
            f"cwd = {toml_string(str(target))}",
            "startup_timeout_sec = 60",
        ])
        if server.get("env"):
            config_lines.extend(["", "[mcp_servers.codegraph.env]"])
            config_lines.extend(
                f"{toml_string(key)} = {toml_string(value)}"
                for key, value in sorted(server["env"].items())
            )
    emit(".codex/config.toml", "\n".join(config_lines) + "\n")

    for path in sorted((source / ".github/agents").glob("*.agent.md")):
        name = path.name.removesuffix(".agent.md")
        guidance = ROLE_GUIDANCE.get(name, f"Follow the {name} workflow within the parent's delegated scope.")
        relative = str(path.relative_to(source))
        developer_instructions = (
            instructions + f"\n{guidance}\nRead {relative} for the full role workflow. "
            "Its YAML tool list is Copilot metadata, not a Codex tool allow-list. "
            "Use docs/guides/CODEX_SETUP.md for runtime translation. "
            "Only the coordinating parent appends tracking rows and stages the combined work. "
            "Return evidence to the parent; never discard unrelated changes."
        )
        sandbox = "read-only" if name == "reviewer" else "workspace-write"
        emit(f".codex/agents/{name}.toml", "\n".join([
            f"name = {toml_string(name)}",
            f"description = {toml_string(guidance)}",
            f"sandbox_mode = {toml_string(sandbox)}",
            f"developer_instructions = {toml_string(developer_instructions)}", "",
        ]))

    if skills:
        for path in sorted((source / ".github/prompts").glob("*.prompt.md")):
            name = path.name.removesuffix(".prompt.md")
            skill_name = f"avb-{name}"
            relative = path.relative_to(source)
            emit(f".agents/skills/{skill_name}/SKILL.md", (
                f"---\nname: {skill_name}\n"
                f"description: Run the scaffold {name} workflow when explicitly requested by the user.\n---\n\n"
                f"# {name.replace('-', ' ').title()}\n\n"
                "Read [Codex runtime guidance](../../../docs/guides/CODEX_SETUP.md) first.\n"
                f"Then read and execute the [{name} workflow](../../../{relative}).\n"
                "Treat YAML frontmatter as source metadata, not executable configuration.\n"
                "Use the user's request as the workflow input; translate slash-command references "
                "to the corresponding avb skill. Delegate roles to native Codex agents, "
                "or follow the role inline when delegation is unavailable and permitted.\n"
            ))
            emit(f".agents/skills/{skill_name}/agents/openai.yaml", (
                "policy:\n  allow_implicit_invocation: false\n"
            ))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--codex", action="store_true")
    parser.add_argument("--mcp", action="store_true")
    parser.add_argument("--skills", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    options = parser.parse_args()
    scaffold(options.source, options.target, options.codex, options.mcp,
             options.skills, options.dry_run, options.force)


if __name__ == "__main__":
    main()
