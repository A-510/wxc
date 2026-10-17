#!/usr/bin/env python
"""把 wxc_launcher.py 打成单文件 `dist/wxc.exe`。

    python scripts/build_exe.py            # 构建（缺图标会自动从 图标.jpg 生成）
    python scripts/build_exe.py --no-verify

打包原则：**只收项目根目录里的文件**，且只收启动器清单里那几项（wxc 包、static、requirements.txt、
背景.jpg、scripts/selftest.py）。.venv / .data / dist / build / 仓库外的任何路径都不会进包——脚本会
在打包前逐个路径校验，越界直接报错退出。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ICON_SRC = ROOT / "图标.jpg"
ICON = ROOT / "assets" / "wxc.ico"
VERSION_FILE = BUILD / "version_info.txt"
EXE = DIST / "wxc.exe"
ICON_SIZES = [256, 128, 64, 48, 32, 24, 16]


def load_launcher():
    """直接读项目根里的启动器，保证打包清单只有一份定义。"""
    spec = importlib.util.spec_from_file_location("wxc_launcher", ROOT / "wxc_launcher.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload_pairs() -> list[tuple[Path, str]]:
    """(源文件, 包内目标目录) 列表；任何一个源文件不在项目根里就报错。"""
    launcher = load_launcher()
    pairs: list[tuple[Path, str]] = []
    outside: list[Path] = []
    for rel in launcher.PAYLOAD_ROOTS:
        src = (ROOT / rel).resolve()
        if not src.is_relative_to(ROOT):
            outside.append(src)
            continue
        if src.is_file():
            pairs.append((src, str(Path(rel).parent).replace("\\", "/") or "."))
        elif src.is_dir():
            for path in sorted(src.rglob("*")):
                if (path.is_file() and "__pycache__" not in path.parts
                        and path.suffix not in (".pyc", ".pyo")):
                    dest = str(path.parent.relative_to(ROOT)).replace("\\", "/") or "."
                    pairs.append((path, dest))
    if outside:
        raise SystemExit(f"拒绝打包项目根以外的路径：{outside}")
    if not pairs:
        raise SystemExit("没有找到任何要打包的文件，检查 PAYLOAD_ROOTS。")
    return pairs


def make_icon() -> None:
    if ICON.exists() and ICON.stat().st_mtime >= ICON_SRC.stat().st_mtime:
        print(f"[icon] 复用 {ICON.relative_to(ROOT)}")
        return
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("需要 Pillow 来生成图标：python -m pip install pillow")
    ICON.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(ICON_SRC).convert("RGBA")
    sizes = [s for s in ICON_SIZES if s <= max(image.size)]
    ICON.write_bytes(encode_ico(image, sizes))
    print(f"[icon] {ICON_SRC.name} → {ICON.relative_to(ROOT)} {sizes}")


def encode_ico(image, sizes: list[int]) -> bytes:
    """自己写 ICO：小尺寸用 32bpp DIB 帧，256 用 PNG 帧。

    Pillow 的 ICO 输出会把所有帧都存成 PNG，GDI+/部分系统组件的旧读取路径对这种帧会裁错画面；
    DIB 帧是兼容性最稳的写法（Explorer、任务栏、第三方工具都认）。
    """
    import io
    import struct

    from PIL import Image

    frames: list[bytes] = []
    for size in sizes:
        frame = image.resize((size, size), Image.LANCZOS)
        if size >= 256:
            buf = io.BytesIO()
            frame.save(buf, format="PNG")
            frames.append(buf.getvalue())
            continue
        pixels = frame.load()
        xor = bytearray()
        for y in range(size - 1, -1, -1):  # DIB 自下而上
            for x in range(size):
                r, g, b, a = pixels[x, y]
                xor += bytes((b, g, r, a))
        mask_stride = ((size + 31) // 32) * 4  # 1bpp，按 4 字节对齐；alpha 已够用，掩码留空
        header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
        frames.append(bytes(header) + bytes(xor) + bytes(mask_stride * size))

    out = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    offset = 6 + 16 * len(frames)
    for size, blob in zip(sizes, frames):
        out += struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0,
                           0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    for blob in frames:
        out += blob
    return bytes(out)


def write_version_file() -> None:
    launcher = load_launcher()
    numbers = [int(x) for x in launcher.LAUNCHER_VERSION.split(".")[:3]]
    numbers += [0] * (4 - len(numbers))
    quad = ".".join(str(n) for n in numbers)
    BUILD.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({', '.join(str(n) for n in numbers)}), prodvers=({', '.join(str(n) for n in numbers)}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080404b0', [
        StringStruct('CompanyName', 'wxc'),
        StringStruct('FileDescription', 'wxc launcher'),
        StringStruct('FileVersion', '{quad}'),
        StringStruct('InternalName', 'wxc'),
        StringStruct('OriginalFilename', 'wxc.exe'),
        StringStruct('ProductName', 'wxc'),
        StringStruct('ProductVersion', '{quad}')])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""", encoding="utf-8")


def build(pairs: list[tuple[Path, str]]) -> None:
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--console", "--name", "wxc", "--icon", str(ICON), "--version-file", str(VERSION_FILE),
            "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"),
            "--specpath", str(BUILD), "--exclude-module", "tkinter", "--exclude-module", "PIL",
            "--log-level", "WARN"]
    for src, dest in pairs:
        args += ["--add-data", f"{src}{os.pathsep}{dest}"]
    args.append(str(ROOT / "wxc_launcher.py"))
    print(f"[build] 收录 {len(pairs)} 个项目内文件，开始打 exe …")
    rc = subprocess.call(args, cwd=str(ROOT))
    if rc != 0:
        raise SystemExit(f"PyInstaller 退出码 {rc}")
    if not EXE.exists():
        raise SystemExit("没看到 dist/wxc.exe，构建失败。")


def verify() -> int:
    """开箱验证：版本号、自检模式、解包，都在一个隔离目录里做。"""
    if not EXE.exists():
        print("[verify] 跳过：没有 exe")
        return 1
    only = os.environ.get("WXC_VERIFY_HOME") or str(BUILD / "verify-home")
    if Path(only).exists():
        shutil.rmtree(only, ignore_errors=True)
    env = {**os.environ, "WXC_HOME": only, "PYTHONUTF8": "1"}
    print("[verify] wxc.exe --version")
    subprocess.call([str(EXE), "--version"], cwd=str(EXE.parent), env=env)
    print("[verify] wxc.exe --check（隔离目录首次运行：会解包项目文件）")
    rc = subprocess.call([str(EXE), "--check"], cwd=str(EXE.parent), env=env)
    extracted = Path(only) / "app"
    files = sorted(p.relative_to(extracted).as_posix() for p in extracted.rglob("*") if p.is_file())
    print(f"[verify] 解包 {len(files)} 个文件到 {extracted}")
    for name in files[:8]:
        print(f"         {name}")
    print(f"[verify] --check 退出码 {rc}（0=环境齐全，1=需要补环境，此时都算正常）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 dist/wxc.exe")
    parser.add_argument("--no-verify", action="store_true", help="跳过构建后的开箱验证")
    opts = parser.parse_args()

    pairs = payload_pairs()
    make_icon()
    write_version_file()
    build(pairs)
    size = EXE.stat().st_size
    digest = hashlib.sha256(EXE.read_bytes()).hexdigest()
    print(f"[done] {EXE}  {size / 1048576:.1f} MiB  sha256={digest[:16]}…")
    if not opts.no_verify:
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
