"use client";

import { useSyncExternalStore } from "react";
import HomeClient from "./HomeClient";

const subscribe = () => () => {};

/**
 * Next 15 often SSR-emits an empty `display:contents` slot for the page.
 * During SSR + hydration we mirror that node; after mount we render the app.
 * (Avoids hydration mismatch without next/dynamic ssr:false.)
 */
export default function Page() {
  const ready = useSyncExternalStore(subscribe, () => true, () => false);
  if (!ready) {
    return <div style={{ display: "contents" }} />;
  }
  return <HomeClient />;
}
