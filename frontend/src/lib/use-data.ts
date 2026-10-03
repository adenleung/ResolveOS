"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
export function useData<T>(path: string | null, revision = 0) {
  const key = `${path}|${revision}`;
  const [state, setState] = useState<{key: string; data?: T; error?: Error}>({key: ""});
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    api<T>(path, {signal: controller.signal}).then(data => setState({key, data})).catch(error => {
      if (!controller.signal.aborted) setState({key, error: error instanceof Error ? error : new Error("Request failed")});
    });
    return () => controller.abort();
  }, [path, key]);
  return {data: state.key === key ? state.data : undefined, error: state.key === key ? state.error : undefined, loading: !!path && (state.key !== key || (!state.data && !state.error))};
}
