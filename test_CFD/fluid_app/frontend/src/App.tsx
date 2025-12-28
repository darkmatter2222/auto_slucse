import { Canvas, useFrame, useLoader } from '@react-three/fiber'
import { OrbitControls, Grid, GizmoHelper, GizmoViewport, TransformControls } from '@react-three/drei'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { TransformControls as TransformControlsImpl } from 'three-stdlib'

import './App.css'
import { fetchRunResult, getRunStatus, startSimulation, type Quality, type RunStatus } from './api'
import { parseNpz } from './npz'

type Vec3 = [number, number, number]

function normalize(v: Vec3): Vec3 {
  const n = Math.hypot(v[0], v[1], v[2])
  if (n < 1e-9) return [0, 0, -1]
  return [v[0] / n, v[1] / n, v[2] / n]
}

function rotateVectorByInverseEuler(v: Vec3, euler: Vec3): Vec3 {
  const rot = new THREE.Euler(euler[0], euler[1], euler[2])
  const q = new THREE.Quaternion().setFromEuler(rot).invert()
  const out = new THREE.Vector3(v[0], v[1], v[2]).applyQuaternion(q)
  return [out.x, out.y, out.z]
}

// Fluid particles rendered as smooth instanced spheres
function FluidParticles({ 
  particleFrames, 
  isPlaying, 
  setIsPlaying, 
  playbackSpeed,
  sizeScale,
}: {
  particleFrames: { data: Float32Array; shape: number[] }
  isPlaying: boolean
  setIsPlaying: (v: boolean) => void
  playbackSpeed: number
  sizeScale: number
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const frameRef = useRef({ idx: 0, acc: 0, initialized: false })
  const lastDataRef = useRef<Float32Array | null>(null)
  const tempMatrix = useMemo(() => new THREE.Matrix4(), [])
  const tempVec = useMemo(() => new THREE.Vector3(), [])

  const { nFrames, nParticles } = useMemo(() => {
    const shape = particleFrames.shape
    if (shape.length !== 3 || shape[2] !== 3) {
      return { nFrames: 0, nParticles: 0 }
    }
    return { nFrames: shape[0], nParticles: shape[1] }
  }, [particleFrames.shape])

  // Particle size based on count (smaller for more particles)
  const baseParticleSize = useMemo(() => {
    if (nParticles > 50000) return 1.2
    if (nParticles > 20000) return 1.8
    return 2.5
  }, [nParticles])

  const particleSize = useMemo(() => {
    const s = Math.max(0.1, Math.min(4.0, baseParticleSize * sizeScale))
    return s
  }, [baseParticleSize, sizeScale])

  useFrame((_, delta) => {
    if (!meshRef.current || nParticles === 0) return

    const { data } = particleFrames

    // Reset state if data changed (new simulation)
    if (data !== lastDataRef.current) {
      lastDataRef.current = data
      frameRef.current = { idx: 0, acc: 0, initialized: false }
    }

    // Initialize on first frame
    if (!frameRef.current.initialized) {
      console.log('Initializing', nParticles, 'fluid particles as spheres')
      frameRef.current = { idx: 0, acc: 0, initialized: true }
      setIsPlaying(true)
    }

    // Advance animation
    if (isPlaying) {
      frameRef.current.acc += delta * playbackSpeed
      const frameStep = 1 / 30
      if (frameRef.current.acc >= frameStep) {
        frameRef.current.acc = 0
        frameRef.current.idx = (frameRef.current.idx + 1) % nFrames
      }
    }

    // Update instance positions
    const start = frameRef.current.idx * nParticles * 3
    for (let i = 0; i < nParticles; i++) {
      const x = data[start + i * 3]
      const y = data[start + i * 3 + 1]
      const z = data[start + i * 3 + 2]
      
      tempVec.set(x, y, z)
      tempMatrix.makeTranslation(tempVec.x, tempVec.y, tempVec.z)
      meshRef.current.setMatrixAt(i, tempMatrix)
    }
    meshRef.current.instanceMatrix.needsUpdate = true
  })

  if (nParticles === 0) return null

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, nParticles]} frustumCulled={false}>
      <sphereGeometry args={[particleSize, 8, 6]} />
      <meshStandardMaterial 
        color={0x38bdf8}
        emissive={0x0ea5e9}
        emissiveIntensity={0.3}
        metalness={0.1}
        roughness={0.3}
        transparent
        opacity={0.9}
      />
    </instancedMesh>
  )
}

