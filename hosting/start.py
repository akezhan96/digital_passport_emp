"""One startup path for initial deploys, cold starts and subsequent releases."""
import os
import subprocess
import sys


def main():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        os.environ["DATABASE_URL"] = "postgresql://" + url[len("postgres://"):]
    subprocess.run([sys.executable, "-m", "hosting.bootstrap_demo"], check=True)
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "hosting.web:app",
             "--host", "0.0.0.0", "--port", os.environ.get("PORT", "10000"),
             "--no-proxy-headers", "--no-access-log"])


if __name__ == "__main__":
    main()
