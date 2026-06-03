/**
 * T056 [US1] Slice 1 home page — renders the `<ChatPanel />`.
 *
 * The predominant disclaimer is mounted in `layout.tsx` (T055) so it is
 * visible above this surface before any chat input is sent.
 */
import { ChatPanel } from "@/components/ChatPanel";

export default function Page() {
  return <ChatPanel />;
}
