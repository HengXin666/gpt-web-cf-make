# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "questionary>=2.0.1",
#   "rich>=13.7.0",
# ]
# ///
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import questionary
    from prompt_toolkit.styles import Style
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except Exception:  # pragma: no cover - fallback for direct python execution
    questionary = None
    Style = None
    Console = None
    Panel = None
    Table = None


APP_ID = "hx-ai-cli"
APP_TITLE = "HX-AI-Cli"
DEFAULT_VSCODE_PROFILE_NAME = "HX-AI-Cli"
LEGACY_VSCODE_PROFILE_NAMES = {"AI Workbench"}
CONFIG_FILE = "config.json"
SESSIONS_FILE = "sessions.json"
WORKSPACE_SCRIPT = Path(".ai-cli") / "ai-task.py"
DEFAULT_TASKS_DIR = ".ai-worktrees"
PLAIN_TASK_PREFIX = "aiw"
BACK_CHOICE = "__aiw_back__"
SHELL_COMMANDS = {"bash", "zsh", "sh", "dash", "ksh", "fish"}
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


console = Console() if Console else None

QUESTIONARY_STYLE = (
    Style.from_dict(
        {
            "qmark": "fg:#00afff bold",
            "question": "fg:#00afff bold",
            "answer": "fg:#00d787 bold",
            "pointer": "fg:#00d787 bold",
            "highlighted": "fg:#00d787 bold",
            "selected": "fg:#00d787",
            "separator": "fg:#5f5f5f",
            "instruction": "fg:#808080",
            "text": "",
            "disabled": "fg:#808080 italic",
        }
    )
    if Style
    else None
)


MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "language_prompt": "Choose interface language",
        "language_zh": "Chinese",
        "language_en": "English",
        "workspace": "Workspace",
        "main_prompt": "What do you want to do?",
        "main_continue": "Continue a saved task",
        "main_new": "Start a new independent task",
        "main_configure": "Configure AI CLIs and tools",
        "main_doctor": "Install or check dependencies",
        "main_vscode": "Configure VS Code terminal profile",
        "main_exit": "Exit",
        "git_init_prompt": "Current workspace is not a Git repository. Initialize git here?",
        "worktree_needs_commit": "Git worktree requires at least one commit. Create an initial commit or start without worktree.",
        "starting": "Starting in {cwd}",
        "command_not_found": "Command not found: {command}",
        "no_sessions": "No saved AI sessions yet.",
        "back": "Back",
        "continue_prompt": "Continue which task?",
        "session_status_title": "Saved task status",
        "col_status": "Status",
        "col_task": "Task",
        "col_session": "Session",
        "status_running": "RUNNING",
        "status_stopped": "STOPPED",
        "status_unknown": "UNKNOWN",
        "stopped_task_action": "This task is not running. What do you want to do?",
        "task_action": "What do you want to do with this task?",
        "attach_running": "Open running task",
        "restart_task": "Restart task",
        "attach_shell": "Open its shell",
        "delete_task": "Delete task and cleanup",
        "delete_task_confirm": "Delete saved task '{name}'?",
        "cleanup_worktree_confirm": "Remove worktree {cwd} and branch {branch}?",
        "deleted_task": "Deleted task {name}",
        "removed_worktree": "Removed worktree {cwd}",
        "remove_worktree_failed": "Failed to remove worktree {cwd}: {detail}",
        "remove_branch_failed": "Failed to remove branch {branch}: {detail}",
        "mux_missing_continue": "{mux} is not available. Starting the recorded command directly.",
        "ai_not_found_suffix": " (not found)",
        "configure_ai_clis": "Configure AI CLIs",
        "choose_ai_cli": "Choose AI CLI",
        "selected_ai_no_command": "Selected AI CLI has no command.",
        "task_name": "Task name",
        "create_worktree": "Create an isolated Git worktree for this task?",
        "starting_without_worktree": "Starting without worktree.",
        "created_worktree": "Created worktree {cwd} on branch {branch}",
        "start_current_workspace": "Start in the current workspace instead?",
        "mux_missing_new": "{mux} is not available. Starting directly; this task is still saved for later.",
        "config_table_title": "Configured AI CLIs",
        "col_name": "Name",
        "col_command": "Command",
        "col_enabled": "Enabled",
        "col_detected": "Detected",
        "col_launch": "Launch command",
        "yes": "yes",
        "no": "no",
        "config_path": "Config: {path}",
        "sessions_path": "Sessions: {path}",
        "config_prompt": "Configuration",
        "config_add_ai": "Add AI CLI",
        "config_toggle_ai": "Toggle AI CLI",
        "config_worktree": "Edit worktree defaults",
        "config_tmux": "Edit tmux settings",
        "config_language": "Change language",
        "config_export": "Export config",
        "config_import": "Import config",
        "config_save_exit": "Save and exit",
        "display_name": "Display name",
        "command": "Command",
        "default_args": "Default args",
        "auto_args": "Auto-drive args",
        "auto_mode": "Auto-drive mode",
        "enabled": "enabled",
        "disabled": "disabled",
        "toggle_cli": "Toggle which CLI?",
        "worktree_root": "Worktree root inside repo",
        "branch_prefix": "Branch prefix",
        "multiplexer_command": "Multiplexer command",
        "session_prefix": "Session prefix",
        "edit_launch": "Edit launch command",
        "select_launch_cli": "Edit launch command for which CLI?",
        "launch_command_input": "Executable command",
        "launch_args_input": "Default launch args",
        "launch_auto_args_input": "Auto-drive args",
        "launch_auto_enabled": "Enable auto-drive mode for this CLI?",
        "export_path": "Export path",
        "import_path": "Import path",
        "exported_to": "Exported to {path}",
        "imported_from": "Imported from {path}",
        "saved": "Saved {path}",
        "no_installer": "No safe automatic installer is configured for {tool} on this system.",
        "install_tool": "Install {tool} using: {command}?",
        "tool_check": "Tool Check",
        "col_tool": "Tool",
        "col_required": "Required",
        "col_found": "Found",
        "col_path": "Path",
        "missing": "missing",
        "run_with_uv": "Run with uv for installation prompts: uv run --script aiw.py doctor",
        "install_missing": "Install missing required/optional tools where supported?",
        "vscode_scope_prompt": "Configure VS Code terminal profile where?",
        "vscode_scope_workspace": "Current workspace .vscode/settings.json",
        "vscode_scope_user": "User settings.json",
        "vscode_default_ignored": "Default terminal profile is left unchanged.",
        "updated": "Updated {path}",
        "exported_config": "Exported config to {path}",
        "imported_config": "Imported config from {path}",
        "cancelled": "Cancelled.",
        "invalid_json": "Invalid JSON in {path}: {error}",
        "run_with_uv_script": "Run with uv: uv run --script aiw.py",
        "command_failed": "{command} failed: {detail}",
        "parse_settings_failed": "Could not parse {path}; backup created at {backup}: {error}",
    },
    "zh": {
        "language_prompt": "选择界面语言",
        "language_zh": "中文",
        "language_en": "English",
        "workspace": "工作区",
        "main_prompt": "你想做什么？",
        "main_continue": "继续一个已保存任务",
        "main_new": "新建一个独立任务",
        "main_configure": "配置 AI CLI 和工具",
        "main_doctor": "安装或检查依赖",
        "main_vscode": "配置 VS Code 自定义终端",
        "main_exit": "退出",
        "git_init_prompt": "当前工作区不是 Git 仓库。是否在这里执行 git init？",
        "worktree_needs_commit": "Git worktree 至少需要一个提交。请先创建初始提交，或改为不使用 worktree 启动。",
        "starting": "正在从 {cwd} 启动",
        "command_not_found": "找不到命令：{command}",
        "no_sessions": "还没有保存过的 AI 任务。",
        "back": "返回",
        "continue_prompt": "继续哪个任务？",
        "session_status_title": "已保存任务状态",
        "col_status": "状态",
        "col_task": "任务",
        "col_session": "会话",
        "status_running": "运行中",
        "status_stopped": "已停止",
        "status_unknown": "未知",
        "stopped_task_action": "这个任务当前没有运行。你想怎么处理？",
        "task_action": "你想怎么处理这个任务？",
        "attach_running": "进入运行中的任务",
        "restart_task": "重启任务",
        "attach_shell": "进入它的 shell",
        "delete_task": "删除任务并清理",
        "delete_task_confirm": "删除已保存任务“{name}”？",
        "cleanup_worktree_confirm": "删除 worktree {cwd} 和分支 {branch}？",
        "deleted_task": "已删除任务 {name}",
        "removed_worktree": "已删除 worktree {cwd}",
        "remove_worktree_failed": "删除 worktree {cwd} 失败：{detail}",
        "remove_branch_failed": "删除分支 {branch} 失败：{detail}",
        "mux_missing_continue": "{mux} 不可用。将直接启动已记录的命令。",
        "ai_not_found_suffix": "（未找到）",
        "configure_ai_clis": "配置 AI CLI",
        "choose_ai_cli": "选择 AI CLI",
        "selected_ai_no_command": "选中的 AI CLI 没有配置命令。",
        "task_name": "任务名称",
        "create_worktree": "是否为这个任务创建隔离的 Git worktree？",
        "starting_without_worktree": "将不使用 worktree 启动。",
        "created_worktree": "已创建 worktree：{cwd}，分支：{branch}",
        "start_current_workspace": "是否改为在当前工作区启动？",
        "mux_missing_new": "{mux} 不可用。将直接启动；这个任务仍会保存，方便之后继续。",
        "config_table_title": "已配置的 AI CLI",
        "col_name": "名称",
        "col_command": "命令",
        "col_enabled": "启用",
        "col_detected": "已检测到",
        "col_launch": "启动命令",
        "yes": "是",
        "no": "否",
        "config_path": "配置文件：{path}",
        "sessions_path": "任务记录：{path}",
        "config_prompt": "配置",
        "config_add_ai": "添加 AI CLI",
        "config_toggle_ai": "启用或禁用 AI CLI",
        "config_worktree": "修改 worktree 默认值",
        "config_tmux": "修改 tmux 设置",
        "config_language": "修改语言",
        "config_export": "导出配置",
        "config_import": "导入配置",
        "config_save_exit": "保存并退出",
        "display_name": "显示名称",
        "command": "命令",
        "default_args": "默认参数",
        "auto_args": "自动驾驶参数",
        "auto_mode": "自动驾驶模式",
        "enabled": "已启用",
        "disabled": "已禁用",
        "toggle_cli": "切换哪个 CLI？",
        "worktree_root": "仓库内的 worktree 目录",
        "branch_prefix": "分支前缀",
        "multiplexer_command": "终端复用器命令",
        "session_prefix": "会话名前缀",
        "edit_launch": "修改启动命令",
        "select_launch_cli": "修改哪个 CLI 的启动命令？",
        "launch_command_input": "可执行命令",
        "launch_args_input": "默认启动参数",
        "launch_auto_args_input": "自动驾驶参数",
        "launch_auto_enabled": "是否为这个 CLI 启用自动驾驶模式？",
        "export_path": "导出路径",
        "import_path": "导入路径",
        "exported_to": "已导出到 {path}",
        "imported_from": "已从 {path} 导入",
        "saved": "已保存 {path}",
        "no_installer": "当前系统没有为 {tool} 配置安全的自动安装命令。",
        "install_tool": "是否使用以下命令安装 {tool}：{command}？",
        "tool_check": "工具检查",
        "col_tool": "工具",
        "col_required": "必需",
        "col_found": "找到",
        "col_path": "路径",
        "missing": "缺失",
        "run_with_uv": "如需安装提示，请使用 uv 运行：uv run --script aiw.py doctor",
        "install_missing": "是否安装缺失的必需/可选工具？",
        "vscode_scope_prompt": "把 VS Code 自定义终端配置写到哪里？",
        "vscode_scope_workspace": "当前工作区 .vscode/settings.json",
        "vscode_scope_user": "用户级 settings.json",
        "vscode_default_ignored": "已保持默认终端配置不变。",
        "updated": "已更新 {path}",
        "exported_config": "已导出配置到 {path}",
        "imported_config": "已从 {path} 导入配置",
        "cancelled": "已取消。",
        "invalid_json": "{path} 中的 JSON 无效：{error}",
        "run_with_uv_script": "请使用 uv 运行：uv run --script aiw.py",
        "command_failed": "{command} 执行失败：{detail}",
        "parse_settings_failed": "无法解析 {path}；已创建备份 {backup}：{error}",
    },
}


def language_of(config: dict[str, Any] | None = None) -> str:
    language = (config or {}).get("language")
    return language if language in MESSAGES else "en"


def tr(config: dict[str, Any] | None, key: str, **kwargs: Any) -> str:
    language = language_of(config)
    message = MESSAGES.get(language, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))
    return message.format(**kwargs)


def choose_language(config: dict[str, Any]) -> str:
    choice = ask_select(
        "Choose interface language / 选择界面语言",
        [
            questionary.Choice(title="中文", value="zh"),
            questionary.Choice(title="English", value="en"),
        ],
        default=config.get("language") if config.get("language") in MESSAGES else "zh",
    )
    config["language"] = choice
    return choice


