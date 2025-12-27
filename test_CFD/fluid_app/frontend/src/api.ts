export type Quality = 'low' | 'medium' | 'high'

export type RunState = 'queued' | 'running' | 'done' | 'error'

export type RunStatus = {
  state: RunState
  progress: number
  message: string
  traceback?: string
}

export async function startSimulation(params: {
  sourcePointMm: [number, number, number]
  gravity: [number, number, number]
  flowGph: number
  quality: Quality
}): Promise<{ runId: string }> {
  const res = await fetch('/api/simulate', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      sourcePointMm: params.sourcePointMm,
      gravity: params.gravity,
      flowGph: params.flowGph,
      quality: params.quality,
    }),
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`startSimulation failed (${res.status}): ${text}`)
  }

  return (await res.json()) as { runId: string }
}

export async function getRunStatus(runId: string): Promise<RunStatus> {
  const res = await fetch(`/api/run/${encodeURIComponent(runId)}/status`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`status failed (${res.status}): ${text}`)
  }
  return (await res.json()) as RunStatus
}

export async function fetchRunResult(runId: string): Promise<ArrayBuffer> {
  const res = await fetch(`/api/run/${encodeURIComponent(runId)}/result`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`result failed (${res.status}): ${text}`)
  }
  return await res.arrayBuffer()
}
