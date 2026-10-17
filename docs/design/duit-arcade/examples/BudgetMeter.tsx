import type { CSSProperties } from 'react';

type BudgetState = 'on-track' | 'ahead' | 'over';
type Props = {
  label: string;
  spentCents: number;
  budgetCents: number | null;
  /** Business rules supply the state, including weekly/scheduled cadence. */
  state: BudgetState;
  /** Optional elapsed proportion of this meter's period, between 0 and 1. */
  pace?: number;
};

const labels: Record<BudgetState, string> = {
  'on-track': 'On track', ahead: 'Ahead of pace', over: 'Over budget',
};
const rm = (cents: number) => 'RM ' + (cents / 100).toLocaleString('en-MY', {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export function BudgetMeter({ label, spentCents, budgetCents, state, pace }: Props) {
  if (!Number.isSafeInteger(spentCents) || (budgetCents !== null && !Number.isSafeInteger(budgetCents))) {
    return <p>{label}: amount unavailable</p>;
  }
  if (budgetCents === null || budgetCents <= 0) {
    return <p><strong>{label}</strong> · {rm(spentCents)} spent · No budget set</p>;
  }

  const actualPercent = spentCents / budgetCents * 100;
  const visiblePercent = clamp(actualPercent, 0, 100);
  const hasPace = pace !== undefined && Number.isFinite(pace);
  const pacePercent = hasPace ? clamp(pace!, 0, 1) * 100 : 0;
  // Overspend always remains explicit even if a caller passed a stale status.
  const resolvedState: BudgetState = spentCents > budgetCents ? 'over' : state;
  const css = {
    '--value': `${visiblePercent}%`, '--pace': `${pacePercent}%`,
  } as CSSProperties;
  const overage = spentCents > budgetCents ? `; ${rm(spentCents - budgetCents)} over` : '';

  return <div className="du-budget">
    <div className="du-budget-label">
      <strong>{label}</strong><span className="du-budget-value">{rm(spentCents)} / {rm(budgetCents)}</span>
    </div>
    <div className={`du-meter du-status--${resolvedState}${hasPace ? ' du-meter--hero' : ''}`}
      style={css} role="progressbar" aria-label={label}
      aria-valuemin={0} aria-valuemax={budgetCents}
      aria-valuenow={clamp(spentCents, 0, budgetCents)}
      aria-valuetext={`${rm(spentCents)} of ${rm(budgetCents)} spent; ${actualPercent.toFixed(1)}%; ${labels[resolvedState]}${overage}`}>
      <span className="du-meter-fill" />
      {hasPace && <span className="du-marker" aria-hidden="true">
        <span>Period {Math.round(pacePercent)}%</span>
      </span>}
    </div>
    <div className="du-budget-foot"><span>{labels[resolvedState]}</span>
      {spentCents > budgetCents && <span>{rm(spentCents - budgetCents)} over</span>}
    </div>
  </div>;
}
