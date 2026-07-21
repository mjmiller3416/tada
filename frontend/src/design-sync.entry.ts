/**
 * design-sync bundle entry (not imported by the app): exactly the components
 * synced to the "Tada UI" project on claude.ai/design — the ui/ primitives
 * plus the reusable presentational app pieces. Behavioral components
 * (AuthGate, HouseholdSection, KidHome, PushSubscribeButton,
 * ServiceWorkerRegister, TaskForm) stay out on purpose: they fetch the API
 * or register browser services on mount.
 */
export {
  AppShell,
  Button,
  Card,
  Burst,
  Confetti,
  Chip,
  FocusCard,
  ProgressDots,
  type NavItem,
  type ButtonVariant,
  type ButtonSize,
  type ChipTone,
} from "@/components/ui";
export { default as DirtinessDot } from "@/components/DirtinessDot";
export { default as SnoozeMenu } from "@/components/SnoozeMenu";
export { default as TaskRow } from "@/components/TaskRow";
