import os
import traceback
import platform
import subprocess
import requests
import shutil
import tarfile
from decouple import config
from pathlib import Path
from subprocess import check_output
from subprocess import run as bashrun



def run_cmd(cmd, check=True):
    print(f"--> Running: {cmd}")
    subprocess.run(cmd, shell=True, check=check)


def get_work_dirs():
    """Choose writable dirs for bot."""
    base_dir = os.environ.get("APP_HOME", "/app")
    bot_dir = os.path.join(base_dir, "bot")
    tg_dir = os.path.join(base_dir, "tgenc")

    try:
        os.makedirs(bot_dir, exist_ok=True)
        os.makedirs(tg_dir, exist_ok=True)
    except OSError:
        bot_dir = "/tmp/bot"
        tg_dir = "/tmp/tgenc"
        os.makedirs(bot_dir, exist_ok=True)
        os.makedirs(tg_dir, exist_ok=True)

    return bot_dir, tg_dir


def download_and_extract_ffmpeg():
    arch = platform.machine()
    arch_map = {"aarch64": "arm64", "x86_64": "64"}
    arch_str = arch_map.get(arch, arch)

    url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
    print("--> Fetching latest ffmpeg release info...")
    release = requests.get(url).json()

    asset = None
    for a in release.get("assets", []):
        if f"linux{arch_str}-gpl" in a["name"] and a["name"].endswith(".tar.xz"):
            asset = a
            break

    if not asset:
        raise RuntimeError(f"No ffmpeg build found for arch={arch_str}")

    ffmpeg_url = asset["browser_download_url"]
    ffmpeg_file = asset["name"]

    print(f"--> Downloading: {ffmpeg_url}")
    run_cmd(f"wget -q {ffmpeg_url}")

    print("--> Extracting ffmpeg...")
    with tarfile.open(ffmpeg_file, "r:xz") as tar:
        tar.extractall(".")

    folder = [f for f in os.listdir(".") if f.startswith("ffmpeg-")][0]
    bin_path = os.path.join(folder, "bin")

    for f in os.listdir(bin_path):
        shutil.copy(os.path.join(bin_path, f), "/usr/bin")

    os.remove(ffmpeg_file)
    shutil.rmtree(folder)

    print("--> Verifying codecs (vp9 + av1)")
    run_cmd("ffmpeg -codecs | grep -E 'vp9|av1'")


def setup_environment():
    bot_dir, tg_dir = get_work_dirs()
    print(f"Bot dir: {bot_dir}")
    print(f"Tgenc dir: {tg_dir}")

    run_cmd(f"chmod 777 {bot_dir}")

    # Install system packages (Debian-based Leapcell)
    run_cmd("apt-get update -qq && apt-get install -y git wget curl xz-utils aria2 jq pv mediainfo procps qbittorrent-nox")

    # Upgrade pip + setuptools
    run_cmd("python3 -m pip install --upgrade pip setuptools")

    # Install ffmpeg with VP9 + AV1
    download_and_extract_ffmpeg()

    # Install Python requirements
    if os.path.exists("requirements.txt"):
        print("requirments.txt is available in the repository! ")
    else:
        print("⚠️ requirements.txt not found")

    # Cleanup apt cache
    run_cmd("apt-get clean && rm -rf /var/lib/apt/lists/*")
    

def varsgetter(files):
    evars = ""
    if files.is_file():
        with open(files, "r") as file:
            evars = file.read().rstrip()
            file.close()
    return evars


def varssaver(evars, files):
    if evars:
        file = open(files, "w")
        file.write(str(evars) + "\n")
        file.close()


def update():
    print("Default var for upstream repo & branch will used if none were given!")
    ALWAYS_DEPLOY_LATEST = config(
        "ALWAYS_DEPLOY_LATEST",
        default=False,
        cast=bool)
    AUPR = config("ALWAYS_UPDATE_PY_REQ", default=False, cast=bool)
    UPSTREAM_REPO = config(
        "UPSTREAM_REPO",
        default="https://github.com/Nubuki-all/Enc")
    UPSTREAM_BRANCH = config("UPSTREAM_BRANCH", default="main")

    r_filep = Path("Auto-rename.txt")
    rvars = varsgetter(r_filep)
    update_check = Path("update")
    cmd = (
        f"git switch {UPSTREAM_BRANCH} -q \
        && git pull -q "
        "&& git reset --hard @{u} -q \
        && git clean -df -q"
    )
    cmd2 = f"git init -q \
           && git config --global user.email 117080364+Niffy-the-conqueror@users.noreply.github.com \
           && git config --global user.name Niffy-the-conqueror \
           && git add . \
           && git commit -sm update -q \
           && git remote add origin {UPSTREAM_REPO} \
           && git fetch origin -q \
           && git reset --hard origin/{UPSTREAM_BRANCH} -q \
           && git switch {UPSTREAM_BRANCH} -q"

    if ALWAYS_DEPLOY_LATEST is True or update_check.is_file():
        if UPSTREAM_BRANCH == "main":
            bashrun(["rm -rf .git"], shell=True)
        if os.path.exists('.git') and check_output(
            ["git config --get remote.origin.url"],
                shell=True).decode().strip() == UPSTREAM_REPO:
            update = bashrun([cmd], shell=True)
        else:
            update = bashrun([cmd2], shell=True)
        if AUPR:
            bashrun(["pip3", "install", "-r", "requirements.txt"])
        if update.returncode == 0:
            print('Successfully updated with latest commit from UPSTREAM_REPO')
        else:
            print('Something went wrong while updating,maybe invalid upstream repo?')
        if update_check.is_file():
            os.remove("update")
        varssaver(rvars, r_filep)
    else:
        print("Auto-update is disabled.")


try:
    if __name__ == "__main__":
        setup_environment()
        update()
except Exception:
    traceback.print_exc()
