"""Authenticated, bounded-cardinality Prometheus text exposition."""
def render_metrics(store):
    stats=store.statistics()
    workers=store.workers()
    lines=[
        '# HELP agentflow_jobs_total Jobs stored in the queue.',
        '# TYPE agentflow_jobs_total gauge',
        'agentflow_jobs_total '+str(stats['total']),
        '# HELP agentflow_jobs_state Count of jobs in a known state.',
        '# TYPE agentflow_jobs_state gauge',
    ]
    valid=('queued','running','waiting_approval','cancel_requested','succeeded','failed','cancelled','uncertain','restored_hold')
    for name in valid:
        lines.append('agentflow_jobs_state{state="'+name+'"} '+str(stats['states'].get(name,0)))
    lines.extend(['# HELP agentflow_workers_online Workers reporting a recent heartbeat.',
                  '# TYPE agentflow_workers_online gauge',
                  'agentflow_workers_online '+str(sum(bool(w['online']) for w in workers)),
                  '# HELP agentflow_workers_known Worker records reported by the database.',
                  '# TYPE agentflow_workers_known gauge',
                  'agentflow_workers_known '+str(len(workers))])
    return '\n'.join(lines)+'\n'
