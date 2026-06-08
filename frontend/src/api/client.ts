const BASE_URL = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(body || `API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export async function uploadFile(
  file: File,
  collection: string,
  force: boolean,
  onProgress: (progress: { stage: string; current: number; total: number }) => void,
  onComplete: (result: unknown) => void,
  onError: (error: string) => void
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("collection", collection);
  formData.append("force", force ? "true" : "false");

  try {
    const res = await fetch(`${BASE_URL}/documents/upload`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok || !res.body) {
      onError(`Upload failed: ${res.status}`);
      return;
    }

    await readSse(res.body, (event, data) => {
      if (event === "progress") onProgress(data);
      else if (event === "complete") onComplete(data);
      else if (event === "error") onError(data.error);
    });
  } catch (err) {
    onError(String(err));
  }
}

async function readSse(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: string, data: any) => void
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    const events = buffer.split(/\r?\n\r?\n/);
    buffer = events.pop() || "";

    for (const rawEvent of events) {
      const lines = rawEvent.split(/\r?\n/);
      const eventLine = lines.find((line) => line.startsWith("event:"));
      const dataLines = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart());

      if (!eventLine || dataLines.length === 0) continue;

      const event = eventLine.slice(6).trim();
      const dataText = dataLines.join("\n");
      try {
        onEvent(event, JSON.parse(dataText));
      } catch {
        onEvent(event, dataText);
      }
    }

    if (done) break;
  }

  if (buffer.trim()) {
    const lines = buffer.split(/\r?\n/);
    const eventLine = lines.find((line) => line.startsWith("event:"));
    const dataLines = lines
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());
    if (eventLine && dataLines.length > 0) {
      const event = eventLine.slice(6).trim();
      const dataText = dataLines.join("\n");
      try {
        onEvent(event, JSON.parse(dataText));
      } catch {
        onEvent(event, dataText);
      }
    }
  }
}

export async function streamQuery(
  query: string,
  collection: string,
  topK: number,
  enableRerank: boolean,
  onStage: (stage: { stage: string; message: string }) => void,
  onToken: (text: string) => void,
  onDone: (data: { citations: unknown[]; metadata: unknown }) => void,
  onError: (error: string) => void
) {
  try {
    const res = await fetch(`${BASE_URL}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, collection, top_k: topK, enable_rerank: enableRerank }),
    });

    if (!res.ok || !res.body) {
      onError(`Query failed: ${res.status}`);
      return;
    }

    await readSse(res.body, (event, data) => {
      if (event === "stage") onStage(data);
      else if (event === "token") onToken(data.text);
      else if (event === "done") onDone(data);
      else if (event === "error") onError(data.error);
    });
  } catch (err) {
    onError(String(err));
  }
}
