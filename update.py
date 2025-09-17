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


def download_and_extract_ffmpeg():
    arch = platform.machine()
    arch_map = {"aarch64": "arm64", "x86_64": "64"}
    arch_str = arch_map.get(arch, arch)

    # Get latest release info from GitHub API
    url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
    print("--> Fetching latest ffmpeg release info...")
    release = requests.get(url).json()

    # Find gpl build with correct arch
    asset = None
    for a in release["assets"]:
        if f"linux{arch_str}-gpl" in a["name"] and a["name"].endswith(".tar.xz"):
            asset = a
            break

    if not asset:
        raise RuntimeError(f"No ffmpeg build found for arch={arch_str}")

    ffmpeg_url = asset["browser_download_url"]
    ffmpeg_file = asset["name"]

    print(f"--> Downloading: {ffmpeg_url}")
    run_cmd(f"wget -q {ffmpeg_url}")

    # Extract
    print("--> Extracting ffmpeg...")
    with tarfile.open(ffmpeg_file, "r:xz") as tar:
        tar.extractall(".")

    # Copy binaries to /usr/bin
    folder = [f for f in os.listdir(".") if f.startswith("ffmpeg-")][0]
    bin_path = os.path.join(folder, "bin")

    for f in os.listdir(bin_path):
        shutil.copy(os.path.join(bin_path, f), "/usr/bin")

    # Cleanup
    os.remove(ffmpeg_file)
    shutil.rmtree(folder)

    # Verify codecs
    print("--> Verifying codecs (vp9 + av1)")
    run_cmd("ffmpeg -codecs | grep -E 'vp9|av1'")


def setup_environment():
    # 1. Create dirs
    BASE_DIR = os.environ.get("APP_HOME", "/app")
    BOT_DIR = os.path.join(BASE_DIR, "bot")
    TG_DIR = os.path.join(BASE_DIR, "tgenc")

    # If /app is not writable (rare case), use /tmp
    try:
        os.makedirs(BOT_DIR, exist_ok=True)
        os.makedirs(TG_DIR, exist_ok=True)
    except OSError:
        BOT_DIR = "/tmp/bot"
        TG_DIR = "/tmp/tgenc"
        os.makedirs(BOT_DIR, exist_ok=True)
        os.makedirs(TG_DIR, exist_ok=True)

    print(f"Bot dir: {BOT_DIR}")
    print(f"Tgenc dir: {TG_DIR}")
    run_cmd("chmod 777 /bot")

    # 2. Environment variables
    os.environ["DEBIAN_FRONTEND"] = "noninteractive"
    os.environ["TZ"] = "Africa/Lagos"
    os.environ["TERM"] = "xterm"

    # 3. Install dependencies
    arch = platform.machine()
    run_cmd("dnf -qq -y update")
    run_cmd(
        "dnf -qq -y install git aria2 bash xz wget curl pv jq python3-pip mediainfo "
        "psmisc procps-ng qbittorrent-nox"
    )
    if arch == "aarch64":
        run_cmd("dnf -qq -y install gcc python3-devel")

    run_cmd("python3 -m pip install --upgrade pip setuptools")

    # 4. Install latest ffmpeg with vp9 + av1
    download_and_extract_ffmpeg()

    # 5. Install Python requirements
    if os.path.exists("requirements.txt"):
        run_cmd("pip3 install -r requirements.txt")
    else:
        print("⚠️ requirements.txt not found")

    # 6. Cleanup for arm64
    if arch == "aarch64":
        run_cmd("dnf -qq -y history undo last")

    run_cmd("dnf clean all")

    

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