function GravityArrow({ gravity, position }: { gravity: Vec3; position: Vec3 }) {
  const g = normalize(gravity)
  const dir = useMemo(() => new THREE.Vector3(g[0], g[1], g[2]).normalize(), [g])
  const pos = useMemo(() => new THREE.Vector3(...position), [position])
  return <arrowHelper args={[dir, pos, 40, 0xef4444, 10, 6]} />
}

// Custom colored axes that are more visible
function ColoredAxes({ size = 100, position }: { size?: number; position: Vec3 }) {
  return (
    <group position={position}>
      {/* X axis - Red */}
      <arrowHelper args={[new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0), size, 0xff4444, size * 0.1, size * 0.05]} />
      {/* Y axis - Green */}
      <arrowHelper args={[new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 0), size, 0x44ff44, size * 0.1, size * 0.05]} />
      {/* Z axis - Blue */}
      <arrowHelper args={[new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, 0), size, 0x4444ff, size * 0.1, size * 0.05]} />
    </group>
  )
}

function Scene(props: {
  gravity: Vec3
  sourcePoint: Vec3 | null
  onPickSource: (p: Vec3) => void
  particleFrames: { data: Float32Array; shape: number[] } | null
  isPlaying: boolean
  setIsPlaying: (v: boolean) => void
  playbackSpeed: number
  showParticles: boolean
  particleSizeScale: number
  showWireframe: boolean
  transformMode: 'translate' | 'rotate' | 'none'
  modelTransform: { position: Vec3; rotation: Vec3 }
  setModelTransform: (t: { position: Vec3; rotation: Vec3 }) => void
}) {
  const stl = useLoader(STLLoader, '/api/stl')
  const meshRef = useRef<THREE.Mesh>(null)
  const modelRef = useRef<THREE.Group>(null)
  const orbitRef = useRef<OrbitControlsImpl>(null)
  const transformRef = useRef<TransformControlsImpl>(null)

  // Safety: if a transform interaction ever leaves orbit disabled, recover.
  // (This can happen if pointer-up occurs outside the canvas.)
  // We still keep zoom enabled while transforming.
  useEffect(() => {
    if (!orbitRef.current) return
    orbitRef.current.enabled = true
    orbitRef.current.enableZoom = true
  }, [props.transformMode])

  // Disable orbit rotate/pan while dragging transform gizmo, but keep zoom.
  useEffect(() => {
    const tc = transformRef.current
    if (!tc) return

    const onDraggingChanged = (event: { value?: boolean }) => {
      const dragging = Boolean(event?.value)
      const orbit = orbitRef.current
      if (!orbit) return
      orbit.enableRotate = !dragging
      orbit.enablePan = !dragging
      orbit.enableZoom = true
      orbit.enabled = true
    }

    ;(tc as any).addEventListener('dragging-changed', onDraggingChanged)
    return () => {
      ;(tc as any).removeEventListener('dragging-changed', onDraggingChanged)
    }
  }, [props.transformMode])

  // Keep original coordinates - DO NOT center! Backend needs original STL coords.
  const meshGeom = useMemo(() => {
    const g = stl as THREE.BufferGeometry
    g.computeVertexNormals()
    g.computeBoundingBox()
    return g
  }, [stl])

  // Get mesh center and size for grid/camera positioning
  const { meshCenter, meshSize } = useMemo(() => {
    if (!meshGeom.boundingBox) return { meshCenter: [0, 0, 0] as Vec3, meshSize: 100 }
    const center = new THREE.Vector3()
    const size = new THREE.Vector3()
    meshGeom.boundingBox.getCenter(center)
    meshGeom.boundingBox.getSize(size)
    return {
      meshCenter: [center.x, center.y, center.z] as Vec3,
      meshSize: Math.max(size.x, size.y, size.z)
    }
  }, [meshGeom])

  // Grid position at the bottom of the model
  const gridPosition = useMemo(() => {
    if (!meshGeom.boundingBox) return [0, 0, 0] as Vec3
    return [meshCenter[0], meshCenter[1], meshGeom.boundingBox.min.z - 5] as Vec3
  }, [meshGeom, meshCenter])

  // Mesh center in WORLD coords (after applying model transform)
  const meshCenterWorld = useMemo(() => {
    const center = new THREE.Vector3(meshCenter[0], meshCenter[1], meshCenter[2])
    const rot = new THREE.Euler(props.modelTransform.rotation[0], props.modelTransform.rotation[1], props.modelTransform.rotation[2])
    center.applyEuler(rot)
    center.add(new THREE.Vector3(props.modelTransform.position[0], props.modelTransform.position[1], props.modelTransform.position[2]))
    return [center.x, center.y, center.z] as Vec3
  }, [meshCenter, props.modelTransform.position, props.modelTransform.rotation])

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.5} />
      <directionalLight position={[200, 200, 200]} intensity={0.8} castShadow />
      <directionalLight position={[-100, 100, -100]} intensity={0.4} />
      <hemisphereLight args={[0x87ceeb, 0x362d1f, 0.3]} />

      {/* Controls */}
      <OrbitControls ref={orbitRef} makeDefault target={meshCenterWorld} enableDamping dampingFactor={0.08} />

      {/* XYZ Gizmo in corner */}
      <GizmoHelper alignment="bottom-right" margin={[80, 80]}>
        <GizmoViewport axisColors={['#ef4444', '#22c55e', '#3b82f6']} labelColor="white" />
      </GizmoHelper>

      {/* Ground grid */}
      <Grid
        position={gridPosition}
        args={[meshSize * 4, meshSize * 4]}
        cellSize={meshSize / 10}
        cellThickness={0.5}
        cellColor="#3b82f6"
        sectionSize={meshSize / 2}
        sectionThickness={1}
        sectionColor="#6366f1"
        fadeDistance={meshSize * 4}
        fadeStrength={1}
        followCamera={false}
        infiniteGrid={true}
      />

      {/* Colored axes at model origin */}
      <ColoredAxes size={meshSize * 0.3} position={gridPosition} />

      {/* STL Mesh with optional transform controls */}
      <group
        ref={modelRef}
        position={props.modelTransform.position}
        rotation={props.modelTransform.rotation}
      >
        <mesh
          ref={meshRef}
          geometry={meshGeom}
          onPointerDown={(e) => {
            if (props.transformMode !== 'none') return // Don't pick source when transforming
            if (!modelRef.current) return
            e.stopPropagation()

            // e.point is WORLD space. Convert it to STL-local space by applying the
            // inverse of the model's current transform.
            const local = modelRef.current.worldToLocal(e.point.clone())
            const pt: Vec3 = [local.x, local.y, local.z]
            console.log('Clicked point (STL local coords):', pt)
            props.onPickSource(pt)
          }}
        >
          <meshStandardMaterial
            color={0xd4d4d8}
            metalness={0.15}
            roughness={0.6}
            wireframe={props.showWireframe}
            transparent={props.showWireframe}
            opacity={props.showWireframe ? 0.4 : 1.0}
          />
        </mesh>

        {/* Wireframe overlay when in wireframe mode */}
        {props.showWireframe && (
          <lineSegments geometry={meshGeom}>
            <lineBasicMaterial color={0x3b82f6} transparent opacity={0.6} />
          </lineSegments>
        )}

        {/* Source point marker (STL-local coords, but rendered under model transform) */}
        {props.sourcePoint && (
          <group position={props.sourcePoint}>
            <mesh>
              <sphereGeometry args={[6, 32, 32]} />
              <meshStandardMaterial color={0x3b82f6} emissive={0x1e40af} emissiveIntensity={0.8} />
            </mesh>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <ringGeometry args={[9, 11, 32]} />
              <meshBasicMaterial color={0x60a5fa} transparent opacity={0.7} side={THREE.DoubleSide} />
            </mesh>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <ringGeometry args={[12, 13, 32]} />
              <meshBasicMaterial color={0x93c5fd} transparent opacity={0.4} side={THREE.DoubleSide} />
            </mesh>
          </group>
        )}

        {/* Particles rendered under same transform so they stay inside the moved/rotated model */}
        {props.particleFrames && props.showParticles && (
          <FluidParticles
            particleFrames={props.particleFrames}
            isPlaying={props.isPlaying}
            setIsPlaying={props.setIsPlaying}
            playbackSpeed={props.playbackSpeed}
            sizeScale={props.particleSizeScale}
          />
        )}
      </group>

      {/* Transform controls when enabled (must NOT be nested inside the controlled group) */}
      {props.transformMode !== 'none' && modelRef.current && (
        <TransformControls
          // Key forces a clean remount when switching modes so the gizmo always appears.
          key={props.transformMode}
          ref={transformRef}
          object={modelRef.current}
          mode={props.transformMode}
          size={0.7}
          onObjectChange={() => {
            if (!modelRef.current) return
            const pos = modelRef.current.position
            const rot = modelRef.current.rotation
            props.setModelTransform({
              position: [pos.x, pos.y, pos.z],
              rotation: [rot.x, rot.y, rot.z]
            })
          }}
        />
      )}

      {/* Gravity arrow - positioned near the model */}
      <GravityArrow
        gravity={props.gravity}
        position={[meshCenterWorld[0] + meshSize * 0.6, meshCenterWorld[1], meshCenterWorld[2] + meshSize * 0.3]}
      />
    </>
  )
}

