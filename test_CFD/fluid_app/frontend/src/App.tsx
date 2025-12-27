import { Canvas, useFrame, useLoader } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'

import './App.css'
import { fetchRunResult, getRunStatus, startSimulation, type Quality, type RunStatus } from './api'
import { parseNpz } from './npz'

type Vec3 = [number, number, number]

function normalize(v: Vec3): Vec3 {
  const n = Math.hypot(v[0], v[1], v[2])
  if (n < 1e-9) return [0, 0, -1]
  return [v[0] / n, v[1] / n, v[2] / n]
}

function GravityArrow({ gravity }: { gravity: Vec3 }) {
  const g = normalize(gravity)
  const dir = useMemo(() => new THREE.Vector3(g[0], g[1], g[2]).normalize(), [g])
  return <arrowHelper args={[dir, new THREE.Vector3(0, 0, 0), 60, 0x111111]} />
}

function Scene(props: {
  gravity: Vec3
  sourcePoint: Vec3 | null
  onPickSource: (p: Vec3) => void
  particleFrames: { data: Float32Array; shape: number[] } | null
  isPlaying: boolean
  setIsPlaying: (v: boolean) => void
}) {
  const stl = useLoader(STLLoader, '/api/stl')

  const meshGeom = useMemo(() => {
    const g = stl as THREE.BufferGeometry
    g.computeVertexNormals()
    g.center()
    return g
  }, [stl])

  const particleGeomRef = useRef<THREE.BufferGeometry>(null)
  const frameRef = useRef({ idx: 0, acc: 0 })

  // Init particle geometry when frames arrive.
  useEffect(() => {
    if (!props.particleFrames || !particleGeomRef.current) return
    const { shape, data } = props.particleFrames
    if (shape.length !== 3 || shape[2] !== 3) return

    const nParticles = shape[1]
    const positions = new Float32Array(nParticles * 3)
    positions.set(data.subarray(0, nParticles * 3))
    particleGeomRef.current.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    particleGeomRef.current.computeBoundingSphere()
    frameRef.current = { idx: 0, acc: 0 }
    props.setIsPlaying(true)
  }, [props.particleFrames, props.setIsPlaying])

  useFrame((_, delta) => {
    if (!props.particleFrames || !particleGeomRef.current) return
    if (!props.isPlaying) return

    const { shape, data } = props.particleFrames
    if (shape.length !== 3 || shape[2] !== 3) return
    const nFrames = shape[0]
    const nParticles = shape[1]

    frameRef.current.acc += delta
    const frameStep = 1 / 30
    if (frameRef.current.acc < frameStep) return
    frameRef.current.acc = 0
    frameRef.current.idx = (frameRef.current.idx + 1) % nFrames

    const start = frameRef.current.idx * nParticles * 3
    const end = start + nParticles * 3
    const attr = particleGeomRef.current.getAttribute('position') as THREE.BufferAttribute
    ;(attr.array as Float32Array).set(data.subarray(start, end))
    attr.needsUpdate = true
  })

  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[80, 80, 80]} intensity={0.7} />
      <OrbitControls makeDefault />

      <mesh
        geometry={meshGeom}
        onPointerDown={(e) => {
          e.stopPropagation()
          props.onPickSource([e.point.x, e.point.y, e.point.z])
        }}
      >
        <meshStandardMaterial color={0xbdbdbd} metalness={0.0} roughness={0.9} />
      </mesh>

      <GravityArrow gravity={props.gravity} />

      {props.sourcePoint ? (
        <mesh position={props.sourcePoint}>
          <sphereGeometry args={[2.0, 16, 16]} />
          <meshStandardMaterial color={0x111111} />
        </mesh>
      ) : null}

      {props.particleFrames ? (
        <points>
          <bufferGeometry ref={particleGeomRef} />
          <pointsMaterial size={1.3} color={0x1f1f1f} sizeAttenuation />
        </points>
      ) : null}
    </>
  )
}

export default function App() {
  const [gravityPreset, setGravityPreset] = useState<'-Z' | '+Z' | '-Y' | '+Y' | '-X' | '+X'>('-Z')
  const gravity: Vec3 = useMemo(() => {
    switch (gravityPreset) {
      case '+Z':
        return [0, 0, 1]
      case '-Z':
        return [0, 0, -1]
      case '+Y':
        return [0, 1, 0]
      case '-Y':
        return [0, -1, 0]
      case '+X':
        return [1, 0, 0]
      case '-X':
        return [-1, 0, 0]
    }
  }, [gravityPreset])

  const [sourcePoint, setSourcePoint] = useState<Vec3 | null>(null)
  const [flowGph, setFlowGph] = useState(200)
  const [quality, setQuality] = useState<Quality>('medium')
  const [status, setStatus] = useState<RunStatus | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [particleFrames, setParticleFrames] = useState<{ data: Float32Array; shape: number[] } | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)

  async function onRun() {
    if (!sourcePoint) return
    setParticleFrames(null)
    setIsPlaying(false)
    setStatus({ state: 'queued', progress: 0, message: 'starting…' })

    const { runId } = await startSimulation({
      sourcePointMm: sourcePoint,
      gravity,
      flowGph,
      quality,
    })
    setRunId(runId)

    // Poll status until done.
    for (;;) {
      const s = await getRunStatus(runId)
      setStatus(s)
      if (s.state === 'done') break
      if (s.state === 'error') return
      await new Promise((r) => setTimeout(r, 800))
    }

    const buf = await fetchRunResult(runId)
    const npz = parseNpz(buf)
    const frames = npz['frames']
    if (!frames || !(frames.data instanceof Float32Array)) {
      throw new Error('Result missing frames')
    }
    setParticleFrames({ data: frames.data, shape: frames.shape })
  }

  return (
    <div className="layout">
      <div className="panel">
        <div className="title">CFD / Gravity Flow (STL)</div>

        <label>
          Gravity direction
          <select value={gravityPreset} onChange={(e) => setGravityPreset(e.target.value as any)}>
            <option value="-Z">-Z</option>
            <option value="+Z">+Z</option>
            <option value="-Y">-Y</option>
            <option value="+Y">+Y</option>
            <option value="-X">-X</option>
            <option value="+X">+X</option>
          </select>
        </label>

        <label>
          Flow rate (GPH)
          <input
            type="number"
            min={0}
            step={10}
            value={flowGph}
            onChange={(e) => setFlowGph(Number(e.target.value))}
          />
        </label>

        <label>
          Rendering intensity
          <select value={quality} onChange={(e) => setQuality(e.target.value as Quality)}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </label>

        <div className="hint">
          Click the STL to pick the water source point.
        </div>

        <button className="run" onClick={onRun} disabled={!sourcePoint || (status?.state === 'running')}>
          Build to go
        </button>

        <button className="run" onClick={() => setIsPlaying((v) => !v)} disabled={!particleFrames}>
          {isPlaying ? 'Pause' : 'Play'}
        </button>

        <div className="status">
          <div>Run: {runId ?? '—'}</div>
          <div>State: {status?.state ?? '—'}</div>
          <div>Progress: {status ? Math.round(status.progress * 100) : 0}%</div>
          <div className="statusMsg">{status?.message ?? ''}</div>
        </div>
      </div>

      <div className="viewport">
        <Canvas camera={{ position: [0, 0, 180], fov: 45 }}>
          <Scene
            gravity={gravity}
            sourcePoint={sourcePoint}
            onPickSource={setSourcePoint}
            particleFrames={particleFrames}
            isPlaying={isPlaying}
            setIsPlaying={setIsPlaying}
          />
        </Canvas>
      </div>
    </div>
  )
}
