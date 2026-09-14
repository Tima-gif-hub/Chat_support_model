/** Generated wire types from canonical contracts. */
export const contractVersion = "1.0.0" as const;
export const workspaceId = "anonymous-furniture-company" as const;
export const businessClasses = [
  "availability", "catalog", "pricing", "payment", "order", "delivery", "returns",
  "warranty", "assembly_service", "complaint", "account_privacy", "general_faq",
  "other_out_of_scope",
] as const;
export type BusinessClass = (typeof businessClasses)[number];
export const complaintTypes = [
  "waiting_time", "product_quality", "price", "delivery_delay", "delivery_damage",
  "wrong_item", "missing_item_or_part", "payment_issue", "return_or_refund",
  "service_quality", "staff_interaction", "availability_or_stock", "other",
] as const;
export type ComplaintType = (typeof complaintTypes)[number];
export type ExpectedAction = "answer" | "rag_answer" | "clarify" | "complaint_tool" | "abstain";
export type SafetyClass = "normal" | "sensitive" | "restricted";
export type SubmissionMode = "explicit_request" | "confirmation_required";

export interface ComplaintArguments {
  complaint_text: string;
  category: "complaint";
  complaint_type: ComplaintType;
  customer_context: string;
}
export interface ComplaintDecision extends ComplaintArguments {
  submission_mode: SubmissionMode;
  consent_evidence: string | null;
}
export interface Decision {
  class: BusinessClass;
  intent: string;
  expected_action: ExpectedAction;
  rag_required: boolean;
  safety_class: SafetyClass;
  clarification_question: string | null;
  complaint: ComplaintDecision | null;
}

export type RuntimeEventName =
  | "message.accepted" | "status" | "token" | "citation"
  | "complaint.confirmation_required" | "complaint.submitted" | "completed" | "error";
export interface RuntimeEventData { [key: string]: unknown }
export interface RuntimeEvent {
  event: RuntimeEventName;
  request_id: string;
  sequence: number;
  data: RuntimeEventData;
}
export interface CitationData {
  citation_id: string;
  title: string;
  heading_path: string[];
  source_uri: string;
  updated_at: string;
}
export interface ComplaintSubmission {
  complaint_id: string;
  status: "queued" | "acknowledged" | "resolved" | "failed";
  duplicate: boolean;
  created_at: string;
}

export interface RetrieveRequest {
  query: string;
  as_of?: string | null;
  max_results?: number;
}
export interface Evidence {
  citation_id: `S${1 | 2 | 3 | 4 | 5}`;
  document_id: string;
  chunk_id: string;
  title: string;
  heading_path: string[];
  content: string;
  source_uri: string;
  dense_score: number;
  lexical_score: number;
  reranker_score: number;
  updated_at: string;
}
export interface RetrievalResponse {
  query_id: string;
  index_version: string;
  status: "ok" | "insufficient_evidence";
  evidence: Evidence[];
}

export type ChatRole = "system" | "user" | "assistant" | "tool";
export interface ChatMessage { role: ChatRole; content: string }
export interface ChatCompletionRequest {
  model?: string;
  messages: ChatMessage[];
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  top_k?: number;
  min_p?: number;
  seed?: number | null;
  response_format?: { type?: "text" | "json_object" };
}
export interface ChatCompletionResponse {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: [{ index: 0; message: { role: "assistant"; content: string }; finish_reason: "stop" | "length" }];
  usage: { prompt_tokens: number | null; completion_tokens: number | null; total_tokens: number | null };
  latency_ms: number;
}
