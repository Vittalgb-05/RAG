import { createParser, type EventSourceMessage } from "eventsource-parser";
import { ApiError } from "./client";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface StreamSSEOptions {
  url: string;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  onEvent: (event: string, data: any) => void;
  onError?: (error: Error) => void;
}

export async function streamSSE({
  url,
  body,
  headers = {},
  signal,
  onEvent,
  onError,
}: StreamSSEOptions): Promise<void> {
  const fullUrl = url.startsWith("http")
    ? url
    : `${BASE_URL.replace(/\/$/, "")}/api/v1${url.startsWith("/") ? url : `/${url}`}`;

  const requestHeaders = new Headers(headers);
  requestHeaders.set("X-RAG-Client", "web");
  requestHeaders.set("Accept", "text/event-stream");

  let bodyStr: string | undefined;
  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
    bodyStr = JSON.stringify(body);
  }

  try {
    const response = await fetch(fullUrl, {
      method: body !== undefined ? "POST" : "GET",
      headers: requestHeaders,
      body: bodyStr,
      signal,
    });

    if (!response.ok) {
      let problem;
      try {
        problem = await response.json();
      } catch {
        problem = {
          title: "Stream Request Failed",
          status: response.status,
          code: "internal",
          detail: `HTTP error ${response.status}: ${response.statusText}`,
        };
      }
      throw new ApiError(problem);
    }

    if (!response.body) {
      throw new Error("No response body available for SSE stream");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    const parser = createParser({
      onEvent: (event: EventSourceMessage) => {
        let parsedData = event.data;
        try {
          parsedData = JSON.parse(event.data);
        } catch {
          // Pass raw string if not JSON
        }
        onEvent(event.event || "message", parsedData);
      },
    });

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
  } catch (err: any) {
    if (signal?.aborted) {
      return;
    }
    if (onError) {
      onError(err);
    } else {
      throw err;
    }
  }
}