def ensure_language(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("language") not in MESSAGES:
        choose_language(config)
        try:
            save_config(config)
        except OSError:
            pass
    return config


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def print_line(message: str = "") -> None:
    if console:
        console.print(message)
    else:
        print(message)


def print_error(message: str) -> None:
    if console:
        console.print(message, style="bold red")
    else:
        print(message, file=sys.stderr)


def print_success(message: str) -> None:
    if console:
        console.print(message, style="bold green")
    else:
        print(message)


def print_info(message: str) -> None:
    if console:
        console.print(message, style="cyan")
    else:
        print(message)


def platform_id() -> str:
    system = platform.system().lower()
    if system.startswith("darwin"):
        return "macos"
    if system.startswith("windows"):
        return "windows"
    return "linux"


def config_dir() -> Path:
    system = platform_id()
    if system == "windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_ID
        return Path.home() / "AppData" / "Roaming" / APP_ID
    if system == "macos":
        return Path.home() / "Library" / "Application Support" / APP_ID
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_ID
    return Path.home() / ".config" / APP_ID


def config_path() -> Path:
    return config_dir() / CONFIG_FILE


def sessions_path() -> Path:
    return config_dir() / SESSIONS_FILE


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(tr(None, "invalid_json", path=path, error=exc)) from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def executable_candidates(command: str) -> list[Path]:
    home = Path.home()
    candidates: list[Path] = []
    candidates.extend([home / ".local" / "bin" / command, home / ".cargo" / "bin" / command])
    candidates.extend(home.glob(f".nvm/versions/node/*/bin/{command}"))
    candidates.extend(home.glob(f".nvm/versions/node/*/lib/node_modules/*/bin/{command}"))
    candidates.extend(home.glob(f".nvm/versions/node/*/lib/node_modules/*/bin/{command}.js"))
    candidates.extend(home.glob(f".nvm/versions/node/*/lib/node_modules/*/node_modules/*/vendor/*/bin/{command}"))
    return sorted(set(candidates), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)


def discover_executable(command: str, shell: str | None = None) -> str | None:
    if not command:
        return None
    if os.path.sep in command or (os.path.altsep and os.path.altsep in command):
        path = Path(command).expanduser()
        return str(path) if path.exists() and os.access(path, os.X_OK) else None
    resolved = shutil.which(command)
    if resolved:
        return resolved
    for candidate in executable_candidates(command):
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    if platform_id() != "windows":
        lookup_shell = shell or default_shell()
        if Path(lookup_shell).name in SHELL_COMMANDS:
            proc = run_capture([lookup_shell, "-lc", f"command -v {shlex.quote(command)}"])
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip().splitlines()[0]
    return None


def command_exists(command: str) -> bool:
    return discover_executable(command) is not None


def ai_cli_exists(command: str) -> bool:
    path = discover_executable(command)
    if not path:
        return False
    if command == "cc":
        try:
            real_name = Path(path).resolve().name.lower()
        except OSError:
            real_name = Path(path).name.lower()
        if real_name.startswith("gcc") or real_name.startswith("clang"):
            return False
    return True


def resolve_claude_command() -> str:
    if ai_cli_exists("claude"):
        return "claude"
    if ai_cli_exists("cc"):
        return "cc"
    return "claude"


def default_auto_args(command: str) -> list[str]:
    if command == "codex":
        return ["--dangerously-bypass-approvals-and-sandbox"]
    if command in {"claude", "cc"}:
        return ["--dangerously-skip-permissions"]
    return []


def default_shell() -> str:
    if platform_id() == "windows":
        return os.environ.get("COMSPEC", "powershell.exe")
    return os.environ.get("SHELL", "/bin/sh")


def default_config() -> dict[str, Any]:
    return {
        "version": 1,
        "language": None,
        "ai_clis": [
            {
                "name": "Codex",
                "command": "codex",
                "args": [],
                "auto_args": default_auto_args("codex"),
                "auto_mode": True,
                "enabled": ai_cli_exists("codex"),
            },
            {
                "name": "Claude Code",
                "command": resolve_claude_command(),
                "args": [],
                "auto_args": default_auto_args(resolve_claude_command()),
                "auto_mode": True,
                "enabled": ai_cli_exists("claude") or ai_cli_exists("cc"),
            },
            {
                "name": "Gemini",
                "command": "gemini",
                "args": [],
                "auto_args": [],
                "auto_mode": True,
                "enabled": ai_cli_exists("gemini"),
            },
            {
                "name": "Aider",
                "command": "aider",
                "args": [],
                "auto_args": [],
                "auto_mode": True,
                "enabled": ai_cli_exists("aider"),
            },
            {
                "name": "OpenCode",
                "command": "opencode",
                "args": [],
                "auto_args": [],
                "auto_mode": True,
                "enabled": ai_cli_exists("opencode"),
            },
        ],
        "multiplexer": {
            "preferred": "tmux",
            "session_prefix": "aiw",
            "auto_install": True,
        },
        "worktree": {
            "root": DEFAULT_TASKS_DIR,
            "branch_prefix": "ai",
        },
        "vscode": {
            "profile_name": DEFAULT_VSCODE_PROFILE_NAME,
        },
        "shell": default_shell(),
    }


def merge_defaults(config: dict[str, Any]) -> dict[str, Any]:
    merged = default_config()
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value

    merged["ai_clis"] = normalize_ai_clis(merged.get("ai_clis", []))
    known_names = {item.get("name") for item in merged.get("ai_clis", [])}
    for item in default_config()["ai_clis"]:
        if item.get("name") not in known_names:
            merged.setdefault("ai_clis", []).append(item)
    vscode = merged.setdefault("vscode", {})
    if vscode.get("profile_name") in LEGACY_VSCODE_PROFILE_NAMES:
        vscode["profile_name"] = DEFAULT_VSCODE_PROFILE_NAME
    return merged


def normalize_ai_clis(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    claude_item: dict[str, Any] | None = None
    for raw in items:
        item = dict(raw)
        command = item.get("command", "")
        name = item.get("name", "")
        if command in {"claude", "cc"} or name in {"Claude", "Claude Code"}:
            if claude_item is None:
                claude_item = item
            else:
                claude_item["enabled"] = bool(claude_item.get("enabled", True) or item.get("enabled", True))
                if not ai_cli_exists(str(claude_item.get("command", ""))) and ai_cli_exists(str(command)):
                    claude_item["command"] = command
                if not claude_item.get("args") and item.get("args"):
                    claude_item["args"] = item.get("args")
                if not claude_item.get("auto_args") and item.get("auto_args"):
                    claude_item["auto_args"] = item.get("auto_args")
            continue
        normalized.append(ensure_cli_defaults(item))

    if claude_item is not None:
        claude_item["name"] = "Claude Code"
        if not ai_cli_exists(str(claude_item.get("command", ""))):
            claude_item["command"] = resolve_claude_command()
        normalized.append(ensure_cli_defaults(claude_item))
    return normalized


def ensure_cli_defaults(item: dict[str, Any]) -> dict[str, Any]:
    item.setdefault("args", [])
    item.setdefault("auto_mode", True)
    item.setdefault("auto_args", default_auto_args(str(item.get("command", ""))))
    item.setdefault("enabled", ai_cli_exists(str(item.get("command", ""))))
    return item


def load_config() -> dict[str, Any]:
    path = config_path()
    config = merge_defaults(read_json(path, {}))
    if not path.exists():
        try:
            save_config(config)
        except OSError:
            pass
    return config


def save_config(config: dict[str, Any]) -> None:
    write_json(config_path(), config)


def load_sessions() -> list[dict[str, Any]]:
    return read_json(sessions_path(), [])


def save_sessions(sessions: list[dict[str, Any]]) -> None:
    write_json(sessions_path(), sessions)


def require_questionary() -> None:
    if questionary is None:
        raise SystemExit(tr(None, "run_with_uv_script"))


def ask_select(message: str, choices: list[Any], default: Any | None = None) -> Any:
    require_questionary()
    answer = questionary.select(
        message,
        choices=choices,
        default=default,
        use_shortcuts=True,
        style=QUESTIONARY_STYLE,
    ).ask()
    if answer is None:
        raise KeyboardInterrupt
    return answer


def ask_confirm(message: str, default: bool = False) -> bool:
    require_questionary()
    answer = questionary.confirm(message, default=default, auto_enter=False, style=QUESTIONARY_STYLE).ask()
    if answer is None:
        raise KeyboardInterrupt
    return bool(answer)


def ask_text(message: str, default: str = "", validate: Any | None = None) -> str:
    require_questionary()
    answer = questionary.text(message, default=default, validate=validate, style=QUESTIONARY_STYLE).ask()
    if answer is None:
        raise KeyboardInterrupt
    return answer.strip()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = value.strip("-._")
    return value or f"task-{now_stamp()}"


def run_capture(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True)


def run_checked(args: list[str], cwd: Path | None = None) -> None:
    proc = run_capture(args, cwd)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(tr(None, "command_failed", command=" ".join(args), detail=detail))


def git_root(path: Path) -> Path | None:
    if not command_exists("git"):
        return None
    proc = run_capture(["git", "rev-parse", "--show-toplevel"], path)
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return Path(root) if root else None


def git_has_head(repo: Path) -> bool:
    proc = run_capture(["git", "rev-parse", "--verify", "HEAD"], repo)
    return proc.returncode == 0


def git_branch(repo: Path) -> str:
    proc = run_capture(["git", "branch", "--show-current"], repo)
    branch = proc.stdout.strip()
    return branch or "HEAD"


def ensure_git_repo(workspace: Path) -> Path | None:
    root = git_root(workspace)
    if root:
        return root
    config = load_config()
    if not ask_confirm(tr(config, "git_init_prompt"), default=True):
        return None
    run_checked(["git", "init"], workspace)
    return git_root(workspace) or workspace


def create_worktree(repo: Path, task_name: str, config: dict[str, Any]) -> tuple[Path, str]:
    if not git_has_head(repo):
        raise RuntimeError(tr(config, "worktree_needs_commit"))

    slug = slugify(task_name)
    base = repo / config["worktree"].get("root", DEFAULT_TASKS_DIR)
    branch_prefix = config["worktree"].get("branch_prefix", "ai").strip("/")
    branch = f"{branch_prefix}/{slug}"
    target = base / slug
    if target.exists():
        suffix = now_stamp()
        target = base / f"{slug}-{suffix}"
        branch = f"{branch_prefix}/{slug}-{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    run_checked(["git", "worktree", "add", "-b", branch, str(target), "HEAD"], repo)
    return target, branch


def ai_choices(config: dict[str, Any]) -> list[dict[str, Any]]:
    configured = []
    for item in config.get("ai_clis", []):
        if item.get("enabled", True):
            configured.append(item)
    if configured:
        return configured
    return config.get("ai_clis", [])


def ai_command(item: dict[str, Any]) -> list[str]:
    command = item.get("command", "").strip()
    args = item.get("args", [])
    if isinstance(args, str):
        args = shlex.split(args)
    auto_args = item.get("auto_args", []) if item.get("auto_mode", True) else []
    if isinstance(auto_args, str):
        auto_args = shlex.split(auto_args)
    return [command, *args, *auto_args]


def resolve_command_executable(command: list[str], shell: str | None = None) -> list[str]:
    if not command or not command[0]:
        return command
    executable = command[0]
    if os.path.sep in executable or (os.path.altsep and os.path.altsep in executable):
        return command
    resolved = discover_executable(executable, shell)
    if not resolved:
        return command
    return [resolved, *command[1:]]


def base_args(item: dict[str, Any]) -> list[str]:
    args = item.get("args", [])
    if isinstance(args, str):
        return shlex.split(args)
    return list(args)


def auto_args(item: dict[str, Any]) -> list[str]:
    args = item.get("auto_args", [])
    if isinstance(args, str):
        return shlex.split(args)
    return list(args)


def session_name(config: dict[str, Any], task_id: str) -> str:
    prefix = config["multiplexer"].get("session_prefix", PLAIN_TASK_PREFIX)
    return f"{prefix}-{slugify(task_id)}"


def multiplexer_command(config: dict[str, Any]) -> str:
    return config.get("multiplexer", {}).get("preferred", "tmux") or "tmux"


def tmux_available(config: dict[str, Any]) -> bool:
    return command_exists(multiplexer_command(config))


def tmux_has_session(config: dict[str, Any], name: str) -> bool:
    proc = run_capture([multiplexer_command(config), "has-session", "-t", name])
    return proc.returncode == 0


def tmux_current_command(config: dict[str, Any], name: str) -> str | None:
    proc = run_capture([multiplexer_command(config), "display-message", "-p", "-t", name, "#{pane_current_command}"])
    if proc.returncode != 0:
        return None
    command = proc.stdout.strip()
    return command or None


def task_runtime_state(config: dict[str, Any], record: dict[str, Any]) -> str:
    name = record.get("session") or session_name(config, record.get("id", "task"))
    if not tmux_available(config):
        return "unknown"
    if not tmux_has_session(config, name):
        return "stopped"
    current = tmux_current_command(config, name)
    if current is None:
        return "unknown"
    if Path(current).name in SHELL_COMMANDS:
        return "stopped"
    return "running"


def task_status_style(state: str) -> str:
    if state == "running":
        return "green"
    if state == "stopped":
        return "yellow"
    return "red"


def task_status_label(config: dict[str, Any], state: str) -> str:
    return tr(config, f"status_{state}") if state in {"running", "stopped", "unknown"} else state


def show_session_status(config: dict[str, Any], sessions: list[dict[str, Any]]) -> None:
    if not console or not Table:
        for item in sessions:
            state = task_runtime_state(config, item)
            print_line(
                f"[{task_status_label(config, state)}] {item.get('name')} | {item.get('cli_name')} | {item.get('cwd')}"
            )
        return
    table = Table(title=tr(config, "session_status_title"), header_style="bold cyan", border_style="blue")
    table.add_column(tr(config, "col_status"))
    table.add_column(tr(config, "col_task"))
    table.add_column(tr(config, "col_command"))
    table.add_column(tr(config, "col_session"))
    table.add_column("cwd")
    for item in sessions:
        state = task_runtime_state(config, item)
        command = resolve_command_executable(item.get("command", []), config.get("shell") or default_shell())
        table.add_row(
            task_status_label(config, state),
            str(item.get("name", "")),
            " ".join(command),
            str(item.get("session", "")),
            str(item.get("cwd", "")),
            style=task_status_style(state),
        )
    console.print(table)


def tmux_attach_or_create(config: dict[str, Any], name: str, cwd: Path, command: list[str]) -> int:
    tmux = multiplexer_command(config)
    if tmux_has_session(config, name):
        return subprocess.call([tmux, "attach-session", "-t", name])
    command_text = subprocess.list2cmdline(command) if platform_id() == "windows" else " ".join(shell_quote(part) for part in command)
    shell = config.get("shell") or default_shell()
    if platform_id() != "windows" and Path(shell).name in SHELL_COMMANDS:
        command_text = shell_fallback_command(command_text, shell, "AI command")
    return subprocess.call([tmux, "new-session", "-s", name, "-c", str(cwd), command_text])


def shell_quote(value: str) -> str:
    if re.match(r"^[A-Za-z0-9_./:=@+-]+$", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def clean_terminal_title(value: str, default: str = DEFAULT_VSCODE_PROFILE_NAME) -> str:
    title = CONTROL_CHARS_RE.sub(" ", str(value)).strip()
    return title or default


def task_terminal_title(task_name: str) -> str:
    return f"HX[{clean_terminal_title(task_name, 'task')}]"


def set_terminal_title(title: str) -> None:
    if not sys.stdout.isatty():
        return
    sys.stdout.write(f"\033]0;{clean_terminal_title(title)}\007")
    sys.stdout.flush()


def shell_fallback_command(command: str, shell: str, label: str, reset_title: bool = False) -> str:
    quoted_shell = shell_quote(shell)
    quoted_label = shell_quote(label)
    title_command = f"printf '\\033]0;%s\\007' {quoted_label}; " if reset_title else ""
    shell_name = Path(shell).name
    if shell_name == "fish":
        return (
            f"{command}; "
            "set aiw_status $status; "
            f"{title_command}"
            f"printf '\\n%s exited with status %s. Starting shell fallback.\\n' {quoted_label} $aiw_status; "
            f"exec {quoted_shell} -l"
        )
    return (
        f"{command}; "
        "aiw_status=$?; "
        f"{title_command}"
        f"printf '\\n%s exited with status %s. Starting shell fallback.\\n' {quoted_label} \"$aiw_status\"; "
        f"exec {quoted_shell} -l"
    )


def launch_direct(cwd: Path, command: list[str]) -> int:
    print_line(tr(load_config(), "starting", cwd=cwd))
    try:
        return subprocess.call(command, cwd=str(cwd))
    except FileNotFoundError:
        print_error(tr(load_config(), "command_not_found", command=command[0]))
        return 127


def add_session_record(record: dict[str, Any]) -> None:
    sessions = [item for item in load_sessions() if item.get("id") != record.get("id")]
    sessions.insert(0, record)
    save_sessions(sessions[:100])


def remove_session_record(record: dict[str, Any]) -> None:
    save_sessions([item for item in load_sessions() if item.get("id") != record.get("id")])


def remove_worktree_for_record(config: dict[str, Any], record: dict[str, Any]) -> None:
    if record.get("mode") != "worktree":
        return
    cwd_value = str(record.get("cwd", "")).strip()
    if not cwd_value:
        return
    cwd = Path(cwd_value).expanduser()
    branch = record.get("branch")
    if not ask_confirm(tr(config, "cleanup_worktree_confirm", cwd=cwd, branch=branch or "-"), default=True):
        return
    workspace = Path(record.get("workspace", ".")).expanduser()
    repo = git_root(workspace) or workspace
    if cwd.exists():
        proc = run_capture(["git", "worktree", "remove", "--force", str(cwd)], repo)
        if proc.returncode == 0:
            print_success(tr(config, "removed_worktree", cwd=cwd))
        else:
            detail = (proc.stderr or proc.stdout).strip()
            print_error(tr(config, "remove_worktree_failed", cwd=cwd, detail=detail))
    if branch:
        proc = run_capture(["git", "branch", "-D", str(branch)], repo)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            print_error(tr(config, "remove_branch_failed", branch=branch, detail=detail))


def delete_task_record(config: dict[str, Any], record: dict[str, Any]) -> None:
    name = record.get("name", record.get("id", "task"))
    if not ask_confirm(tr(config, "delete_task_confirm", name=name), default=False):
        return
    session = record.get("session")
    if session and tmux_available(config) and tmux_has_session(config, session):
        subprocess.call([multiplexer_command(config), "kill-session", "-t", session])
    remove_worktree_for_record(config, record)
    remove_session_record(record)
    print_success(tr(config, "deleted_task", name=name))


def choose_existing_session(config: dict[str, Any]) -> dict[str, Any] | None:
    sessions = load_sessions()
    if not sessions:
        print_error(tr(config, "no_sessions"))
        return None
    show_session_status(config, sessions)
    choices = []
    for item in sessions:
        state = task_runtime_state(config, item)
        label = f"[{task_status_label(config, state)}] {item.get('name')} | {item.get('cli_name')} | {item.get('cwd')}"
        choices.append(questionary.Choice(title=label, value=item))
    choices.append(questionary.Choice(title=tr(config, "back"), value=BACK_CHOICE))
    selected = ask_select(tr(config, "continue_prompt"), choices)
    return selected if isinstance(selected, dict) else None


def start_existing(config: dict[str, Any]) -> int | None:
    record = choose_existing_session(config)
    if not isinstance(record, dict):
        return None
    command = resolve_command_executable(record.get("command", []), config.get("shell") or default_shell())
    cwd = Path(record.get("cwd", ".")).expanduser()
    name = record.get("session") or session_name(config, record.get("id", "task"))
    if tmux_available(config):
        state = task_runtime_state(config, record)
        has_session = tmux_has_session(config, name)
        if state == "running" and has_session:
            actions = [
                questionary.Choice(title=tr(config, "attach_running"), value="attach"),
                questionary.Choice(title=tr(config, "restart_task"), value="restart"),
                questionary.Choice(title=tr(config, "delete_task"), value="delete"),
                questionary.Choice(title=tr(config, "back"), value=BACK_CHOICE),
            ]
            prompt = tr(config, "task_action")
        else:
            actions = [questionary.Choice(title=tr(config, "restart_task"), value="restart")]
            if has_session:
                actions.append(questionary.Choice(title=tr(config, "attach_shell"), value="attach"))
            actions.extend(
                [
                    questionary.Choice(title=tr(config, "delete_task"), value="delete"),
                    questionary.Choice(title=tr(config, "back"), value=BACK_CHOICE),
                ]
            )
            prompt = tr(config, "stopped_task_action")
        action = ask_select(prompt, actions)
        if action == BACK_CHOICE:
            return None
        if action == "delete":
            delete_task_record(config, record)
            return None
        set_terminal_title(task_terminal_title(str(record.get("name", name))))
        if action == "restart" and has_session:
            subprocess.call([multiplexer_command(config), "kill-session", "-t", name])
        return tmux_attach_or_create(config, name, cwd, command)
    set_terminal_title(task_terminal_title(str(record.get("name", name))))
    print_error(tr(config, "mux_missing_continue", mux=multiplexer_command(config)))
    return launch_direct(cwd, command)


def start_new(config: dict[str, Any], workspace: Path) -> int:
    clis = ai_choices(config)
    choices = []
    for item in clis:
        exists = ai_cli_exists(item.get("command", ""))
        suffix = "" if exists else tr(config, "ai_not_found_suffix")
        choices.append(questionary.Choice(title=f"{item.get('name')} - {' '.join(ai_command(item))}{suffix}", value=item))
    choices.append(questionary.Choice(title=tr(config, "configure_ai_clis"), value="configure"))
    selected = ask_select(tr(config, "choose_ai_cli"), choices)
    if selected == "configure":
        configure_interactive(config)
        config = load_config()
        return start_new(config, workspace)

    command = resolve_command_executable(ai_command(selected), config.get("shell") or default_shell())
    if not command or not command[0]:
        print_error(tr(config, "selected_ai_no_command"))
        return 1

    task_name = ask_text(tr(config, "task_name"), default=f"task-{now_stamp()}")
    set_terminal_title(task_terminal_title(task_name))
    use_worktree = False
    repo = git_root(workspace)
    if repo or command_exists("git"):
        use_worktree = ask_confirm(tr(config, "create_worktree"), default=bool(repo))

    cwd = workspace
    branch = None
    mode = "workspace"
    if use_worktree:
        repo = ensure_git_repo(workspace)
        if repo is None:
            print_error(tr(config, "starting_without_worktree"))
        else:
            try:
                cwd, branch = create_worktree(repo, task_name, config)
                mode = "worktree"
                print_success(tr(config, "created_worktree", cwd=cwd, branch=branch))
            except RuntimeError as exc:
                print_error(str(exc))
                if not ask_confirm(tr(config, "start_current_workspace"), default=True):
                    return 1

    task_id = slugify(f"{task_name}-{now_stamp()}")
    session = session_name(config, task_id)
    record = {
        "id": task_id,
        "name": task_name,
        "cli_name": selected.get("name"),
        "command": command,
        "workspace": str(workspace),
        "cwd": str(cwd),
        "mode": mode,
        "branch": branch,
        "session": session,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    add_session_record(record)

    if tmux_available(config):
        return tmux_attach_or_create(config, session, cwd, command)
    print_error(tr(config, "mux_missing_new", mux=multiplexer_command(config)))
    return launch_direct(cwd, command)


def ensure_workspace_script(workspace: Path) -> Path:
    target = workspace / WORKSPACE_SCRIPT
    source = Path(__file__).resolve()
    try:
        if source == target.resolve():
            return target
    except FileNotFoundError:
        pass

    target.parent.mkdir(parents=True, exist_ok=True)
    source_text = source.read_text(encoding="utf-8")
    if not target.exists() or target.read_text(encoding="utf-8") != source_text:
        target.write_text(source_text, encoding="utf-8")
    return target


def launch_interactive(workspace: Path) -> int:
    config = ensure_language(load_config())
    set_terminal_title(config.get("vscode", {}).get("profile_name", DEFAULT_VSCODE_PROFILE_NAME))
    workspace = workspace.resolve()
    ensure_workspace_script(workspace)
    title = f"{tr(config, 'workspace')}: {workspace}"
    if console and Panel:
        console.print(Panel(title, expand=False, border_style="cyan", title=APP_TITLE))
    else:
        print_line(title)

    while True:
        mode = ask_select(
            tr(config, "main_prompt"),
            [
                questionary.Choice(title=tr(config, "main_continue"), value="continue"),
                questionary.Choice(title=tr(config, "main_new"), value="new"),
                questionary.Choice(title=tr(config, "main_configure"), value="configure"),
                questionary.Choice(title=tr(config, "main_doctor"), value="doctor"),
                questionary.Choice(title=tr(config, "main_vscode"), value="vscode"),
                questionary.Choice(title=tr(config, "main_exit"), value="exit"),
            ],
        )
        if mode == "continue":
            result = start_existing(config)
            if result is None:
                continue
            return result
        if mode == "new":
            return start_new(config, workspace)
        if mode == "configure":
            configure_interactive(config)
            config = ensure_language(load_config())
            continue
        if mode == "doctor":
            doctor_interactive()
            continue
        if mode == "vscode":
            configure_vscode(workspace, set_default=None, scope="ask")
            config = ensure_language(load_config())
            continue
        return 0


def show_config(config: dict[str, Any]) -> None:
    if not console or not Table:
        print_line(json.dumps(config, indent=2, ensure_ascii=False))
        return
    table = Table(title=tr(config, "config_table_title"), header_style="bold cyan", border_style="blue")
    table.add_column(tr(config, "col_name"))
    table.add_column(tr(config, "col_command"))
    table.add_column(tr(config, "col_enabled"))
    table.add_column(tr(config, "col_detected"))
    table.add_column(tr(config, "col_launch"))
    for item in config.get("ai_clis", []):
        cmd = item.get("command", "")
        table.add_row(
            item.get("name", ""),
            cmd,
            tr(config, "yes") if item.get("enabled", True) else tr(config, "no"),
            tr(config, "yes") if ai_cli_exists(cmd) else tr(config, "no"),
            " ".join(ai_command(item)),
        )
    console.print(table)
    print_line(tr(config, "config_path", path=config_path()))


def configure_interactive(config: dict[str, Any] | None = None) -> None:
    config = ensure_language(config or load_config())
    while True:
        show_config(config)
        action = ask_select(
            tr(config, "config_prompt"),
            [
                questionary.Choice(title=tr(config, "config_add_ai"), value="add_ai"),
                questionary.Choice(title=tr(config, "config_toggle_ai"), value="toggle_ai"),
                questionary.Choice(title=tr(config, "edit_launch"), value="edit_launch"),
                questionary.Choice(title=tr(config, "config_worktree"), value="worktree"),
                questionary.Choice(title=tr(config, "config_tmux"), value="tmux"),
                questionary.Choice(title=tr(config, "config_language"), value="language"),
                questionary.Choice(title=tr(config, "config_export"), value="export"),
                questionary.Choice(title=tr(config, "config_import"), value="import"),
                questionary.Choice(title=tr(config, "config_save_exit"), value="save_exit"),
            ],
        )
        if action == "add_ai":
            name = ask_text(tr(config, "display_name"))
            command = ask_text(tr(config, "command"))
            args = ask_text(tr(config, "default_args"), default="")
            config.setdefault("ai_clis", []).append(
                {"name": name, "command": command, "args": args.split(), "enabled": True}
            )
        elif action == "toggle_ai":
            choices = [
                questionary.Choice(
                    title=f"{item.get('name')} - {tr(config, 'enabled') if item.get('enabled', True) else tr(config, 'disabled')}",
                    value=item,
                )
                for item in config.get("ai_clis", [])
            ]
            item = ask_select(tr(config, "toggle_cli"), choices)
            item["enabled"] = not item.get("enabled", True)
        elif action == "edit_launch":
            choices = [
                questionary.Choice(
                    title=f"{item.get('name')} - {' '.join(ai_command(item))}",
                    value=item,
                )
                for item in config.get("ai_clis", [])
            ]
            item = ask_select(tr(config, "select_launch_cli"), choices)
            item["command"] = ask_text(tr(config, "launch_command_input"), str(item.get("command", "")))
            item["args"] = shlex.split(
                ask_text(tr(config, "launch_args_input"), " ".join(base_args(item)))
            )
            default_auto = " ".join(auto_args(item) or default_auto_args(str(item.get("command", ""))))
            item["auto_args"] = shlex.split(ask_text(tr(config, "launch_auto_args_input"), default_auto))
            item["auto_mode"] = ask_confirm(tr(config, "launch_auto_enabled"), default=bool(item.get("auto_mode", True)))
        elif action == "worktree":
            config["worktree"]["root"] = ask_text(tr(config, "worktree_root"), config["worktree"].get("root", DEFAULT_TASKS_DIR))
            config["worktree"]["branch_prefix"] = ask_text(tr(config, "branch_prefix"), config["worktree"].get("branch_prefix", "ai"))
        elif action == "tmux":
            config["multiplexer"]["preferred"] = ask_text(tr(config, "multiplexer_command"), config["multiplexer"].get("preferred", "tmux"))
            config["multiplexer"]["session_prefix"] = ask_text(tr(config, "session_prefix"), config["multiplexer"].get("session_prefix", "aiw"))
        elif action == "language":
            choose_language(config)
        elif action == "export":
            target = Path(ask_text(tr(config, "export_path"), default=str(Path.cwd() / "aiw-config.json"))).expanduser()
            write_json(target, config)
            print_success(tr(config, "exported_to", path=target))
        elif action == "import":
            source = Path(ask_text(tr(config, "import_path"))).expanduser()
            imported = read_json(source, {})
            config = merge_defaults(imported)
            ensure_language(config)
            print_success(tr(config, "imported_from", path=source))
        elif action == "save_exit":
            save_config(config)
            print_success(tr(config, "saved", path=config_path()))
            return


def install_command_for(tool: str) -> list[str] | None:
    system = platform_id()
    if tool == "uv":
        if system == "windows":
            return ["winget", "install", "--id", "astral-sh.uv", "-e"]
        if system == "macos" and command_exists("brew"):
            return ["brew", "install", "uv"]
        if system == "linux":
            if command_exists("brew"):
                return ["brew", "install", "uv"]
            if command_exists("pacman"):
                return ["sudo", "pacman", "-S", "uv"]
            return None
    if tool == "git":
        if system == "windows":
            return ["winget", "install", "--id", "Git.Git", "-e"]
        if system == "macos" and command_exists("brew"):
            return ["brew", "install", "git"]
        if system == "linux":
            if command_exists("apt"):
                return ["sudo", "apt", "install", "-y", "git"]
            if command_exists("dnf"):
                return ["sudo", "dnf", "install", "-y", "git"]
            if command_exists("pacman"):
                return ["sudo", "pacman", "-S", "git"]
            if command_exists("zypper"):
                return ["sudo", "zypper", "install", "-y", "git"]
    if tool == "tmux":
        if system == "windows":
            if command_exists("scoop"):
                return ["scoop", "install", "tmux"]
            return None
        if system == "macos" and command_exists("brew"):
            return ["brew", "install", "tmux"]
        if system == "linux":
            if command_exists("apt"):
                return ["sudo", "apt", "install", "-y", "tmux"]
            if command_exists("dnf"):
                return ["sudo", "dnf", "install", "-y", "tmux"]
            if command_exists("pacman"):
                return ["sudo", "pacman", "-S", "tmux"]
            if command_exists("zypper"):
                return ["sudo", "zypper", "install", "-y", "tmux"]
    return None


def install_missing_tools(tools: list[str]) -> None:
    config = load_config()
    for tool in tools:
        if command_exists(tool):
            continue
        command = install_command_for(tool)
        if not command:
            print_error(tr(config, "no_installer", tool=tool))
            continue
        if ask_confirm(tr(config, "install_tool", tool=tool, command=" ".join(command)), default=True):
            subprocess.call(command)


def collect_doctor_status() -> list[dict[str, str]]:
    required = ["uv", "git"]
    optional = ["tmux"]
    rows = []
    ai_tools = ["codex", "cc", "claude", "gemini", "aider", "opencode"]
    for tool in [*required, *optional, *ai_tools]:
        path = discover_executable(tool)
        found = command_exists(tool) if tool not in ai_tools else ai_cli_exists(tool)
        rows.append(
            {
                "tool": tool,
                "required": "yes" if tool in required else "no",
                "found": "yes" if found else "no",
                "path": path or "",
            }
        )
    return rows


def doctor_interactive(json_output: bool = False) -> None:
    config = load_config()
    rows = collect_doctor_status()
    if json_output:
        print_line(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if questionary is not None:
        config = ensure_language(config)

    required = ["uv", "git"]
    optional = ["tmux"]
    if console and Table:
        table = Table(title=tr(config, "tool_check"), header_style="bold cyan", border_style="blue")
        table.add_column(tr(config, "col_tool"))
        table.add_column(tr(config, "col_required"))
        table.add_column(tr(config, "col_found"))
        table.add_column(tr(config, "col_path"))
        for row in rows:
            table.add_row(row["tool"], row["required"], row["found"], row["path"])
        console.print(table)
    else:
        for row in rows:
            print_line(f"{row['tool']}: {row['path'] or tr(config, 'missing')}")

    missing = [tool for tool in [*required, *optional] if not command_exists(tool)]
    if missing and questionary is None:
        print_line(tr(config, "run_with_uv"))
        return
    if missing and ask_confirm(tr(config, "install_missing"), default=False):
        install_missing_tools(missing)


def strip_jsonc(text: str) -> str:
    result = []
    i = 0
    in_string = False
    escape = False
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            i += 1
            continue
        if char == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if char == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        result.append(char)
        i += 1
    return "".join(result)


def strip_trailing_commas(text: str) -> str:
    result = []
    i = 0
    in_string = False
    escape = False
    while i < len(text):
        char = text[i]
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            i += 1
            continue
        if char == ",":
            j = i + 1
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j < len(text) and text[j] in "]}":
                i += 1
                continue
        result.append(char)
        i += 1
    return "".join(result)


def read_vscode_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        json_text = strip_trailing_commas(strip_jsonc(text))
        return json.loads(json_text or "{}")
    except json.JSONDecodeError as exc:
        backup = path.with_suffix(path.suffix + f".bak-{now_stamp()}")
        shutil.copy2(path, backup)
        raise RuntimeError(tr(load_config(), "parse_settings_failed", path=path, backup=backup, error=exc)) from exc


def vscode_platform_key() -> tuple[str, str]:
    system = platform_id()
    if system == "windows":
        return "terminal.integrated.profiles.windows", "terminal.integrated.defaultProfile.windows"
    if system == "macos":
        return "terminal.integrated.profiles.osx", "terminal.integrated.defaultProfile.osx"
    return "terminal.integrated.profiles.linux", "terminal.integrated.defaultProfile.linux"


def vscode_user_settings_path(variant: str) -> Path:
    names = {
        "code": "Code",
        "insiders": "Code - Insiders",
        "codium": "VSCodium",
    }
    app_name = names.get(variant, "Code")
    system = platform_id()
    if system == "windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / app_name / "User" / "settings.json"
        return Path.home() / "AppData" / "Roaming" / app_name / "User" / "settings.json"
    if system == "macos":
        return Path.home() / "Library" / "Application Support" / app_name / "User" / "settings.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / app_name / "User" / "settings.json"


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def vscode_uv_command() -> str:
    return shutil.which("uv") or "uv"


def vscode_launch_command(script: Path) -> str:
    workspace_var = "${workspaceFolder}"
    uv = vscode_uv_command()
    if platform_id() == "windows":
        return (
            f"& {powershell_quote(uv)} run --script "
            f"{powershell_quote(str(script))} launch --workspace {powershell_quote(workspace_var)}"
        )
    return (
        f"{shell_quote(uv)} run --script "
        f"{shell_quote(str(script))} launch --workspace {shell_quote(workspace_var)}"
    )


def vscode_shell_fallback_command(command: str, shell: str, label: str) -> str:
    return shell_fallback_command(command, shell, label, reset_title=True)


def vscode_profile(script: Path, config: dict[str, Any], profile_name: str) -> dict[str, Any]:
    system = platform_id()
    command = vscode_launch_command(script)
    if system == "windows":
        shell = config.get("shell") or "powershell.exe"
        return {
            "path": shell,
            "args": ["-NoExit", "-ExecutionPolicy", "Bypass", "-Command", command],
            "icon": "terminal-powershell",
            "overrideName": True,
        }

    shell = config.get("shell") or default_shell()
    shell_name = Path(shell).name
    if shell_name in {"bash", "zsh", "sh", "dash", "ksh", "fish"}:
        return {
            "path": shell,
            "args": ["-lc", vscode_shell_fallback_command(command, shell, profile_name)],
            "icon": "terminal-bash",
            "overrideName": True,
        }
    return {"path": shell, "args": ["-c", command], "icon": "terminal", "overrideName": True}


def is_aiw_vscode_profile(profile: Any) -> bool:
    if not isinstance(profile, dict):
        return False
    args = profile.get("args", [])
    text = " ".join(str(part) for part in args) if isinstance(args, list) else str(args)
    return " launch --workspace " in text and ("aiw.py" in text or str(WORKSPACE_SCRIPT) in text)


def configure_vscode(workspace: Path, set_default: bool | None, scope: str = "user", variant: str = "code") -> None:
    workspace = workspace.resolve()
    config = load_config()
    if scope == "ask":
        config = ensure_language(config)
    profile_name = config.get("vscode", {}).get("profile_name", DEFAULT_VSCODE_PROFILE_NAME)
    if scope == "ask":
        scope = ask_select(
            tr(config, "vscode_scope_prompt"),
            [
                questionary.Choice(title=tr(config, "vscode_scope_user"), value="user"),
                questionary.Choice(title=tr(config, "vscode_scope_workspace"), value="workspace"),
            ],
        )

    if scope == "user":
        script = Path(__file__).resolve()
        settings_path = vscode_user_settings_path(variant)
    else:
        script = ensure_workspace_script(workspace)
        settings_path = workspace / ".vscode" / "settings.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = read_vscode_settings(settings_path)
    profiles_key, default_key = vscode_platform_key()
    profiles = settings.setdefault(profiles_key, {})
    for legacy_name in LEGACY_VSCODE_PROFILE_NAMES:
        if legacy_name != profile_name and is_aiw_vscode_profile(profiles.get(legacy_name)):
            profiles.pop(legacy_name, None)
        if settings.get(default_key) == legacy_name:
            settings.pop(default_key, None)
    profiles[profile_name] = vscode_profile(script, config, profile_name)
    if set_default is True:
        settings[default_key] = profile_name
    elif set_default is False and settings.get(default_key) == profile_name:
        settings.pop(default_key, None)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print_success(tr(config, "updated", path=settings_path))


def export_config(target: Path) -> None:
    config = load_config()
    write_json(target.expanduser(), config)
    print_success(tr(config, "exported_config", path=target))


def import_config(source: Path) -> None:
    config = merge_defaults(read_json(source.expanduser(), {}))
    save_config(config)
    print_success(tr(config, "imported_config", path=source))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    sub = parser.add_subparsers(dest="command")

    launch = sub.add_parser("launch", help="open the interactive task launcher")
    launch.add_argument("--workspace", default=os.getcwd())

    sub.add_parser("configure", help="edit global configuration")
    doctor = sub.add_parser("doctor", help="check and install required tools")
    doctor.add_argument("--json", action="store_true")

    vscode = sub.add_parser("vscode", help="configure VS Code terminal profile")
    vscode.add_argument("--workspace", default=os.getcwd())
    vscode.add_argument("--scope", choices=["workspace", "user"], default="user")
    vscode.add_argument("--variant", choices=["code", "insiders", "codium"], default="code")
    vscode.add_argument("--set-default", action="store_true", help="also make this the VS Code default terminal profile")
    vscode.add_argument("--no-default", action="store_true", help="remove this profile as the VS Code default terminal profile")

    export = sub.add_parser("export", help="export configuration")
    export.add_argument("path")

    import_cmd = sub.add_parser("import", help="import configuration")
    import_cmd.add_argument("path")

    sub.add_parser("where", help="show config paths")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command in (None, "launch"):
            workspace = Path(getattr(args, "workspace", os.getcwd())).expanduser()
            return launch_interactive(workspace)
        if args.command == "configure":
            configure_interactive()
            return 0
        if args.command == "doctor":
            doctor_interactive(json_output=args.json)
            return 0
        if args.command == "vscode":
            set_default = True if args.set_default else False if args.no_default else None
            configure_vscode(Path(args.workspace).expanduser(), set_default, scope=args.scope, variant=args.variant)
            return 0
        if args.command == "export":
            export_config(Path(args.path))
            return 0
        if args.command == "import":
            import_config(Path(args.path))
            return 0
        if args.command == "where":
            config = load_config()
            print_line(tr(config, "config_path", path=config_path()))
            print_line(tr(config, "sessions_path", path=sessions_path()))
            return 0
    except KeyboardInterrupt:
        print_line(f"\n{tr(load_config(), 'cancelled')}")
        return 130
    except (RuntimeError, OSError) as exc:
        print_error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
