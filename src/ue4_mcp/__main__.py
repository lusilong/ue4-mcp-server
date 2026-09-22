"""Entry point: ``ue4-mcp`` / ``python -m ue4_mcp``. Serves MCP over stdio."""
import logging, sys
from .protocol import serve_stdio
from .server import TOOLS, RESOURCES

def main():
    if "--verbose" in sys.argv:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    serve_stdio(TOOLS, RESOURCES)

if __name__ == "__main__":
    main()