export default function App() {
  const [gravityPreset, setGravityPreset] = useState<'-Z' | '+Z' | '-Y' | '+Y' | '-X' | '+X'>('-Z')
  const gravity: Vec3 = useMemo(() => {
    switch (gravityPreset) {
      case '+Z': return [0, 0, 1]
      case '-Z': return [0, 0, -1]
      case '+Y': return [0, 1, 0]
      case '-Y': return [0, -1, 0]
      case '+X': return [1, 0, 0]
      case '-X': return [-1, 0, 0]
    }
  }, [gravityPreset])

  const [sourcePoint, setSourcePoint] = useState<Vec3 | null>(null)
  const [flowGph, setFlowGph] = useState(200)
  const [quality, setQuality] = useState<Quality>('medium')
  const [status, setStatus] = useState<RunStatus | null>(null)
  const [particleFrames, setParticleFrames] = useState<{ data: Float32Array; shape: number[] } | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0)
  const [showParticles, setShowParticles] = useState(true)
  const [particleSizeScale, setParticleSizeScale] = useState(0.35)
  const [showWireframe, setShowWireframe] = useState(false)
  const [transformMode, setTransformMode] = useState<'translate' | 'rotate' | 'none'>('none')
  const [modelTransform, setModelTransform] = useState<{ position: Vec3; rotation: Vec3 }>({
    position: [0, 0, 0],
    rotation: [0, 0, 0]
  })

  async function onRun() {
    if (!sourcePoint) return
    setParticleFrames(null)
    setIsPlaying(false)
    setStatus({ state: 'queued', progress: 0, message: 'Initializing...' })

    // The STL can be moved/rotated in the UI, but the backend loads the STL file
    // in its ORIGINAL coordinate system. So we convert world-gravity into STL-local
    // gravity by applying the inverse model rotation.
    const gravityLocal = normalize(rotateVectorByInverseEuler(gravity, modelTransform.rotation))

    const { runId } = await startSimulation({
      sourcePointMm: sourcePoint,
      gravity: gravityLocal,
      flowGph,
      quality,
    })
      void runId

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

  const gravityOptions: { value: typeof gravityPreset; label: string; desc: string }[] = [
    { value: '-X', label: '−X', desc: 'Left' },
    { value: '+X', label: '+X', desc: 'Right' },
    { value: '-Y', label: '−Y', desc: 'Down' },
    { value: '+Y', label: '+Y', desc: 'Up' },
    { value: '-Z', label: '−Z', desc: 'Back' },
    { value: '+Z', label: '+Z', desc: 'Front' },
  ]

  const qualityOptions: { value: Quality; name: string; desc: string }[] = [
    { value: 'low', name: 'Fast', desc: '~15 sec • 15K particles' },
    { value: 'medium', name: 'Balanced', desc: '~30 sec • 40K particles' },
    { value: 'high', name: 'Detailed', desc: '~60 sec • 80K particles' },
  ]

  const isRunning = status?.state === 'running' || status?.state === 'queued'
  const progressPct = status ? Math.round(status.progress * 100) : 0

  return (
    <div className="layout">
      <div className="panel">
        {/* Header */}
        <div className="panel-header">
          <h1 className="panel-title">Fluid Dynamics</h1>
          <p className="panel-subtitle">GPU-Accelerated CFD Simulation</p>
        </div>

        <div className="panel-content">
          {/* Source Point Section */}
          <div className="section">
            <h3 className="section-title">Water Source</h3>
            <div className="source-indicator">
              <div className={`source-dot ${sourcePoint ? 'active' : ''}`} />
              <div className="source-info">
                <div className="source-label">
                  {sourcePoint ? 'Source position (mm)' : 'Click on model to place source'}
                </div>
                {sourcePoint && (
                  <div className="source-coords">
                    X: {sourcePoint[0].toFixed(1)}, Y: {sourcePoint[1].toFixed(1)}, Z: {sourcePoint[2].toFixed(1)}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Gravity Section */}
          <div className="section">
            <h3 className="section-title">Gravity Direction</h3>
            <div className="gravity-selector">
              {gravityOptions.map((opt) => (
                <button
                  key={opt.value}
                  className={`gravity-btn ${gravityPreset === opt.value ? 'active' : ''}`}
                  onClick={() => setGravityPreset(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Flow Rate */}
          <div className="section">
            <h3 className="section-title">Flow Settings</h3>
            <div className="control-group">
              <label className="control-label">
                Flow Rate
                <span className="control-hint">Gallons per hour</span>
              </label>
              <div className="input-with-unit">
                <input
                  type="number"
                  min={10}
                  max={1000}
                  step={10}
                  value={flowGph}
                  onChange={(e) => setFlowGph(Number(e.target.value))}
                />
                <span className="input-unit">GPH</span>
              </div>
            </div>
          </div>

          {/* Quality Selection */}
          <div className="section">
            <h3 className="section-title">Simulation Quality</h3>
            <div className="quality-cards">
              {qualityOptions.map((opt) => (
                <div
                  key={opt.value}
                  className={`quality-card ${quality === opt.value ? 'active' : ''}`}
                  onClick={() => setQuality(opt.value)}
                >
                  <div className="quality-name">{opt.name}</div>
                  <div className="quality-desc">{opt.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Run Button */}
          <button
            className="btn btn-primary"
            onClick={onRun}
            disabled={!sourcePoint || isRunning}
          >
            {isRunning ? (
              <>
                <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                Simulating...
              </>
            ) : (
              '▶ Run Simulation'
            )}
          </button>

          {/* Status */}
          {status && (
            <div className="status-card">
              <div className="status-row">
                <span className="status-label">Status</span>
                <span className={`status-value ${status.state}`}>
                  {status.state === 'done' ? '✓ Complete' : 
                   status.state === 'error' ? '✗ Error' :
                   status.state === 'running' ? '● Running' : '○ Queued'}
                </span>
              </div>
              {isRunning && (
                <div className="progress-container">
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${progressPct}%` }} />
                  </div>
                  <div className="progress-text">{status.message || `${progressPct}%`}</div>
                </div>
              )}
            </div>
          )}

          {/* Playback Controls */}
          {particleFrames && (
            <div className="section">
              <h3 className="section-title">Playback</h3>
              <div className="playback-row">
                <button
                  className={`btn ${isPlaying ? 'btn-secondary' : 'btn-primary'}`}
                  onClick={() => setIsPlaying(!isPlaying)}
                >
                  {isPlaying ? '⏸ Pause' : '▶ Play'}
                </button>
                <button
                  className={`btn ${showParticles ? 'btn-secondary' : 'btn-primary'}`}
                  onClick={() => setShowParticles(!showParticles)}
                >
                  {showParticles ? '◌ Hide Particles' : '◉ Show Particles'}
                </button>
              </div>
              <div className="speed-control">
                <span>Speed</span>
                <input
                  type="range"
                  min={0.25}
                  max={3}
                  step={0.25}
                  value={playbackSpeed}
                  onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
                />
                <span>{playbackSpeed}x</span>
              </div>
              <div className="speed-control">
                <span>Size</span>
                <input
                  type="range"
                  min={0.1}
                  max={2.0}
                  step={0.05}
                  value={particleSizeScale}
                  onChange={(e) => setParticleSizeScale(Number(e.target.value))}
                />
                <span>{particleSizeScale.toFixed(2)}x</span>
              </div>
            </div>
          )}

          {/* Help */}
          {!sourcePoint && (
            <div className="help-box">
              <strong>Getting Started:</strong><br />
              1. Click anywhere on the 3D model to place your water source<br />
              2. Choose gravity direction<br />
              3. Set flow rate and quality<br />
              4. Click "Run Simulation"
            </div>
          )}
        </div>
      </div>

      <div className="viewport">
        <Canvas camera={{ position: [50, 100, 300], fov: 45 }} shadows>
          <color attach="background" args={['#0a0a14']} />
          <fog attach="fog" args={['#0a0a14', 500, 1500]} />
          <Scene
            gravity={gravity}
            sourcePoint={sourcePoint}
            onPickSource={setSourcePoint}
            particleFrames={particleFrames}
            isPlaying={isPlaying}
            setIsPlaying={setIsPlaying}
            playbackSpeed={playbackSpeed}
            showParticles={showParticles}
            particleSizeScale={particleSizeScale}
            showWireframe={showWireframe}
            transformMode={transformMode}
            modelTransform={modelTransform}
            setModelTransform={setModelTransform}
          />
        </Canvas>

        {/* Axis Legend */}
        <div className="axis-legend">
          <div className="axis-row">
            <div className="axis-color x" />
            <span className="axis-name">X axis (red)</span>
          </div>
          <div className="axis-row">
            <div className="axis-color y" />
            <span className="axis-name">Y axis (green)</span>
          </div>
          <div className="axis-row">
            <div className="axis-color z" />
            <span className="axis-name">Z axis (blue)</span>
          </div>
        </div>

        {/* View Controls */}
        <div className="view-controls">
          <button
            className={`view-btn ${transformMode === 'none' ? 'active' : ''}`}
            onClick={() => setTransformMode('none')}
            title="Select / Pick Source"
          >
            ⊙
          </button>
          <button
            className={`view-btn ${transformMode === 'translate' ? 'active' : ''}`}
            onClick={() => setTransformMode('translate')}
            title="Move Model"
          >
            ✥
          </button>
          <button
            className={`view-btn ${transformMode === 'rotate' ? 'active' : ''}`}
            onClick={() => setTransformMode('rotate')}
            title="Rotate Model"
          >
            ↻
          </button>
          <button
            className={`view-btn ${showWireframe ? 'active' : ''}`}
            onClick={() => setShowWireframe(!showWireframe)}
            title="Toggle Wireframe"
          >
            ◇
          </button>
        </div>

        {/* Transform info */}
        {transformMode !== 'none' && (
          <div className="transform-info">
            <div className="transform-mode">
              {transformMode === 'translate' ? '⊞ Move Mode' : '↻ Rotate Mode'}
            </div>
            <div className="transform-hint">
              Drag the gizmo handles to {transformMode === 'translate' ? 'move' : 'rotate'} the model
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
