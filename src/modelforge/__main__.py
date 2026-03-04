"""Entry point: python -m modelforge"""

import uvicorn

from modelforge.config import settings


def main():
    uvicorn.run(
        "modelforge.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["src/modelforge"],
        reload_excludes=[str(settings.MODEL_STORE_PATH)],
    )


if __name__ == "__main__":
    main()
