"use client";

import { useCallback, useEffect, useState } from "react";
import {
  disconnectAllApps,
  getConnectedApps,
  type ConnectedAppsResponse,
} from "@/lib/api";
import { friendlyDate } from "@/lib/dates";
import { Button, Card } from "@/components/ui";
import styles from "./ConnectedAppsSection.module.css";

/**
 * "Connected apps" — who has connected ChatGPT to Tada (the MCP
 * connector, backend routers/oauth.py), and one button that signs every
 * connection out. Reconnecting just means approving again from ChatGPT.
 * Stays out of the way: a short card, no detail screens.
 */
export default function ConnectedAppsSection() {
  const [data, setData] = useState<ConnectedAppsResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await getConnectedApps());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDisconnect() {
    if (!window.confirm("Disconnect ChatGPT? It will need your OK again to use Tada.")) {
      return;
    }
    setBusy(true);
    try {
      await disconnectAllApps();
      await load();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  const connections = data?.connections ?? [];

  return (
    <Card className={styles.section}>
      <h2 className={styles.heading}>Connected apps</h2>
      {failed ? (
        <p className={styles.help}>Couldn’t check just now — try again in a bit.</p>
      ) : data === null ? (
        <p className={styles.help}>Checking…</p>
      ) : connections.length === 0 ? (
        <p className={styles.help}>
          {data.enabled
            ? "Nothing connected. ChatGPT can be added as a connector and will ask for your OK here."
            : "The ChatGPT connector is switched off."}
        </p>
      ) : (
        <>
          <ul className={styles.list}>
            {connections.map((c, i) => (
              <li key={i} className={styles.row}>
                <span className={styles.name}>{c.client_name}</span>
                <span className={styles.meta}>
                  as {c.user_name.split(" ")[0]} · last used{" "}
                  {friendlyDate(c.last_used_at.slice(0, 10))}
                </span>
              </li>
            ))}
          </ul>
          <Button variant="secondary" fullWidth disabled={busy} onClick={handleDisconnect}>
            {busy ? "Disconnecting…" : "Disconnect ChatGPT"}
          </Button>
        </>
      )}
    </Card>
  );
}
