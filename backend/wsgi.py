"""Entry point for WSGI servers and for `flask run`.

The .env file is loaded before `app` is imported: Config reads os.environ in the
class body, so anything loaded after that import would be ignored. Values already
present in the environment win, so an explicit export still overrides the file.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from app import create_app  # noqa: E402  (must come after load_dotenv)

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
