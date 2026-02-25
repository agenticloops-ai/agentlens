import { create } from "zustand";
import type { LiveEvent } from "../types";

type LiveEventHandler = (event: LiveEvent) => void;

interface LiveState {
  connected: boolean;
  connect: () => void;
  disconnect: () => void;
  subscribe: (handler: LiveEventHandler) => () => void;
}

/** Build the WebSocket URL based on the current page location. */
function getWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/ws/live`;
}

// ---------------------------------------------------------------------------
// Internal state shared across connect/disconnect calls (not exposed via
// Zustand because we only care about the `connected` boolean in the UI).
// ---------------------------------------------------------------------------

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 1000;
const MAX_RECONNECT_DELAY = 30_000;
let intentionalClose = false;

// Set of subscribed event handlers
const handlers = new Set<LiveEventHandler>();

// ---------------------------------------------------------------------------

export const useLiveStore = create<LiveState>((set) => {
  function scheduleReconnect() {
    if (intentionalClose) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connectWs();
    }, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
  }

  function connectWs() {
    // Prevent duplicate connections
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    intentionalClose = false;
    const ws = new WebSocket(getWsUrl());

    ws.addEventListener("open", () => {
      reconnectDelay = 1000; // reset back-off on successful connect
      set({ connected: true });
    });

    ws.addEventListener("message", (ev) => {
      try {
        const event = JSON.parse(ev.data as string) as LiveEvent;
        handlers.forEach((h) => h(event));
      } catch {
        // Ignore malformed messages
      }
    });

    ws.addEventListener("close", () => {
      set({ connected: false });
      socket = null;
      scheduleReconnect();
    });

    ws.addEventListener("error", () => {
      // The close event will fire after error; we handle reconnect there.
    });

    socket = ws;
  }

  function disconnectWs() {
    intentionalClose = true;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (socket) {
      socket.close();
      socket = null;
    }
    set({ connected: false });
  }

  return {
    connected: false,

    connect: connectWs,
    disconnect: disconnectWs,

    subscribe: (handler: LiveEventHandler) => {
      handlers.add(handler);
      return () => {
        handlers.delete(handler);
      };
    },
  };
});
