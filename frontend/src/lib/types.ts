/* ──────────────────────────────────────────────
   TypeScript Types matching Backend Pydantic Schemas
   ────────────────────────────────────────────── */

export interface ColumnDefinition {
  column_name: string;
  data_type: string;
  nullable: boolean;
  description?: string;
}

export interface DistributionConstraint {
  column_name: string;
  categories: string[];
  ratios: number[];
}

export interface BoundaryRule {
  column_name: string;
  operator: string;
  value: number | string | number[];
  action: string;
  description?: string;
}

export interface InterdependentRule {
  target_column: string;
  condition_column: string;
  condition_operator: string;
  condition_value: any;
  target_fill_value: any;
  description?: string;
}

export interface GenerationConfig {
  config_id: string;
  schema_definition: ColumnDefinition[];
  distribution_constraints: DistributionConstraint[];
  boundary_rules: BoundaryRule[];
  interdependent_rules: InterdependentRule[];
  total_records: number;
}

export interface DraftConfigResponse {
  config: GenerationConfig;
  requires_manual_review: boolean;
  critic_feedback?: string;
  actor_critic_iterations: number;
}

export interface CsvColumnInfo {
  column_name: string;
  pandas_dtype: string;
  inferred_type: string;
  sample_values: string[];
  null_count: number;
}

export interface CsvSchemaResponse {
  filename: string;
  total_columns: number;
  rows_sampled: number;
  columns: CsvColumnInfo[];
}

export interface GenerationJobResponse {
  job_id: string;
  status: string;
  message: string;
  total_records: number;
  total_chunks: number;
}

export interface GenerationProgress {
  job_id: string;
  status: string;
  current_stage: string;
  current_chunk: number;
  total_chunks: number;
  rows_processed: number;
  total_rows: number;
  progress_percent: number;
  message?: string;
}

export interface DistributionCheck {
  column_name: string;
  expected_ratios: Record<string, number>;
  actual_ratios: Record<string, number>;
  is_pass: boolean;
  deviation: number;
}

export interface BoundaryCheck {
  column_name: string;
  operator: string;
  value: string;
  boundary_rows_found: number;
  is_pass: boolean;
}

export interface ValidationResult {
  is_valid: boolean;
  distribution_checks: DistributionCheck[];
  boundary_checks: BoundaryCheck[];
  total_rows_generated: number;
}

export interface JobStatusResponse {
  job_id: string;
  status: string;
  total_records: number;
  total_chunks: number;
  output_path?: string;
  error?: string;
  progress?: GenerationProgress;
  validation?: ValidationResult;
}

export type AppStep = "upload" | "configure" | "generate" | "results";
