import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { useLiveStore } from "../../stores/liveStore";
import { useLiveUpdates } from "../../api/useLiveUpdates";

export function Layout() {
  const connect = useLiveStore((s) => s.connect);
  const disconnect = useLiveStore((s) => s.disconnect);

  // Open WebSocket on mount, close on unmount
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  // Bridge live events to React Query cache invalidation
  useLiveUpdates();

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <Sidebar />

      <div className="flex flex-col flex-1 min-w-0">
        <Header />

        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
