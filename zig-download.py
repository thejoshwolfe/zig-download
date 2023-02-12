#!/usr/bin/env python3

import os, sys, subprocess
import shutil
import urllib.request
import json

metadata_url = "https://ziglang.org/download/index.json"
downloads_dir = os.path.expanduser("~/zig-downloads")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    with urllib.request.urlopen(metadata_url) as r:
        metadata = json.load(r)

    version = metadata["master"]["version"]
    dest_dir = os.path.join(downloads_dir, version)
    tmp_path = os.path.join(downloads_dir, ".tmp")
    if not os.path.isdir(dest_dir):
        download_url = metadata["master"]["x86_64-linux"]["tarball"]
        print("downloading: " + download_url)
        if os.path.exists(tmp_path):
            shutil.rmtree(tmp_path)
        os.makedirs(tmp_path)
        with urllib.request.urlopen(download_url) as r:
            # Can't pipe this straight to tar, because that makes the bytes different in some mysterious way.
            buf = r.read()
        subprocess.run(["tar", "-xJ"], input=buf, cwd=tmp_path, check=True)
        [the_name] = os.listdir(tmp_path)
        os.rename(os.path.join(tmp_path, the_name), dest_dir)
        os.rmdir(tmp_path)

    active_symlink = os.path.join(downloads_dir, "active")
    if os.readlink(active_symlink) != version:
        print("activating version: " + version)
        os.symlink(version, tmp_path)
        os.rename(tmp_path, active_symlink)
    else:
        print("version up to date: " + version)

if __name__ == "__main__":
    main()
