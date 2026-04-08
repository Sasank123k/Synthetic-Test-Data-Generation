/* ──────────────────────────────────────────────
   API Client — Backend Communication Layer
   ────────────────────────────────────────────── */

import type {
  CsvSchemaResponse,
  DraftConfigResponse,
  GenerationConfig,
  GenerationJobResponse,
  JobStatusResponse,
} from "./types";

const BASE = "/api";

export async function fetchHealth() {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error("Backend not reachable");
  return res.json();
}

export async function extractSchema(file: File): Promise<CsvSchemaResponse> {
  const form = new FormData();
  form.append("csv_file", file);
  const res = await fetch(`${BASE}/extract-schema`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Schema extraction failed (${res.status})`);
  }
  return res.json();
}

export async function generateDraftConfig(
  prompt: string,
  totalRecords: number,
  csvFile?: File
): Promise<DraftConfigResponse> {
  const form = new FormData();
  form.append("prompt", prompt);
  form.append("total_records", String(totalRecords));
  if (csvFile) form.append("csv_file", csvFile);

  const res = await fetch(`${BASE}/generate-draft-config`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Config generation failed (${res.status})`);
  }
  return res.json();
}

export async function executeGeneration(
  config: GenerationConfig,
  chunkSize = 100_000
): Promise<GenerationJobResponse> {
  const res = await fetch(`${BASE}/execute-generation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config, chunk_size: chunkSize }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Generation failed (${res.status})`);
  }
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${BASE}/job-status/${jobId}`);
  if (!res.ok) throw new Error(`Job status fetch failed (${res.status})`);
  return res.json();
}

export function getExportUrl(jobId: string): string {
  return `${BASE}/export/${jobId}`;
}
