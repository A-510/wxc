#!/usr/bin/env python
"""wxc.exe · 启动器：环境自检 → 自动装依赖 → 提示重开 → 启动服务。

打包：`python scripts/build_exe.py` → `dist/wxc.exe`
未打包也可以直接跑：`python wxc_launcher.py`

第一次双击：检查电脑环境（Python / ffmpeg / 依赖），缺什么装什么，装完提示重开。
第二次双击：环境齐全 → 直接 `wxc start`（抓包 + 网页界面）。
带参数时转交给 wxc 自己的命令行，例如 `wxc.exe doctor`、`wxc.exe proxy off`。
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unicodedata
import webbrowser
from pathlib import Path

LAUNCHER_VERSION = "1.0.0"
PYTHON_MIN = (3, 10)
PYTHON_URL = "https://www.python.org/downloads/windows/"
FFMPEG_WINGET_ID = "Gyan.FFmpeg"
CN_PIP_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"

FROZEN = bool(getattr(sys, "frozen", False))
#: onefile 解包出的临时目录（里面按与项目根相同的相对路径放好 wxc/ static/ 等）
PAYLOAD_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
EXE_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
#: 打包进 exe 的项目内文件（相对项目根）。exe 之外的文件一概不进包。
PAYLOAD_ROOTS = ("wxc", "static", "requirements.txt", "背景.jpg", "scripts/selftest.py")
REQUIRED_MODULES = "fastapi, uvicorn, httpx, mitmproxy"

COLOR = False
_C = {"ink": "\033[38;5;95m", "mag": "\033[38;5;168m", "cyan": "\033[38;5;37m",
      "ok": "\033[38;5;35m", "warn": "\033[38;5;178m", "err": "\033[38;5;167m",
      "dim": "\033[2m", "b": "\033[1m", "r": "\033[0m"}

# --------------------------------------------------------------------------- 控制台


def _enable_vt() -> None:
    """打开 Windows 控制台的 ANSI 转义支持（没有就算了）。"""
    if os.name != "nt":
        return
    try:
        k32 = ctypes.windll.kernel32
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(k32.GetStdHandle(-11), ctypes.byref(mode)):
            k32.SetConsoleMode(k32.GetStdHandle(-11), mode.value | 0x0004)
    except Exception:
        pass


def setup_console() -> None:
    """控制台切 UTF-8（中文和颜文字不能变问号），并尝试开启颜色。"""
    global COLOR
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    _enable_vt()
    COLOR = bool(getattr(sys.stdout, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")


def c(text: str, *keys: str) -> str:
    if not COLOR or not keys:
        return text
    return "".join(_C[k] for k in keys) + text + _C["r"]


def dwidth(s: str) -> int:
    """终端显示宽度（CJK 算两格）。"""
    width = 0
    for ch in s:
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def say(text: str = "", *keys: str) -> None:
    print(c("  " + text, *keys) if text else "", flush=True)


def banner() -> None:
    line = "=" * 63
    print(c("  " + line, "ink"))
    print(c("    ✦ wxc · 网课搬回家", "b", "mag"), c("   (｡･ω･｡)ﾉ♡", "dim"))
    print(c("    微信小程序网课 → 你自己的电脑本地 mp4", "cyan"))
    print(c("  " + line, "ink"))
    print(flush=True)


def step(no: str, title: str, detail: str, state: str = "info") -> None:
    """一行自检结果，例如 `  ① 电脑环境 ······ ✓ Python 3.12.12 已就位`"""
    mark = {"ok": c("✓", "ok"), "warn": c("!", "warn"), "err": c("✗", "err"),
            "info": c("…", "cyan"), "note": c("·", "dim")}[state]
    dots = c("·" * max(2, 18 - dwidth(title)), "dim")
    head = f"  {c(no + ' ' + title, 'b')} {dots} {mark}"
    print(f"{head} {detail}" if detail else head, flush=True)


def ok_face(text: str) -> None:
    say("✧*。 " + text, "b", "mag")


def pause(message: str) -> None:
    """等用户按键；没有交互终端（管道 / CI）就跳过。"""
    say()
    say(message, "dim")
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            input()
    except (EOFError, KeyboardInterrupt):
        pass


def ask_yes(message: str) -> bool:
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return False
        return input(c("  " + message + " [Y/n] ", "b")).strip().lower() in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


# --------------------------------------------------------------------------- 路径


def launcher_home() -> Path:
    env = os.environ.get("WXC_HOME")
    if env:
        return Path(env).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") or Path.home()
    return (Path(base) / "wxc").resolve()


def resolve_app_dir() -> tuple[Path, bool]:
    """返回 (项目目录, 是否需要从 exe 里解包)。"""
    if not FROZEN:
        return Path(__file__).resolve().parent, False
    if (EXE_DIR / "wxc" / "cli.py").exists():
        return EXE_DIR, False  # exe 旁边就是项目源码 → 就地跑
    return launcher_home() / "app", True


APP_DIR, NEEDS_EXTRACT = resolve_app_dir()
DATA_DIR = APP_DIR / ".data"
VENV_DIR = APP_DIR / ".venv"
STATE_FILE = DATA_DIR / "launcher.json"
DEPS_MARKER = VENV_DIR / ".wxc-deps.json"
PAYLOAD_MARKER = APP_DIR / ".wxc-payload.json"


def venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ffprobe_of(ffmpeg: str) -> Path:
    return Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(**kw) -> None:
    state = load_state()
    state.update(kw)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
    except OSError as exc:
        say(f"（设置没存下来：{exc}）", "dim")


# --------------------------------------------------------------------------- 解包


def payload_files() -> list[Path]:
    """按相对路径列出打包清单里的文件（.pyc / __pycache__ 不收）。"""
    out: list[Path] = []
    for rel in PAYLOAD_ROOTS:
        src = PAYLOAD_DIR / rel
        if src.is_file():
            out.append(src)
        elif src.is_dir():
            out.extend(p for p in sorted(src.rglob("*"))
                       if p.is_file() and "__pycache__" not in p.parts
                       and p.suffix not in (".pyc", ".pyo"))
    return out


def payload_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in payload_files():
        digest.update(str(path.relative_to(PAYLOAD_DIR)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()[:16]


def extract_payload() -> None:
    """把 exe 里带的项目文件铺到 APP_DIR（.data / .venv 一概不碰）。"""
    files = payload_files()
    if not files:
        return
    stamp = {"fingerprint": payload_fingerprint(), "version": LAUNCHER_VERSION}
    try:
        if json.loads(PAYLOAD_MARKER.read_text("utf-8")) == stamp:
            return
    except (OSError, ValueError):
        pass
    step("·", "准备工作目录", str(APP_DIR), "note")
    for src in files:
        dst = APP_DIR / src.relative_to(PAYLOAD_DIR)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    PAYLOAD_MARKER.write_text(json.dumps(stamp), "utf-8")


# --------------------------------------------------------------------------- 自检项


def probe_python(argv: list[str]) -> tuple[int, int, str] | None:
    """跑一次候选解释器，返回 (主版本, 次版本, "3.12.12")；跑不动就 None。"""
    try:
        proc = subprocess.run(argv + ["-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        major, minor, patch = (int(x) for x in proc.stdout.strip().split(".")[:3])
    except ValueError:
        return None
    return major, minor, f"{major}.{minor}.{patch}"


def find_system_python() -> tuple[list[str], str] | None:
    """找一个系统 Python（>= 3.10 优先）用来建 .venv。"""
    ours = venv_python()
    fallback: tuple[list[str], str] | None = None
    for name in ("python", "py", "python3"):
        found = shutil.which(name)
        if not found:
            continue
        argv = [found, "-3"] if name == "py" else [found]
        try:
            if Path(argv[0]).resolve() == ours.resolve():
                continue  # 别拿 .venv 里的自己去建 .venv
        except OSError:
            pass
        info = probe_python(argv)
        if not info:
            continue
        major, minor, version = info
        if (major, minor) >= PYTHON_MIN:
            return argv, version
        fallback = fallback or (argv, version)
    return fallback


def version_pair(version: str) -> tuple[int, int]:
    major, minor = version.split(".")[:2]
    return int(major), int(minor)


def find_ffmpeg() -> str | None:
    saved = load_state().get("ffmpeg") or os.environ.get("WXC_FFMPEG")
    if saved and Path(saved).exists():
        return saved
    return shutil.which("ffmpeg")


def winget_install_ffmpeg() -> str | None:
    """没 ffmpeg 就用 winget 装一个；装完记下绝对路径（PATH 没刷新也能用）。"""
    winget = shutil.which("winget")
    if not winget or os.environ.get("WXC_NO_AUTO_INSTALL"):
        return None
    say("→ 用 winget 装 ffmpeg（会弹一点日志，装完就好）", "cyan")
    try:
        rc = subprocess.call([winget, "install", "--id", FFMPEG_WINGET_ID, "-e", "--silent",
                              "--accept-source-agreements", "--accept-package-agreements",
                              "--disable-interactivity"])
    except OSError:
        return None
    if rc != 0:
        return None
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Microsoft" / "WinGet" / "Packages"
    for cand in sorted(root.glob(f"{FFMPEG_WINGET_ID}*/**/bin/ffmpeg.exe")):
        return str(cand)
    return None


def requirements_hash() -> str:
    try:
        return hashlib.sha256((APP_DIR / "requirements.txt").read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def imports_ok() -> bool:
    python = venv_python()
    if not python.exists():
        return False
    try:
        proc = subprocess.run([str(python), "-c", f"import {REQUIRED_MODULES}"],
                              cwd=str(APP_DIR), capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def write_deps_marker() -> None:
    try:
        DEPS_MARKER.write_text(json.dumps({"requirements": requirements_hash(),
                                           "launcher": LAUNCHER_VERSION}), "utf-8")
    except OSError:
        pass


def deps_ready() -> bool:
    """标记对得上 → 再 import 复核一次（venv 可能被弄坏）；没有标记 → 认一次用户自己 pip 装的。

    requirements.txt 变了（hash 对不上）必须重装，不能靠 import 蒙过去。
    """
    try:
        marker = json.loads(DEPS_MARKER.read_text("utf-8"))
    except (OSError, ValueError):
        marker = None
    if marker is not None and marker.get("requirements") != requirements_hash():
        return False
    if imports_ok():
        write_deps_marker()
        return True
    return False


def run_live(argv: list[str], cwd: Path) -> int:
    """输出直接接到当前窗口（pip 进度条、winget 日志都看得见）。"""
    say(f"$ {' '.join(argv)}", "dim")
    try:
        return subprocess.call(argv, cwd=str(cwd))
    except OSError as exc:
        say(f"命令没跑起来：{exc}", "err")
        return 127


def install_deps(system_python: list[str]) -> bool:
    if not venv_python().exists():
        say("→ 给项目安一个小房间（.venv）", "cyan")
        if run_live(system_python + ["-m", "venv", str(VENV_DIR)], APP_DIR) != 0 or not venv_python().exists():
            say("建虚拟环境失败了 (´；ω；`) 多半是装 Python 时没勾 PATH / py launcher。", "err")
            return False
    pip = [str(venv_python()), "-m", "pip", "install", "--disable-pip-version-check",
           "-r", "requirements.txt"]
    say("→ 开始下载依赖（第一次会慢一点，别关窗口哦）", "cyan")
    if run_live(pip, APP_DIR) == 0:
        write_deps_marker()
        return True
    say("主站没连上，换国内镜像再试一次～", "warn")
    if run_live(pip[:4] + ["-i", CN_PIP_INDEX] + pip[4:], APP_DIR) == 0:
        write_deps_marker()
        return True
    return False


# --------------------------------------------------------------------------- 启动服务


def start_service(forward: list[str]) -> int:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["WXC_DATA"] = str(DATA_DIR)
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        env["WXC_FFMPEG"] = ffmpeg
        if ffprobe_of(ffmpeg).exists():
            env["WXC_FFPROBE"] = str(ffprobe_of(ffmpeg))
    sub = ["start"] if (not forward or forward[0].startswith("-")) else []
    argv = [str(venv_python()), "-m", "wxc.cli", *(sub + forward)]
    say(f"$ wxc {' '.join(sub + forward)}", "dim")
    say()
    try:
        return subprocess.call(argv, cwd=str(APP_DIR), env=env)
    except OSError as exc:
        say(f"启动失败了：{exc}", "err")
        return 1


# --------------------------------------------------------------------------- 主流程


def check_environment(first: bool = True) -> dict:
    """只读自检：不装任何东西。"""
    python = find_system_python()
    ffmpeg = find_ffmpeg()
    deps = deps_ready()
    if python and version_pair(python[1]) >= PYTHON_MIN:
        step("①" if first else "·", "电脑环境", f"Python {python[1]} 已就位", "ok")
    elif python:
        step("①" if first else "·", "电脑环境", f"Python {python[1]} 太旧（要 3.10+）", "err")
    else:
        step("①" if first else "·", "电脑环境", "没找到 3.10 或更新的 Python", "err")
    step("②", "ffmpeg", f"已就位（{ffmpeg}）" if ffmpeg else "没找到（合并 mp4 要用它）",
         "ok" if ffmpeg else "warn")
    step("③", "依赖库", "齐了" if deps else "还没装", "ok" if deps else "warn")
    step("·", "项目目录", str(APP_DIR), "note")
    return {"python": python, "ffmpeg": ffmpeg, "deps": deps}


def main(argv: list[str] | None = None) -> int:
    setup_console()
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv and argv[0] == "--version":
        print(f"wxc launcher {LAUNCHER_VERSION}")
        return 0
    check_only = "--check" in argv
    force = "--repair" in argv
    forward = [a for a in argv if a not in ("--check", "--repair")]

    if NEEDS_EXTRACT:
        banner()
        extract_payload()
    else:
        banner()

    if check_only:
        result = check_environment()
        ready = bool(result["python"] and version_pair(result["python"][1]) >= PYTHON_MIN
                     and result["deps"] and result["ffmpeg"])
        say()
        say(f"判定：{'可以启动啦 ✧' if ready else '还没准备好，双击一次 wxc.exe 我就帮你装'}"
            , "b", "mag" if ready else "warn")
        return 0 if ready else 1

    say("(｡･ω･｡)ﾉ♡ 你好呀～ 让我先看看你的电脑准备好了没有。", "mag")
    say()

    # ---- ① Python
    python = find_system_python()
    if not python or version_pair(python[1]) < PYTHON_MIN:
        step("①", "电脑环境", f"Python {python[1]} 太旧了（要 3.10 或更新）" if python else "这台电脑还没有 Python",
             "err")
        say()
        say("(´；ω；`) 我需要 Python 3.10+ 才能给自己装零件。", "err")
        say("装的时候记得勾选 “Add python.exe to PATH”，装完再双击一次我就好～", "cyan")
        say(f"下载页：{PYTHON_URL}", "cyan")
        if ask_yes("要我现在帮你打开下载页吗？"):
            webbrowser.open(PYTHON_URL)
        pause("按回车关掉这个窗口。")
        return 1
    step("①", "电脑环境", f"Python {python[1]} 已就位", "ok")

    # ---- ② ffmpeg
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        step("②", "ffmpeg", "没找到，我帮你装一个～", "warn")
        ffmpeg = winget_install_ffmpeg()
        if ffmpeg:
            save_state(ffmpeg=ffmpeg)
            step("②", "ffmpeg", f"装好了：{ffmpeg}", "ok")
        else:
            say()
            say("(｡•́︿•̀｡) ffmpeg 得你自己装一下（合并视频要用）：", "warn")
            say("  winget install Gyan.FFmpeg        ← 在 PowerShell 里跑这句，最省事", "cyan")
            say("  或去 https://www.gyan.dev/ffmpeg/builds/ 下 full 包，把 bin 目录加进 PATH", "cyan")
            say("装完再双击一次我，我认得出来 ✧", "mag")
            pause("按回车关掉这个窗口。")
            return 1
    else:
        step("②", "ffmpeg", f"已就位（{ffmpeg}）", "ok")

    # ---- ③ 依赖
    installed_something = False
    if deps_ready() and not force:
        step("③", "依赖库", "齐了，不用装", "ok")
    else:
        step("③", "依赖库", "正在装小零件…", "info")
        if not install_deps(python[0]):
            say()
            say("(＞﹏＜) 依赖没装上，多半是网络不通。换个网络再双击我一次试试～", "err")
            say("手动也行：项目目录里跑 .venv\\Scripts\\python.exe -m pip install -r requirements.txt", "dim")
            pause("按回车关掉这个窗口。")
            return 1
        installed_something = True

    # ---- 装完东西 → 提示重开（第一次打开的正常结局）
    if installed_something:
        say()
        ok_face("装好啦！零件都齐了～")
        say()
        print(c("      请把这个窗口关掉，然后再双击一次 wxc.exe ：", "b", "mag"))
        print(c("      这次我会直接帮你打开浏览器，开始干活 (๑˃ᴗ˂)ﻭ", "mag"))
        say()
        say("小提醒：进去之后先点「安装 CA 证书」+「开启系统代理」，界面上有按钮，点两下就好。", "dim")
        pause("按回车关掉这个窗口。")
        return 0

    # ---- ④ 启动
    step("④", "启动服务", "(っ˘ω˘ς) 正在唤醒…", "info")
    say()
    code = start_service(forward)
    if code == 0:
        say()
        ok_face("窗口关了就停啦，下次再双击我～")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
