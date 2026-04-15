# ThermalBits Documentation

This directory contains an isolated MkDocs project for the ThermalBits
documentation. It keeps the documentation configuration, content, dependencies,
and generated site separate from the Python package.

## Install documentation dependencies

```bash
python -m pip install -r documentation/requirements-docs.txt
```

## Serve locally

From the repository root:

```bash
mkdocs serve -f documentation/mkdocs.yml
```

Then open `http://127.0.0.1:8000`.

## Build the static site

```bash
mkdocs build -f documentation/mkdocs.yml
```

The generated site is written to `documentation/site/`, which is ignored by Git.
