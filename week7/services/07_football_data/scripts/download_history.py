"""Download pinned public historical inputs; never read or print API credentials."""

import asyncio
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "history"
SOURCES = {
    "openfootball": ("openfootball/england", "b17e8f0"),
    "fjelstul": ("jfjelstul/englishfootball", "ff3c376"),
}


async def main():
    RAW.mkdir(parents=True, exist_ok=True)
    previous_path = RAW / "manifest.json"
    previous = (
        json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    )
    manifest = {}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for name, (repo, ref) in SOURCES.items():
            response = await client.get(f"https://api.github.com/repos/{repo}/commits/{ref}")
            response.raise_for_status()
            sha = response.json()["sha"]
            manifest[name] = {"repository": repo, "commit": sha, "files": []}
            paths = []
            if name == "openfootball":
                for year in range(1992, 2026):
                    season = f"{year}-{str(year + 1)[2:]}"
                    paths.append(
                        (
                            ("archive/1990s/" if year < 2000 else "")
                            + season
                            + "/1-premierleague.txt",
                            f"{year}.txt",
                        )
                    )
                paths += [("LICENSE.md", "LICENSE.md")]
            else:
                # Fjelstul declares the license in README, not a separate LICENSE file.
                paths = [
                    ("data-csv/standings.csv", "standings.csv"),
                    ("data-csv/teams.csv", "teams.csv"),
                    ("README.md", "README.md"),
                ]
            target_dir = RAW / name
            target_dir.mkdir(exist_ok=True)
            for path, local in paths:
                url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
                cached = next(
                    (
                        item
                        for item in previous.get(name, {}).get("files", [])
                        if item["path"] == path and item["url"] == url
                    ),
                    None,
                )
                target = target_dir / local
                if (
                    cached
                    and target.exists()
                    and hashlib.sha256(target.read_bytes()).hexdigest() == cached["sha256"]
                ):
                    manifest[name]["files"].append(cached)
                    continue
                response = await client.get(url)
                if response.status_code == 404 and "LICENSE" in path:
                    # Repository trees determine the license filename, not assumptions.
                    tree = await client.get(f"https://api.github.com/repos/{repo}/git/trees/{sha}")
                    tree.raise_for_status()
                    candidates = [
                        x["path"]
                        for x in tree.json()["tree"]
                        if x["path"].lower().startswith(("license", "licence"))
                    ]
                    if len(candidates) != 1:
                        raise ValueError(f"Unresolved license filename for {repo}: {candidates}")
                    path = candidates[0]
                    url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
                    response = await client.get(url)
                response.raise_for_status()
                data = response.content
                (target_dir / local).write_bytes(data)
                manifest[name]["files"].append(
                    {
                        "path": path,
                        "local": local,
                        "url": url,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            print(f"{name}: {len(paths)} pinned files ready (verified cache or download) at {sha}")
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
