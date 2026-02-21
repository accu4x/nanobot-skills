import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
import urllib.request

# Config
workspace_skills = Path(r"C:\Users\hn2_f\.nanobot\workspace\skills")
target_repo = Path(r"C:\Users\hn2_f\source\repos\nanobot-skills")
skills_target = target_repo / "skills"
repo_name = "nanobot-skills"
description = "Collection of nanobot skills exported from local workspace"
private = False


def run(cmd, cwd=None, check=True):
    print(f"> {cmd}")
    res = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\nReturn code: {res.returncode}")
    return res


def copy_skills():
    if not workspace_skills.exists():
        raise FileNotFoundError(f"Skills workspace not found: {workspace_skills}")
    skills_target.mkdir(parents=True, exist_ok=True)
    for item in workspace_skills.iterdir():
        if item.is_dir():
            dest = skills_target / item.name
            # If dest exists, remove and recopy to avoid merge issues
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
            print(f"Copied {item} -> {dest}")


def ensure_git_init():
    if not (target_repo / ".git").exists():
        run("git init", cwd=target_repo)
    # set default branch name to main
    run("git checkout -B main", cwd=target_repo)


def commit_all():
    run("git add .", cwd=target_repo)
    # Check if there is anything to commit
    res = subprocess.run("git status --porcelain", shell=True, cwd=target_repo, capture_output=True, text=True)
    if res.stdout.strip() == "":
        print("Nothing to commit")
        return
    run("git commit -m \"Add nanobot skills export: initial import\"", cwd=target_repo)


def github_api_create_repo(token):
    url = "https://api.github.com/user/repos"
    data = json.dumps({"name": repo_name, "private": private, "description": description}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode()
        return json.loads(body)


def github_get_user(token):
    url = "https://api.github.com/user"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode()
        return json.loads(body)


def push_with_netrc(clone_url, username, token):
    # Create a temporary _netrc file in user's home
    home = Path.home()
    netrc_path = home / "_netrc" if os.name == 'nt' else home / ".netrc"
    backup = None
    if netrc_path.exists():
        backup = netrc_path.with_suffix('.backup')
        netrc_path.replace(backup)
    try:
        content = f"machine github.com login {username} password {token}\n"
        netrc_path.write_text(content)
        # On Unix set permission
        try:
            netrc_path.chmod(0o600)
        except Exception:
            pass
        # Add remote (replace if exists)
        # If remote exists, set-url
        res = subprocess.run("git remote", shell=True, cwd=target_repo, capture_output=True, text=True)
        if "origin" in res.stdout.split():
            run(f"git remote set-url origin {clone_url}", cwd=target_repo)
        else:
            run(f"git remote add origin {clone_url}", cwd=target_repo)
        # Push
        run("git push -u origin main", cwd=target_repo)
    finally:
        # Remove netrc and restore backup
        try:
            netrc_path.unlink()
        except Exception:
            pass
        if backup and backup.exists():
            backup.replace(netrc_path)


if __name__ == '__main__':
    try:
        print("Starting copy and push routine...")
        copy_skills()
        ensure_git_init()
        commit_all()
        token = os.environ.get('GITHUB_PAT') or os.environ.get('GITHUB_TOKEN')
        if not token:
            print("GITHUB_PAT not found in environment; created local repo only.")
            sys.exit(0)
        user = github_get_user(token)
        username = user.get('login')
        print(f"Authenticated to GitHub as: {username}")
        # Create repo
        print(f"Creating repository {repo_name}...")
        resp = github_api_create_repo(token)
        html_url = resp.get('html_url')
        clone_url = resp.get('clone_url')
        print(f"Repository created: {html_url}")
        # Push using netrc
        push_with_netrc(clone_url, username, token)
        print("Push complete.")
        print(html_url)
    except Exception as e:
        print("Error:", str(e))
        sys.exit(2)
