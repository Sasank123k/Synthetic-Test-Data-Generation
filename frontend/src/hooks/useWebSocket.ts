/* ──────────────────────────────────────────────
   WebSocket Hook — Throttled Progress Streaming
   
   Implements a 250ms debounce/throttle to prevent
   excessive React re-renders during fast generation.
   ────────────────────────────────────────────── */

import { useEffect, useRef, useState, useCallback } from "react";
import type { GenerationProgress } from "@/lib/types";

const THROTTLE_MS = 250;

export function useGenerationWebSocket(jobId: string | null) {
  const [progress, setProgress] = useState<GenerationProgress | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const lastUpdateRef = useRef<number>(0);
  const pendingRef = useRef<GenerationProgress | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const throttledUpdate = useCallback((data: GenerationProgress) => {
    const now = Date.now();
    const elapsed = now - lastUpdateRef.current;

    if (elapsed >= THROTTLE_MS) {
      lastUpdateRef.current = now;
      setProgress(data);
    } else {
      pendingRef.current = data;
      if (!timerRef.current) {
        timerRef.current = setTimeout(() => {
          if (pendingRef.current) {
            lastUpdateRef.current = Date.now();
            setProgress(pendingRef.current);
            pendingRef.current = null;
          }
          timerRef.current = null;
        }, THROTTLE_MS - elapsed);
      }
    }
  }, []);

  useEffect(() => {
    if (!jobId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/generation/${jobId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.heartbeat) return; // Ignore heartbeats

        // For completion/failure, update immediately (skip throttle)
        if (data.status === "completed" || data.status === "failed") {
          setProgress(data);
        } else {
          throttledUpdate(data);
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onerror = () => {
      setError("WebSocket connection error");
    };

    ws.onclose = () => {
      setConnected(false);
    };

    return () => {
      ws.close();
      wsRef.current = null;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jobId, throttledUpdate]);

  return { progress, connected, error };
}
