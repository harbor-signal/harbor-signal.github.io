# Harbor Signal

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

The production target is the Ingrid-owned GitHub Pages org repo:
`harbor-signal/harbor-signal.github.io`.
