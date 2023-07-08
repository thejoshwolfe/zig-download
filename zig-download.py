#!/usr/bin/env python3

import os, sys, subprocess
import shutil
import urllib.request
import json, re
import functools

metadata_url = "https://ziglang.org/download/index.json"
guess_url_template = "https://ziglang.org/builds/zig-linux-x86_64-{version}.tar.xz"
downloads_dir = os.path.expanduser("~/zig-downloads")
active_symlink = os.path.join(downloads_dir, "active")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=[
        "activate", "list", "pin", "unpin", "gc",
    ], default="activate", help=
        "default is: %(default)s. "
        "acitvate [--version v]: download the specified --version and activate it; "
        "performs auto gc. "
        "list [--version v]: shows the downloaded versions; shows the index useful for --version shorthand. "
        "{pin,unpin} --version v: a pinned --version never gets deleted by gc. "
        "gc: delete all unpinned non-active versions; "
        "auto gc keeps 10 versions downloaded, and deletes excess unpinned non-active versions "
        "starting with the oldest ones (according to version number).")
    parser.add_argument("--version", metavar="v", help=
        "'master' or 'stable' or '0.10.1' etc. "
        "Default is 'master'. 'stable' is the greatest available semver version. "
        "You can also give a numeric index into the list output by the 'list' command. "
        "Negative indexes count back from the end (Python's list[i] operator).")
    args = parser.parse_args()

    version = args.version
    if version != None:
        try:
            int(version)
        except ValueError:
            pass
        else:
            # Resolve version index
            version = get_version_list()[int(version)]

    if args.command == "activate":
        do_activate(version)
    elif args.command == "list":
        metadata = load_metadata()
        active_version = read_active_symlink()
        def get_status_code(name):
            if name == active_version:
                return ">"
            if name in metadata["pins"]:
                return "+"
            return " "
        outputs = [
            "{}{}) {}".format(get_status_code(name), i, name) for i, name in enumerate(get_version_list())
            if version == None or name == version
        ]
        if len(outputs) > 0:
            print("\n".join(outputs))
        else:
            if version != None:
                print("WARNING: version not installed: " + version, file=sys.stderr)
            # otherwise, there's just nothing downloaded.
    elif args.command == "pin":
        if version == None:
            parser.error("pin requires --version")
        if version not in get_version_list():
            sys.exit("ERROR: version not downloaded: " + version)
        metadata = load_metadata()
        if version not in metadata["pins"]:
            metadata["pins"].append(version)
            save_metadata(metadata)
    elif args.command == "unpin":
        if version == None:
            parser.error("unpin requires --version")
        if version not in get_version_list():
            sys.exit("ERROR: version not downloaded: " + version)
        metadata = load_metadata()
        if version in metadata["pins"]:
            metadata["pins"].remove(version)
            save_metadata(metadata)
    elif args.command == "gc":
        do_gc("manual")
    else: assert False

def load_metadata():
    try:
        with open(os.path.join(downloads_dir, "metadata.json")) as f:
            metadata = json.load(f)
    except FileNotFoundError:
        metadata = {}
    if type(metadata.get("pins", None)) != list:
        metadata["pins"] = []
    metadata["pins"] = [x for x in metadata["pins"] if type(x) == str]
    return metadata

def save_metadata(metadata):
    sort_versions(metadata["pins"])
    with open(os.path.join(downloads_dir, "metadata.json"), "w") as f:
        f.write(json.dumps(metadata, indent=2, sort_keys=True))
        f.write("\n")

_version_list_cache = None
def get_version_list():
    global _version_list_cache
    if _version_list_cache != None:
        return _version_list_cache
    try:
        names = [
            name for name in os.listdir(downloads_dir)
            if not name.endswith(".tmp") and
                name not in ("active", "metadata.json")
        ]
    except FileNotFoundError:
        names = []
    assert all(os.path.isdir(os.path.join(downloads_dir, name)) for name in names), "something's going on in the downloads dir: " + downloads_dir
    sort_versions(names)
    _version_list_cache = names
    return _version_list_cache

def sort_versions(names):
    def parse_version(v):
        # example: "0.10.1"
        # example: "0.11.0-dev.3658+5d9e8f27d"
        parts = re.split("[.+-]", v)
        assert len(parts) in (3, 6)
        for i in range(3):
            parts[i] = int(parts[i])
        if len(parts) == 6:
            parts[4] = int(parts[4])
        return parts
    names.sort(key=parse_version)

def do_gc(mode):
    names = get_version_list()
    metadata = load_metadata()
    active_version = read_active_symlink()

    limit = {
        "auto": 10,
        "manual": 0,
    }[mode]

    overage = len(names) - limit
    if overage <= 0:
        # We're good
        return

    unpinned_names = [
        name for name in names
        if name != active_version and name not in metadata["pins"]
    ]
    unpinned_names.reverse()

    for _ in range(overage):
        try:
            name = unpinned_names.pop()
        except IndexError:
            break
        print("INFO: removing old version: " + name)
        shutil.rmtree(os.path.join(downloads_dir, name))

def do_activate(version):
    with urllib.request.urlopen(metadata_url) as r:
        metadata = json.load(r)

    if version in (None, "master"):
        release_obj = metadata["master"]
        version = release_obj["version"]
        download_url = release_obj["x86_64-linux"]["tarball"]
    elif version == "stable":
        version = sorted([
            key for key in metadata.keys()
            if key != "master"
        ], key=lambda key: tuple(int(n) for n in key.split(".")))[-1]
        release_obj = metadata[version]
        download_url = release_obj["x86_64-linux"]["tarball"]
    else:
        try:
            release_obj = metadata[version]
        except KeyError:
            print("\n".join("WARNING: " + line for line in [
                "version not supported: " + version,
                "attempting to download anyway.",
            ]), file=sys.stderr, flush=True)
            download_url = guess_url_template.format(version=version)
        else:
            download_url = release_obj["x86_64-linux"]["tarball"]
    dest_dir = os.path.join(downloads_dir, version)
    tmp_path = os.path.join(downloads_dir, ".tmp")
    if not os.path.isdir(dest_dir):
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

    active_version = read_active_symlink()
    if active_version != version:
        print("activating version: " + version)
        os.symlink(version, tmp_path)
        os.rename(tmp_path, active_symlink)
    else:
        print("version up to date: " + version)

    global _version_list_cache
    _version_list_cache = None
    do_gc("auto")

def read_active_symlink():
    try:
        return os.readlink(active_symlink)
    except FileNotFoundError:
        return None

if __name__ == "__main__":
    main()
