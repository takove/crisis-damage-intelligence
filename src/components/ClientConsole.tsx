"use client";

import dynamic from "next/dynamic";

const OperationsConsole = dynamic(() => import("./OperationsConsole"), {
  ssr: false,
  loading: () => <main className="boot">Loading crisis map...</main>,
});

export default function ClientConsole() {
  return <OperationsConsole />;
}
