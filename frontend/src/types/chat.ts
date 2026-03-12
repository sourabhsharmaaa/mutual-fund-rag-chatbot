export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  source_urls?: string[];
  guardrail_triggered?: boolean;
  timestamp?: Date;
  activeFunds?: string[];   // which funds were selected when user sent this message
  scopedFund?: string;      // specific fund this assistant response is scoped to
}
