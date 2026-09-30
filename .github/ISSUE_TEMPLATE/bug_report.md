---
name: Bug report
about: Report a download, playback, search, Web UI, or Auto-Sync problem
title: ""
labels: ["bug"]
---

## What happened?

Describe what fails and where: CLI/menu, Web UI, Auto-Sync, HTTP API, or Discord bot.
For downloads, say whether it fails before starting, stops partway through, skips episodes, or produces a broken file.

## What did you expect to happen?

Describe the expected result, including the episode, language, or download location if relevant.

## Affected title / source

For search, extraction, download, or playback problems, fill in what applies:

- Site and title:
- Public series / episode / chapter URL:
- Season and episode / chapter number:
- Selected language and stream hoster (e.g. German Dub / VOE):
- Does it affect one episode, a whole title, or multiple titles?
- Does the same episode play on the source site in your browser? Does another offered hoster work in AniWorld-Downloader?

Use the source page URL rather than an expiring direct video URL. For a search problem, include the exact search term and selected site.

## How to reproduce

Paste the exact command, or describe the Web UI/menu steps and selected settings.
For Auto-Sync, include its reported result or skip reason and the language of the existing files.

1.
2.
3.

## Output / error

Include the error and the log lines leading up to it, not just the final traceback.
Add `--debug` to your command, or set `ANIWORLD_DEBUG_MODE=1` in your Docker environment and recreate the container.
For the Web UI, also copy the queue item's error details. For a broken page or stuck spinner, include a screenshot and browser console errors.

With the supplied Compose file, collect logs using `docker compose logs --tail=200 aniworld`.
Remove secrets before posting; attach long logs as a text file.

```text
(paste here)
```

## Environment

- OS and version (for Docker, include the host OS / NAS platform):
- Installation: pip / pipx / source checkout / executable / Docker
- Installed app version (`aniworld --version`; for source, also include `git rev-parse --short HEAD`):
- Python version (`python --version`; skip for executable / Docker):
- For Docker: image tag, CPU architecture, and when you last pulled/recreated it:
- For Web UI problems: browser and version; reverse proxy, if used:

With the supplied Compose file, get the app version using `docker compose exec aniworld aniworld --version`.

## Relevant settings (if applicable)

Paste only settings relevant to the problem, such as language, provider fallback order, custom download paths, or Auto-Sync options.
Say whether you set them in the Web UI, `.env`, command-line arguments, or Docker environment.

The default config is `~/.aniworld/.env` (`%USERPROFILE%\.aniworld\.env` on Windows), or under `ANIWORLD_INSTALL_FOLDER` if changed.
For Docker path/permission issues, include the relevant volume mounts and container path.

Do not post your whole config without reviewing it. Remove passwords, API keys, Discord tokens, SSO secrets, and cookies.

## Checklist

- [ ] I searched existing issues to avoid duplicates
