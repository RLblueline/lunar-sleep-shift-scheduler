"""Assemble web/dist/index.html from the engine and UI sources (no third-party build tools).

The same file runs two ways:
  * served by the data service  -> uses RemoteStore (fsync'd files on disk)
  * opened directly as a file   -> falls back to LocalStore (browser demo)
"""
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def build() -> str:
    shell = read(HERE, "src", "shell.html")
    engine = read(ROOT, "engine", "engine.js")
    store = read(HERE, "src", "store-local.js") + "\n" + read(HERE, "src", "store-remote.js")
    app = read(HERE, "src", "app.js")
    for marker in ("/*ENGINE*/", "/*STORE*/", "/*APP*/"):
        assert shell.count(marker) == 1, f"shell.html must contain {marker} exactly once"
    html = shell.replace("/*ENGINE*/", engine).replace("/*STORE*/", store).replace("/*APP*/", app)
    out_dir = os.path.join(HERE, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    digest = hashlib.sha256(html.encode()).hexdigest()[:16]
    with open(os.path.join(out_dir, "BUILD"), "w") as f:
        f.write(f"sha256:{digest}\n")
    return out


if __name__ == "__main__":
    print("built", build())
