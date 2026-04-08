import { useState, useEffect, useCallback, useRef } from "react";
import type {
  AppStep,
  CsvSchemaResponse,
  GenerationConfig,
  JobStatusResponse,
} from "./lib/types";
import {
  fetchHealth,
  extractSchema,
  generateDraftConfig,
  executeGeneration,
  getJobStatus,
  getExportUrl,
} from "./lib/api";
import { useGenerationWebSocket } from "./hooks/useWebSocket";
import "./index.css";

/* ═══════════════════════════════════════════════
   Main Application
   ═══════════════════════════════════════════════ */

function App() {
  // ── Global State ──
  const [step, setStep] = useState<AppStep>("upload");
  const [health, setHealth] = useState<{ llm_provider: string; llm_model: string } | null>(null);

  // ── Upload State ──
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvSchema, setCsvSchema] = useState<CsvSchemaResponse | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  // ── Config State (Frontend is the state owner) ──
  const [prompt, setPrompt] = useState("");
  const [totalRecords, setTotalRecords] = useState(1000);
  const [config, setConfig] = useState<GenerationConfig | null>(null);
  const [draftMeta, setDraftMeta] = useState<{ review: boolean; feedback?: string; iterations: number } | null>(null);
  const [configLoading, setConfigLoading] = useState(false);

  // ── Generation State ──
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const { progress, connected: wsConnected } = useGenerationWebSocket(jobId);

  // ── Error ──
  const [error, setError] = useState<string | null>(null);

  // Health check on mount
  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setError("Backend not reachable. Start it with: python run.py"));
  }, []);

  // Poll job status when generating
  useEffect(() => {
    if (!jobId || step !== "generate") return;
    const interval = setInterval(async () => {
      try {
        const status = await getJobStatus(jobId);
        setJobStatus(status);
        if (status.status === "completed" || status.status === "failed") {
          clearInterval(interval);
          setStep("results");
        }
      } catch { /* ignore */ }
    }, 1000);
    return () => clearInterval(interval);
  }, [jobId, step]);

  // ── Handlers ──
  const handleFileUpload = useCallback(async (file: File) => {
    setError(null);
    setCsvFile(file);
    setUploadLoading(true);
    try {
      const schema = await extractSchema(file);
      setCsvSchema(schema);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploadLoading(false);
    }
  }, []);

  const handleGenerateConfig = useCallback(async () => {
    if (!prompt.trim()) { setError("Please enter a prompt"); return; }
    setError(null);
    setConfigLoading(true);
    try {
      const draft = await generateDraftConfig(prompt, totalRecords, csvFile || undefined);
      setConfig(draft.config);
      setDraftMeta({
        review: draft.requires_manual_review,
        feedback: draft.critic_feedback || undefined,
        iterations: draft.actor_critic_iterations,
      });
      setStep("configure");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setConfigLoading(false);
    }
  }, [prompt, totalRecords, csvFile]);

  const handleExecute = useCallback(async () => {
    if (!config) return;
    setError(null);
    try {
      const job = await executeGeneration(config);
      setJobId(job.job_id);
      setStep("generate");
    } catch (e: any) {
      setError(e.message);
    }
  }, [config]);

  const handleReset = useCallback(() => {
    setStep("upload");
    setCsvFile(null);
    setCsvSchema(null);
    setPrompt("");
    setConfig(null);
    setDraftMeta(null);
    setJobId(null);
    setJobStatus(null);
    setError(null);
  }, []);

  // ── Step indicators ──
  const steps: { key: AppStep; label: string; icon: string }[] = [
    { key: "upload", label: "Upload & Prompt", icon: "1" },
    { key: "configure", label: "Review Config", icon: "2" },
    { key: "generate", label: "Generate", icon: "3" },
    { key: "results", label: "Results", icon: "4" },
  ];
  const stepIdx = steps.findIndex((s) => s.key === step);

  return (
    <div className="dark min-h-screen bg-background text-foreground">
      {/* ── Top Bar ── */}
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 text-sm font-bold text-white">
              SD
            </div>
            <span className="text-lg font-semibold tracking-tight">Synthetic Data Engine</span>
          </div>
          {health && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              {health.llm_provider}/{health.llm_model}
            </div>
          )}
        </div>
      </header>

      {/* ── Progress Steps ── */}
      <div className="mx-auto max-w-6xl px-6 pt-8">
        <div className="mb-8 flex items-center justify-center gap-1">
          {steps.map((s, i) => (
            <div key={s.key} className="flex items-center">
              <div className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all ${
                i === stepIdx
                  ? "bg-primary text-primary-foreground shadow-lg shadow-primary/25"
                  : i < stepIdx
                  ? "bg-primary/20 text-primary"
                  : "bg-muted/50 text-muted-foreground"
              }`}>
                <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
                  i < stepIdx ? "bg-primary text-primary-foreground" : "bg-white/10"
                }`}>
                  {i < stepIdx ? "✓" : s.icon}
                </span>
                <span className="hidden sm:inline">{s.label}</span>
              </div>
              {i < steps.length - 1 && (
                <div className={`mx-2 h-px w-8 ${i < stepIdx ? "bg-primary" : "bg-border"}`} />
              )}
            </div>
          ))}
        </div>

        {/* ── Error Banner ── */}
        {error && (
          <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            <span className="font-medium">Error:</span> {error}
            <button onClick={() => setError(null)} className="ml-3 text-red-300 hover:text-red-100">✕</button>
          </div>
        )}

        {/* ═══ STEP 1: Upload & Prompt ═══ */}
        {step === "upload" && (
          <div className="mx-auto max-w-3xl space-y-6">
            {/* CSV Upload */}
            <div className="rounded-xl border border-border/50 bg-card/50 p-6 backdrop-blur-sm">
              <h2 className="mb-1 text-xl font-semibold">📄 Upload CSV (Optional)</h2>
              <p className="mb-4 text-sm text-muted-foreground">Upload a sample CSV to extract column headers as ground truth for the AI config generator.</p>
              
              <FileDropZone
                onFile={handleFileUpload}
                loading={uploadLoading}
                currentFile={csvFile}
              />

              {csvSchema && (
                <div className="mt-4 rounded-lg border border-border/30 bg-muted/20 p-4">
                  <h3 className="mb-2 text-sm font-medium text-green-400">
                    ✓ Extracted {csvSchema.total_columns} columns from {csvSchema.filename}
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border/30 text-left text-xs text-muted-foreground">
                          <th className="pb-2 pr-4">Column</th>
                          <th className="pb-2 pr-4">Type</th>
                          <th className="pb-2">Sample Values</th>
                        </tr>
                      </thead>
                      <tbody>
                        {csvSchema.columns.map((col) => (
                          <tr key={col.column_name} className="border-b border-border/10">
                            <td className="py-2 pr-4 font-mono text-xs text-blue-400">{col.column_name}</td>
                            <td className="py-2 pr-4">
                              <span className="rounded bg-muted/50 px-2 py-0.5 text-xs">{col.inferred_type}</span>
                            </td>
                            <td className="py-2 text-xs text-muted-foreground">{col.sample_values.slice(0, 3).join(", ")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* NL Prompt */}
            <div className="rounded-xl border border-border/50 bg-card/50 p-6 backdrop-blur-sm">
              <h2 className="mb-1 text-xl font-semibold">🧠 Describe Your Data</h2>
              <p className="mb-4 text-sm text-muted-foreground">
                Describe the test data scenario in natural language. The AI Actor-Critic chain will generate a strict configuration.
              </p>
              <textarea
                id="nl-prompt-input"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="e.g. Generate credit scoring data with 60% prime, 25% near-prime, 15% sub-prime borrowers. Include credit scores, annual income, and approval status."
                className="w-full rounded-lg border border-border/50 bg-muted/20 px-4 py-3 text-sm text-foreground placeholder-muted-foreground/50 outline-none transition-all focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
                rows={4}
              />
              <div className="mt-4 flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <label className="text-sm text-muted-foreground">Total Records:</label>
                  <input
                    id="total-records-input"
                    type="number"
                    value={totalRecords}
                    onChange={(e) => setTotalRecords(Math.max(1, parseInt(e.target.value) || 1))}
                    className="w-28 rounded-lg border border-border/50 bg-muted/20 px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
                    min={1}
                    max={10000000}
                  />
                </div>
                <button
                  id="generate-config-btn"
                  onClick={handleGenerateConfig}
                  disabled={configLoading || !prompt.trim()}
                  className="ml-auto rounded-lg bg-gradient-to-r from-blue-500 to-purple-600 px-6 py-2.5 text-sm font-medium text-white shadow-lg shadow-blue-500/25 transition-all hover:shadow-xl hover:shadow-blue-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {configLoading ? (
                    <span className="flex items-center gap-2">
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                      Generating...
                    </span>
                  ) : (
                    "Generate Config →"
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ═══ STEP 2: Review & Edit Config ═══ */}
        {step === "configure" && config && (
          <div className="mx-auto max-w-4xl space-y-6">
            {/* Review Banner */}
            {draftMeta && (
              <div className={`rounded-lg border px-4 py-3 text-sm ${
                draftMeta.review
                  ? "border-yellow-500/30 bg-yellow-500/10 text-yellow-400"
                  : "border-green-500/30 bg-green-500/10 text-green-400"
              }`}>
                {draftMeta.review ? "⚠️ Manual Review Required" : "✓ AI Critic Approved"} — {draftMeta.iterations} iteration(s)
                {draftMeta.feedback && <p className="mt-1 text-xs opacity-80">{draftMeta.feedback}</p>}
              </div>
            )}

            {/* Config Summary Card */}
            <div className="grid grid-cols-5 gap-4">
              {[
                { label: "Columns", value: config.schema_definition.length, color: "blue" },
                { label: "Distributions", value: config.distribution_constraints.length, color: "purple" },
                { label: "Boundaries", value: config.boundary_rules.length, color: "orange" },
                { label: "Dependencies", value: config.interdependent_rules.length, color: "teal" },
                { label: "Total Rows", value: config.total_records.toLocaleString(), color: "green" },
              ].map((card) => (
                <div key={card.label} className="rounded-lg border border-border/50 bg-card/50 p-4 text-center backdrop-blur-sm">
                  <div className="text-xl font-bold text-foreground">{card.value}</div>
                  <div className="text-xs text-muted-foreground">{card.label}</div>
                </div>
              ))}
            </div>

            {/* Schema Definition */}
            <ConfigSection title="📋 Schema Definition" defaultOpen>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/30 text-left text-xs text-muted-foreground">
                      <th className="pb-2 pr-4">Column Name</th>
                      <th className="pb-2 pr-4">Data Type</th>
                      <th className="pb-2 pr-4">Nullable</th>
                      <th className="pb-2">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {config.schema_definition.map((col, i) => (
                      <tr key={i} className="border-b border-border/10">
                        <td className="py-2.5 pr-4 font-mono text-xs text-blue-400">{col.column_name}</td>
                        <td className="py-2.5 pr-4">
                          <span className="rounded bg-muted/50 px-2 py-0.5 text-xs">{col.data_type}</span>
                        </td>
                        <td className="py-2.5 pr-4 text-xs">{col.nullable ? "Yes" : "No"}</td>
                        <td className="py-2.5 text-xs text-muted-foreground">{col.description || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </ConfigSection>

            {/* Distribution Constraints */}
            {config.distribution_constraints.length > 0 && (
              <ConfigSection title="📊 Distribution Constraints" defaultOpen>
                {config.distribution_constraints.map((dc, i) => (
                  <div key={i} className="mb-4 last:mb-0">
                    <div className="mb-2 font-mono text-sm text-purple-400">{dc.column_name}</div>
                    <div className="flex flex-wrap gap-2">
                      {dc.categories.map((cat, j) => (
                        <div key={j} className="flex items-center gap-2 rounded-lg border border-border/30 bg-muted/20 px-3 py-1.5">
                          <span className="text-sm">{cat}</span>
                          <span className="rounded bg-purple-500/20 px-2 py-0.5 text-xs font-medium text-purple-400">
                            {dc.ratios[j]}%
                          </span>
                        </div>
                      ))}
                    </div>
                    {/* Visual bar */}
                    <div className="mt-2 flex h-3 overflow-hidden rounded-full">
                      {dc.categories.map((cat, j) => (
                        <div
                          key={j}
                          style={{ width: `${dc.ratios[j]}%` }}
                          className={`transition-all ${
                            ["bg-blue-500", "bg-purple-500", "bg-orange-500", "bg-green-500", "bg-pink-500"][j % 5]
                          }`}
                          title={`${cat}: ${dc.ratios[j]}%`}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </ConfigSection>
            )}

            {/* Boundary Rules */}
            {config.boundary_rules.length > 0 && (
              <ConfigSection title="🎯 Boundary Rules" defaultOpen>
                {config.boundary_rules.map((br, i) => (
                  <div key={i} className="mb-3 flex items-center gap-3 rounded-lg border border-border/30 bg-muted/20 px-4 py-3 last:mb-0">
                    <span className="font-mono text-sm text-orange-400">{br.column_name}</span>
                    <span className="rounded bg-muted/60 px-2 py-0.5 text-xs font-medium">{br.operator}</span>
                    <span className="text-sm">{Array.isArray(br.value) ? br.value.join(" – ") : String(br.value)}</span>
                    <span className="ml-auto rounded bg-blue-500/20 px-2 py-0.5 text-xs text-blue-400">{br.action}</span>
                  </div>
                ))}
              </ConfigSection>
            )}

            {/* Interdependent Rules */}
            {config.interdependent_rules && config.interdependent_rules.length > 0 && (
              <ConfigSection title="🔗 Interdependent Rules" defaultOpen>
                {config.interdependent_rules.map((ir, i) => (
                  <div key={i} className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-border/30 bg-muted/20 px-4 py-3 last:mb-0">
                    <span className="text-sm text-muted-foreground">If</span>
                    <span className="font-mono text-sm text-purple-400">{ir.condition_column}</span>
                    <span className="rounded bg-muted/60 px-2 py-0.5 text-xs font-medium">{ir.condition_operator}</span>
                    <span className="text-sm">{Array.isArray(ir.condition_value) ? ir.condition_value.join(" – ") : String(ir.condition_value)}</span>
                    <span className="text-sm text-muted-foreground">then</span>
                    <span className="font-mono text-sm text-teal-400">{ir.target_column}</span>
                    <span className="text-sm font-medium text-muted-foreground">=</span>
                    <span className="text-sm font-medium">{Array.isArray(ir.target_fill_value) ? ir.target_fill_value.join(" – ") : String(ir.target_fill_value)}</span>
                    {ir.description && <span className="ml-auto text-xs text-muted-foreground">({ir.description})</span>}
                  </div>
                ))}
              </ConfigSection>
            )}

            {/* Total Records Editor */}
            <div className="rounded-xl border border-border/50 bg-card/50 p-4 backdrop-blur-sm">
              <label className="mb-2 block text-sm font-medium">Total Records</label>
              <input
                type="number"
                value={config.total_records}
                onChange={(e) => {
                  const val = Math.max(1, parseInt(e.target.value) || 1);
                  setConfig({ ...config, total_records: val });
                }}
                className="w-40 rounded-lg border border-border/50 bg-muted/20 px-3 py-2 text-sm outline-none focus:border-primary/50"
                min={1}
                max={10000000}
              />
            </div>

            {/* Actions */}
            <div className="flex items-center gap-4">
              <button
                onClick={() => setStep("upload")}
                className="rounded-lg border border-border/50 px-5 py-2.5 text-sm text-muted-foreground transition-all hover:bg-muted/30"
              >
                ← Back
              </button>
              <button
                id="approve-and-generate-btn"
                onClick={handleExecute}
                className="ml-auto rounded-lg bg-gradient-to-r from-green-500 to-emerald-600 px-8 py-2.5 text-sm font-medium text-white shadow-lg shadow-green-500/25 transition-all hover:shadow-xl hover:shadow-green-500/30"
              >
                ✓ Approve & Generate
              </button>
            </div>
          </div>
        )}

        {/* ═══ STEP 3: Generation Progress ═══ */}
        {step === "generate" && (
          <div className="mx-auto max-w-2xl space-y-6">
            <div className="rounded-xl border border-border/50 bg-card/50 p-8 text-center backdrop-blur-sm">
              <div className="mb-4 text-4xl">⚙️</div>
              <h2 className="mb-2 text-xl font-semibold">Generating Data</h2>
              <p className="mb-6 text-sm text-muted-foreground">
                {wsConnected ? "Connected via WebSocket — streaming live progress" : "Polling for updates..."}
              </p>

              {/* Progress Bar */}
              {(progress || jobStatus?.progress) && (() => {
                const p = progress || jobStatus!.progress!;
                return (
                  <div className="space-y-4">
                    <div className="relative h-4 overflow-hidden rounded-full bg-muted/30">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-blue-500 to-purple-600 transition-all duration-500"
                        style={{ width: `${p.progress_percent}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">
                        {p.rows_processed.toLocaleString()} / {p.total_rows.toLocaleString()} rows
                      </span>
                      <span className="font-medium text-primary">{p.progress_percent}%</span>
                    </div>
                    <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
                      <span>Stage: <span className="text-foreground">{p.current_stage}</span></span>
                      <span>Chunk: <span className="text-foreground">{p.current_chunk}/{p.total_chunks}</span></span>
                    </div>
                    {p.message && <p className="text-xs text-muted-foreground">{p.message}</p>}
                  </div>
                );
              })()}

              {!progress && !jobStatus?.progress && (
                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
                  Starting generation engine...
                </div>
              )}
            </div>
          </div>
        )}

        {/* ═══ STEP 4: Results ═══ */}
        {step === "results" && jobStatus && (
          <div className="mx-auto max-w-3xl space-y-6">
            {/* Status Banner */}
            <div className={`rounded-xl border p-6 text-center ${
              jobStatus.status === "completed"
                ? "border-green-500/30 bg-green-500/10"
                : "border-red-500/30 bg-red-500/10"
            }`}>
              <div className="mb-2 text-4xl">{jobStatus.status === "completed" ? "✅" : "❌"}</div>
              <h2 className="text-xl font-semibold">
                {jobStatus.status === "completed" ? "Generation Complete!" : "Generation Failed"}
              </h2>
              {jobStatus.error && <p className="mt-2 text-sm text-red-400">{jobStatus.error}</p>}
            </div>

            {/* Validation Results */}
            {jobStatus.validation && (
              <div className="rounded-xl border border-border/50 bg-card/50 p-6 backdrop-blur-sm">
                <h3 className="mb-4 text-lg font-semibold">
                  📊 Validation Results
                  <span className={`ml-2 rounded-full px-3 py-0.5 text-xs ${
                    jobStatus.validation.is_valid
                      ? "bg-green-500/20 text-green-400"
                      : "bg-red-500/20 text-red-400"
                  }`}>
                    {jobStatus.validation.is_valid ? "ALL PASS" : "ISSUES FOUND"}
                  </span>
                </h3>

                <div className="mb-3 text-sm text-muted-foreground">
                  Total rows generated: <span className="font-medium text-foreground">
                    {jobStatus.validation.total_rows_generated.toLocaleString()}
                  </span>
                </div>

                {/* Distribution Checks */}
                {jobStatus.validation.distribution_checks.length > 0 && (
                  <div className="mb-4">
                    <h4 className="mb-2 text-sm font-medium text-muted-foreground">Distribution Accuracy</h4>
                    {jobStatus.validation.distribution_checks.map((dc, i) => (
                      <div key={i} className="mb-2 rounded-lg border border-border/30 bg-muted/10 p-3">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-sm text-purple-400">{dc.column_name}</span>
                          <span className={`rounded-full px-2 py-0.5 text-xs ${
                            dc.is_pass ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                          }`}>
                            {dc.is_pass ? "PASS" : "FAIL"} — {dc.deviation}% deviation
                          </span>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <span className="text-muted-foreground">Expected: </span>
                            {Object.entries(dc.expected_ratios).map(([k, v]) => `${k}:${v}%`).join(", ")}
                          </div>
                          <div>
                            <span className="text-muted-foreground">Actual: </span>
                            {Object.entries(dc.actual_ratios).map(([k, v]) => `${k}:${v}%`).join(", ")}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Boundary Checks */}
                {jobStatus.validation.boundary_checks.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-sm font-medium text-muted-foreground">Boundary Rules</h4>
                    {jobStatus.validation.boundary_checks.map((bc, i) => (
                      <div key={i} className="mb-2 flex items-center justify-between rounded-lg border border-border/30 bg-muted/10 p-3">
                        <span className="text-sm">
                          <span className="font-mono text-orange-400">{bc.column_name}</span>
                          {" "}{bc.operator} {bc.value}
                        </span>
                        <span className={`rounded-full px-2 py-0.5 text-xs ${
                          bc.is_pass ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                        }`}>
                          {bc.boundary_rows_found} rows — {bc.is_pass ? "PASS" : "FAIL"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-4">
              <button
                onClick={handleReset}
                className="rounded-lg border border-border/50 px-5 py-2.5 text-sm text-muted-foreground transition-all hover:bg-muted/30"
              >
                ← Start New
              </button>
              {jobStatus.status === "completed" && jobId && (
                <a
                  id="download-csv-btn"
                  href={getExportUrl(jobId)}
                  download
                  className="ml-auto rounded-lg bg-gradient-to-r from-blue-500 to-purple-600 px-6 py-2.5 text-sm font-medium text-white shadow-lg shadow-blue-500/25 transition-all hover:shadow-xl hover:shadow-blue-500/30"
                >
                  📥 Download CSV
                </a>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer spacer */}
      <div className="h-20" />
    </div>
  );
}


/* ═══════════════════════════════════════════════
   Sub-Components
   ═══════════════════════════════════════════════ */

function FileDropZone({
  onFile,
  loading,
  currentFile,
}: {
  onFile: (file: File) => void;
  loading: boolean;
  currentFile: File | null;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) onFile(file);
      }}
      onClick={() => inputRef.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-all ${
        dragOver
          ? "border-primary bg-primary/5"
          : currentFile
          ? "border-green-500/50 bg-green-500/5"
          : "border-border/50 hover:border-primary/30 hover:bg-muted/10"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
          Extracting schema...
        </div>
      ) : currentFile ? (
        <div className="text-center">
          <div className="mb-1 text-2xl">📄</div>
          <div className="text-sm font-medium text-green-400">{currentFile.name}</div>
          <div className="text-xs text-muted-foreground">Click or drop to replace</div>
        </div>
      ) : (
        <div className="text-center">
          <div className="mb-1 text-2xl">📁</div>
          <div className="text-sm text-muted-foreground">Drop a CSV file here, or click to browse</div>
        </div>
      )}
    </div>
  );
}

function ConfigSection({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-xl border border-border/50 bg-card/50 backdrop-blur-sm overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-6 py-4 text-left transition-colors hover:bg-muted/10"
      >
        <h3 className="text-lg font-semibold">{title}</h3>
        <span className={`text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}>▼</span>
      </button>
      {open && <div className="border-t border-border/30 px-6 py-4">{children}</div>}
    </div>
  );
}

export default App;
