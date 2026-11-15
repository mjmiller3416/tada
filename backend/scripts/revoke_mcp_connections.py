"""One-off script: disconnect every ChatGPT connection (the MCP connector).

Revokes every outstanding OAuth access and refresh token, so each
connected ChatGPT has to be approved again on the consent page. The same
thing as Settings -> Connected apps -> "Disconnect ChatGPT", for when the
app itself isn't reachable. To switch the connector off entirely, set
MCP_ENABLED=false on the backend service instead.

    railway run --service backend python -m scripts.revoke_mcp_connections
"""

from app.database import SessionLocal
from app.services import oauth_service


def main() -> None:
    db = SessionLocal()
    try:
        count = oauth_service.revoke_all(db)
    finally:
        db.close()
    print(f"Revoked {count} token(s). Every ChatGPT connection must sign in again.")


if __name__ == "__main__":
    main()
