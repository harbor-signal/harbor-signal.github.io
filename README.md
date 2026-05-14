# Ingrid Watch

Public Hugo site for Ingrid's harbor traffic observatory and sci-fi review space.

## Local Development

```bash
hugo server --disableFastRender
```

## Build

```bash
hugo --minify
pytest -q
```

The production target is an Ingrid-owned GitHub Pages org repo:
`ingrid-watch/ingrid-watch.github.io`. Create that org/repo in GitHub, then set
`origin` to the repo URL and push `main`.
