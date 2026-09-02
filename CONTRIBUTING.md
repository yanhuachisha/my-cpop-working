# Contributing

感谢你对 C-Pop Atlas 的关注。提交改动前，请先确认它能在现有 Lite 模式下运行，并尽量提供对应测试或复现步骤。

## Development flow

1. Create a focused branch from `main`.
2. Make one coherent change per pull request.
3. Run the relevant Python, Java, frontend, and Compose checks locally.
4. Update documentation or screenshots when user-facing behavior changes.
5. Open a pull request using the repository template.

## Commit messages

Use a short Conventional Commit style prefix:

```text
feat: add catalog search filter
fix: prevent duplicate memory projection
docs: clarify full profile startup
test: cover tool authorization failure
refactor: split retrieval policy
```

## Local checks

```powershell
cd backend
pytest -q
ruff check .

cd ..\services\music-core
..\..\mvnw.cmd test

cd ..\..\frontend
npm ci
npm run build
```

Do not commit `.env`, API keys, model caches, generated executables, or private user data.
