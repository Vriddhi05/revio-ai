import { ArrowRight, MessageCircleMore } from "lucide-react";

export default function EmptyState({ title, description, actionLabel, onAction }) {
  return (
    <div className="empty-state">
      <span className="empty-icon"><MessageCircleMore size={23} strokeWidth={1.6} /></span>
      <h3>{title}</h3>
      <p>{description}</p>
      {actionLabel && <button type="button" className="text-action" onClick={onAction}>{actionLabel}<ArrowRight size={15} /></button>}
    </div>
  );
}
