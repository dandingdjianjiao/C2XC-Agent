import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { learnReasoningBank, listReasoningBankDeltas, listReasoningBankJobs, rollbackReasoningBank } from '../api/c2xc'
import type { RbDelta, RbJob } from '../api/types'
import { useT } from '../i18n/i18n'

function formatTs(ts: number | null): string {
  if (!ts) return '—'
  try {
    return new Date(ts * 1000).toLocaleString()
  } catch {
    return String(ts)
  }
}

function opsSummary(delta: RbDelta): string {
  const ops = delta.ops ?? []
  const counts = { add: 0, update: 0, archive: 0, other: 0 }
  for (const op of ops) {
    if (op.op === 'add') counts.add++
    else if (op.op === 'update') counts.update++
    else if (op.op === 'archive') counts.archive++
    else counts.other++
  }
  const parts = []
  if (counts.add) parts.push(`add=${counts.add}`)
  if (counts.update) parts.push(`update=${counts.update}`)
  if (counts.archive) parts.push(`archive=${counts.archive}`)
  if (counts.other) parts.push(`other=${counts.other}`)
  return parts.length ? parts.join(' ') : 'no ops'
}

export function ReasoningBankTab(props: { runId: string; onOpenRBTrace?: () => void }) {
  const t = useT()
  const queryClient = useQueryClient()
  const runId = props.runId

  const jobsQuery = useQuery({
    queryKey: ['rb_jobs', runId],
    queryFn: () => listReasoningBankJobs(runId, 20),
    enabled: !!runId,
    refetchInterval: 2000,
  })

  const deltasQuery = useQuery({
    queryKey: ['rb_deltas', runId],
    queryFn: () => listReasoningBankDeltas(runId),
    enabled: !!runId,
    refetchInterval: 2000,
  })

  const learnMutation = useMutation({
    mutationFn: () => learnReasoningBank(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rb_deltas', runId] })
      queryClient.invalidateQueries({ queryKey: ['rb_jobs', runId] })
      queryClient.invalidateQueries({ queryKey: ['events', runId] })
    },
  })

  const rollbackMutation = useMutation({
    mutationFn: (delta_id: string | null) => rollbackReasoningBank({ run_id: runId, delta_id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rb_deltas', runId] })
      queryClient.invalidateQueries({ queryKey: ['rb_jobs', runId] })
      queryClient.invalidateQueries({ queryKey: ['events', runId] })
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })

  const jobs = jobsQuery.data?.jobs ?? []
  const latestJob: RbJob | null = jobs.length ? jobs[0] : null
  const deltas = deltasQuery.data?.deltas ?? []
  const latestApplied = deltas.find((d) => d.status === 'applied') ?? null

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-fg">{t('run.reasoningbank')}</div>
          <div className="mt-1 text-xs text-muted">{t('rb.learnHint')}</div>
        </div>
        <div className="flex items-center gap-2">
          {props.onOpenRBTrace ? (
            <button
              type="button"
              onClick={() => props.onOpenRBTrace?.()}
              className="rounded-md border border-border bg-bg px-2 py-1 text-xs text-fg hover:border-accent"
            >
              {t('rb.openTraceRb')}
            </button>
          ) : null}
          <button
            type="button"
            disabled={learnMutation.isPending}
            onClick={() => learnMutation.mutate()}
            className="rounded-md border border-border bg-bg px-2 py-1 text-xs text-fg hover:border-accent disabled:opacity-50"
          >
            {learnMutation.isPending ? t('common.loading') : t('rb.learn')}
          </button>
          <button
            type="button"
            disabled={!latestApplied || rollbackMutation.isPending}
            onClick={() => rollbackMutation.mutate(latestApplied?.delta_id ?? null)}
            className="rounded-md border border-border bg-bg px-2 py-1 text-xs text-fg hover:border-accent disabled:opacity-50"
            title={latestApplied ? latestApplied.delta_id : ''}
          >
            {rollbackMutation.isPending ? t('common.loading') : t('rb.rollbackLatest')}
          </button>
        </div>
      </div>

      {learnMutation.error ? (
        <div className="text-sm text-danger">
          {t('common.error')}: {(learnMutation.error as ApiError).message}
        </div>
      ) : null}
      {rollbackMutation.error ? (
        <div className="text-sm text-danger">
          {t('common.error')}: {(rollbackMutation.error as ApiError).message}
        </div>
      ) : null}

      <div className="rounded-md border border-border bg-bg p-3">
        <div className="mb-2 text-xs font-medium text-muted">{t('rb.jobs')}</div>
        {jobsQuery.isLoading ? (
          <div className="text-sm text-muted">{t('common.loading')}</div>
        ) : jobsQuery.error ? (
          <div className="text-sm text-danger">
            {t('common.error')}: {(jobsQuery.error as ApiError).message}
          </div>
        ) : !latestJob ? (
          <div className="text-sm text-muted">{t('rb.noJobs')}</div>
        ) : (
          <div className="grid gap-2">
            <div className="rounded-md border border-border bg-surface px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-mono text-xs text-fg">{latestJob.rb_job_id}</div>
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[11px] ${
                        latestJob.status === 'completed'
                          ? 'border-success text-success'
                          : latestJob.status === 'failed'
                            ? 'border-danger text-danger'
                            : latestJob.status === 'running'
                              ? 'border-accent text-accent'
                              : 'border-muted text-muted'
                      }`}
                    >
                      {latestJob.status}
                    </span>
                    <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted">
                      {latestJob.kind}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-muted">
                    {t('run.createdAt')}: {formatTs(latestJob.created_at)}
                    {latestJob.started_at ? ` · started: ${formatTs(latestJob.started_at)}` : ''}
                    {latestJob.ended_at ? ` · ended: ${formatTs(latestJob.ended_at)}` : ''}
                  </div>
                  {latestJob.status === 'failed' && latestJob.error ? (
                    <div className="mt-2 text-xs text-danger">
                      {t('rb.jobError')}: <span className="font-mono">{latestJob.error}</span>
                    </div>
                  ) : null}
                </div>
                <div className="text-[11px] text-muted">
                  queued: {jobs.filter((j) => j.status === 'queued').length} · running:{' '}
                  {jobs.filter((j) => j.status === 'running').length}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-md border border-border bg-bg p-3">
        <div className="mb-2 text-xs font-medium text-muted">{t('rb.deltas')}</div>
        {deltasQuery.isLoading ? (
          <div className="text-sm text-muted">{t('common.loading')}</div>
        ) : deltasQuery.error ? (
          <div className="text-sm text-danger">
            {t('common.error')}: {(deltasQuery.error as ApiError).message}
          </div>
        ) : deltas.length === 0 ? (
          <div className="text-sm text-muted">{t('rb.noDeltas')}</div>
        ) : (
          <div className="grid gap-2">
            {deltas.map((d) => (
              <div
                key={d.delta_id}
                className="rounded-md border border-border bg-surface px-3 py-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-mono text-xs text-fg">{d.delta_id}</div>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[11px] ${
                          d.status === 'applied'
                            ? 'border-success text-success'
                            : 'border-muted text-muted'
                        }`}
                      >
                        {d.status}
                      </span>
                      <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted">
                        {opsSummary(d)}
                      </span>
                    </div>
                    <div className="mt-1 text-[11px] text-muted">
                      {t('run.createdAt')}: {formatTs(d.created_at)}
                      {d.rolled_back_at ? ` · rolled_back_at: ${formatTs(d.rolled_back_at)}` : ''}
                    </div>
                    {d.rolled_back_reason ? (
                      <div className="mt-1 text-[11px] text-muted">
                        rolled_back_reason: <span className="font-mono">{d.rolled_back_reason}</span>
                      </div>
                    ) : null}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={d.status !== 'applied' || rollbackMutation.isPending}
                      onClick={() => rollbackMutation.mutate(d.delta_id)}
                      className="rounded-md border border-border bg-bg px-2 py-1 text-xs text-fg hover:border-accent disabled:opacity-50"
                    >
                      {rollbackMutation.isPending ? t('common.loading') : t('rb.rollback')}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
