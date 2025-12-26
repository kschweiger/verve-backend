#!/bin/sh

OLD_VERSION=$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")

echo "Bumping Version"

uv run python bump.py . $1 --init --version-file --package verve_backend
if [[ $? != 0 ]]; then
  echo "Bumping version failed. Exiting..."
  exit 1
fi

VERSION=$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")

echo $VERSION

uvx git-changelog --bump ${VERSION}

git add pyproject.toml CHANGELOG.md VERSION uv.lock verve_backend/__init__.py
git commit -n -m "build: Bumping ${OLD_VERSION} -> ${VERSION} 🔖"

git tag ${VERSION}

echo "Pushing"
git push

echo "Pushing tag"
git push --tag
