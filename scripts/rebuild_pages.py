#!/usr/bin/env python3
"""Request a branch-based Pages rebuild and verify its target commit, without PATs."""
import json
import os
import subprocess
import time
from urllib.request import Request, urlopen


def api(path, method="GET"):
    request = Request("https://api.github.com/" + path, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "GlobalStrategicIntelligence-Pages/1.0",
    })
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def main():
    repository = os.environ["GSI_REPOSITORY"]
    if repository != "ShawnZUW/Global-Strategic-Intelligence":
        raise RuntimeError("unexpected repository")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    info = api("repos/" + repository + "/pages")
    source = info.get("source", {})
    if source.get("branch") != "main" or source.get("path") != "/":
        raise RuntimeError("Pages is not configured for main / root; no settings were changed")
    result = api("repos/" + repository + "/pages/builds", "POST")
    print("Pages rebuild requested:", result.get("status", "unknown"))
    # Keep the existing main/root publishing source. GITHUB_TOKEN pushes alone
    # do not trigger Pages builds. Successful API queueing is not deployment.
    for _ in range(18):
        time.sleep(10)
        latest = api("repos/" + repository + "/pages/builds/latest")
        if latest.get("commit") != commit:
            continue
        if latest.get("status") == "built":
            print("Pages built the published feed commit:", commit)
            return
        if latest.get("status") == "errored":
            raise RuntimeError("Pages build failed: " + str(latest.get("error", {}).get("message")))
    raise RuntimeError("Pages build was requested but its completion was not verified within 3 minutes; inspect the Pages build")


if __name__ == "__main__":
    main()
