---
name: pp
description: Bump the current project's version, integrate its release into main, and publish from main using the existing release workflow. Use when the user says pp, /pp, or asks to bump version and publish.
metadata:
  author: local
  version: "1.0.2"
---

# Bump and publish

This is a shared skill. Keep the canonical instructions in `~/.agents/skills/pp/SKILL.md`; agent-specific discovery paths should link to that directory rather than duplicate its implementation.

Treat `pp` as authorization to bump the version and publish the current project's intended release. Use the user's requested version or destination when supplied.

Publish from `main` only. Release changes and their version bump must be integrated into `main` and pushed before any separate package publication, tag, or release. When starting on a feature branch, follow the repository's normal merge or pull-request workflow into `main`; an invoked `pp` authorizes that integration for the current project. If `main` does not exist or a merge is blocked, report the blocker instead of publishing from another branch. Never change or merge another project as part of this release.

1. Inspect repository instructions, Git status, the release history, and existing release scripts or CI. Identify the version source, mirrored version fields, and actual publication destination. Do not invent an npm publish, Git tag, or GitHub Release when the project does not use one. Ask one focused question if the destination remains ambiguous.
2. Select the smallest appropriate version increment: patch for fixes or copy changes, minor for compatible features. Require an explicit request for a major version or breaking release. Update only the version fields and release notes required by the established workflow; preserve unrelated changes.
3. Run the project's applicable formatting and static checks. Do not treat `pp` as a request to run tests. Review the release diff and exclude credentials and local configuration.
4. Commit the release changes, integrate them into `main`, and push `main`. Publish the resulting `main` commit using the existing workflow. If publication is simply a push to `main`, do not add other release artifacts. Never force-push. If publication fails, inspect the remote state before retrying; do not bump again merely to retry.
5. Verify that the release commit is on remote `main` and that the actual publication destination serves the intended version. Report the version, commit, branch or package, and publication result. Report unavailable checks plainly.

For `Jeinn-co/agent-skills`, inspect the changed skill's release history. `ai-usage` mirrors its version in `skills/ai-usage/SKILL.md` (`metadata.version`) and `skills/ai-usage/portable.py` (`VERSION`); its updater reads GitHub `main`. Follow that source publication workflow unless the repository has since added another one.
