import os

from dotenv import load_dotenv

load_dotenv()

import config
from dashboard.app import create_app


def main() -> None:
    app = create_app()
    port = config.DASHBOARD_PORT
    try:
        from waitress import serve
    except ImportError:
        app.run(host="0.0.0.0", port=port, threaded=True)
        return
    serve(app, host="0.0.0.0", port=port, threads=8, ident="soward")


main()
