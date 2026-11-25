/**
 * Small progress pieces shared by the module page and practice mode:
 * a unit's mastery status and its next spaced-review date.
 */
import type { UnitProgress } from "@/lib/yaxa-api";

export const STATUS_LABEL = { new: "Not started", practising: "Practising", mastered: "Mastered" } as const;

export function StatusChip({ status }: { status: UnitProgress["status"] }) {
  return <span className={`yx-status yx-status-${status}`}>{STATUS_LABEL[status]}</span>;
}

/** "Review due", or when the next review falls, e.g. "Review 3 Dec". */
export function ReviewLabel({ review }: { review: UnitProgress["review"] }) {
  if (!review) return null;
  if (review.due) {
    return (
      <span className="yx-status yx-status-due" title={`About ${Math.round(review.recall * 100)}% likely you still remember this`}>
        Review due
      </span>
    );
  }
  const when = new Date(`${review.next_review}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return (
    <span className="yx-muted" style={{ fontSize: 12.5 }} title="Yaxa will ask you about this unit again then, so it sticks">
      Review {when}
    </span>
  );
}
