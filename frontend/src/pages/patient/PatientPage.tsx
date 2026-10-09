import { useEffect, useState } from "react";
import { getCurrentMemories, type Memory } from "../../api";

export default function PatientPage() {
  const [memories, setMemories] = useState<Memory[]>([]);

  useEffect(() => {
    getCurrentMemories()
      .then((data) => setMemories(data.memories))
      .catch(() => setMemories([]));
  }, []);

  const next = memories[0];

  return (
    <main style={{ padding: 32, fontSize: 32 }}>
      <h1>Patient day clock</h1>
      {next ? <p>Next: {next.summary}</p> : <p>No plans yet today</p>}
    </main>
  );
}