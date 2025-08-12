import os
import sys
import subprocess
from pathlib import Path


def build():
    base_dir = Path(__file__).resolve().parent
    os.chdir(base_dir)

    main_py = base_dir / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(f"main.py not found: {main_py}")

    # 아이콘 경로: 요청 경로 우선, 없으면 프로젝트 기본 아이콘으로 폴백
    icon_candidates = [
        base_dir / "imgs" / "no.icon",          # 요청 경로 (그대로 반영)
        base_dir / "imgs" / "icon" / "no.ico", # 기존 프로젝트 아이콘 경로
    ]
    icon_path = next((str(p) for p in icon_candidates if p.exists()), str(icon_candidates[0]))

    # 간단한 컴파일 명령 (hooks 제거)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--clean",
        "--noconsole",
        f"--icon={icon_path}",
        "--name",
        "main",
        "--exclude-module",
        "pythoncom",
        "--exclude-module",
        "pywintypes",
        "--exclude-module",
        "win32com",
        str(main_py),
    ]

    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    build()