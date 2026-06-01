const BASE_URL = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
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
  onProgress: (progress: { stage: string; current: number; total: number }) => void,
  onComplete: (result: unknown) => void,
  onError: (error: string) => void
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("collection", collection);

  try {
    const res = await fetch(`${BASE_URL}/documents/upload`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok || !res.body) {
      onError(`Upload failed: ${res.status}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          const event = line.slice(7).trim();
          const dataLine = lines[lines.indexOf(line) + 1];
          if (dataLine?.startsWith("data: ")) {
            const data = JSON.parse(dataLine.slice(6));
            if (event === "progress") onProgress(data);
            else if (event === "complete") onComplete(data);
            else if (event === "error") onError(data.error);
          }
        }
      }
    }
  } catch (err) {
    onError(String(err));
  }
}

export async function streamQuery(
  query: string,
  collection: string,
  topK: number,
  onStage: (stage: { stage: string; message: string }) => void,
  onToken: (text: string) => void,
  onDone: (data: { citations: unknown[]; metadata: unknown }) => void,
  onError: (error: string) => void
) {
  try {
    const res = await fetch(`${BASE_URL}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, collection, top_k: topK }),
    });

    if (!res.ok || !res.body) {
      onError(`Query failed: ${res.status}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          const event = line.slice(7).trim();
          const dataLine = lines[lines.indexOf(line) + 1];
          if (dataLine?.startsWith("data: ")) {
            const data = JSON.parse(dataLine.slice(6));
            if (event === "stage") onStage(data);
            else if (event === "token") onToken(data.text);
            else if (event === "done") onDone(data);
            else if (event === "error") onError(data.error);
          }
        }
      }
    }
  } catch (err) {
    onError(String(err));
  }
}
