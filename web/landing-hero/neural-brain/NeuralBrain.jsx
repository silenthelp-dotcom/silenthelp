// NeuralBrain, pinned Framer revision dZBfieHBLCQvZdQ9YpK1. See README.md.
import { jsx as _jsx } from "react/jsx-runtime";
import * as React from "react"; // @ts-ignore - brainData.js is a runtime JS module with named exports
import {
  brainMeshVertices,
  brainMeshFaces,
  brainWireVertices,
  brainWireFaces,
} from "./brainData.js";
const INITIAL_YAW = 0;
const INITIAL_PITCH = 0;
const MAX_PITCH = (65 * Math.PI) / 180;
const EDGE_BUCKETS = 6;
const NODE_BUCKETS = 6;
const PULSE_LINE_BUCKETS = 4;
const EDGE_GLOW_BUCKETS = 40;
const EDGE_GLOW_PERCENTILE = 0.94;
const IMPULSE_TRAIL_MS = 260;
const IMPULSE_LEAD_MS = 110;
const IDLE_RESUME_DELAY_MS = 850;
const MESH_UPDATE_INTERVAL_MS = 50;
const ENTER_ANIM_START_CENTER = -1.3;
const SIZE_TIERS = [0.5, 0.7, 1, 1.35, 1.75, 2.2, 2.8];
const SIZE_WEIGHTS = [28, 24, 20, 13, 8, 5, 2];
const SIZE_WEIGHT_TOTAL = SIZE_WEIGHTS.reduce((a, b) => a + b, 0);
function pickSizeTier(r) {
  let target = r * SIZE_WEIGHT_TOTAL;
  for (let i = 0; i < SIZE_TIERS.length; i++) {
    target -= SIZE_WEIGHTS[i];
    if (target <= 0) return SIZE_TIERS[i];
  }
  return SIZE_TIERS[SIZE_TIERS.length - 1];
}
const DISSOLVE_DIR_X = 0.6;
const DISSOLVE_DIR_Y = 0.8;
const DISSOLVE_DIR_Z = 0;
function smoothstep(edge0, edge1, x) {
  const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}
function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}
function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}
function seedHash(n) {
  let x = n | 0;
  x = x ^ 61 ^ (x >>> 16);
  x = x + (x << 3);
  x = x ^ (x >>> 4);
  x = Math.imul(x, 668265261);
  x = x ^ (x >>> 15);
  return (x >>> 0) / 4294967295;
}
function parseHexColor(color) {
  const c = color.trim();
  if (/^#([0-9a-f]{3})$/i.test(c))
    return [
      parseInt(c[1] + c[1], 16),
      parseInt(c[2] + c[2], 16),
      parseInt(c[3] + c[3], 16),
    ];
  if (/^#([0-9a-f]{6})$/i.test(c))
    return [
      parseInt(c.slice(1, 3), 16),
      parseInt(c.slice(3, 5), 16),
      parseInt(c.slice(5, 7), 16),
    ];
  const rgbMatch = c.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i);
  if (rgbMatch) {
    return [
      Math.round(parseFloat(rgbMatch[1])),
      Math.round(parseFloat(rgbMatch[2])),
      Math.round(parseFloat(rgbMatch[3])),
    ];
  }
  return [220, 225, 235];
}
function buildUniqueEdges(faces) {
  const seen = new Set();
  const result = [];
  for (let i = 0; i < faces.length; i++) {
    const f = faces[i];
    for (let j = 0; j < 3; j++) {
      const a = f[j];
      const b = f[(j + 1) % 3];
      const key = a < b ? `${a}_${b}` : `${b}_${a}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(a < b ? [a, b] : [b, a]);
      }
    }
  }
  return result;
}
function getResolvedProps(props) {
  return {
    brainScale: props.brainScale ?? 1.15,
    nodeSize: props.nodeSize ?? 0.55,
    nodeBrightness: props.nodeBrightness ?? 1.08,
    lineBrightness: props.lineBrightness ?? 0.55,
    lineWidth: props.lineWidth ?? 0.6,
    pulseLineWidthMult: props.pulseLineWidthMult ?? 2.5,
    pulseColor: props.pulseColor ?? "#FFFFFF",
    connectionDensity: props.connectionDensity ?? 1,
    meshOpacity: props.meshOpacity ?? 0.045,
    meshColor: props.meshColor ?? "#D8A8B0",
    edgeGlow: props.edgeGlow ?? 0.8,
    dissolveAmount: props.dissolveAmount ?? 0.6,
    dissolveCenter: props.dissolveCenter ?? 0.3,
    dissolveWidth: props.dissolveWidth ?? 0.6,
    densifyAmount: props.densifyAmount ?? 0.5,
    enterAnimEnabled: props.enterAnimEnabled ?? true,
    enterAnimDuration: props.enterAnimDuration ?? 2.6,
    snapBackEnabled: props.snapBackEnabled ?? true,
    pointJitter: props.pointJitter ?? 0.32,
    dragSensitivity: props.dragSensitivity ?? 0.012,
    dragInertia: props.dragInertia ?? 0.87,
    autoRotation: props.autoRotation ?? true,
    autoRotationSpeed: props.autoRotationSpeed ?? 0.03,
    hoverRadius: props.hoverRadius ?? 110,
    hoverStrength: props.hoverStrength ?? 0.75,
    pulseEnabled: props.pulseEnabled ?? true,
    pulseInterval: props.pulseInterval ?? 4.4,
    pulseSpeed: props.pulseSpeed ?? 1,
    pulseBrightness: props.pulseBrightness ?? 1,
    backgroundParticleCount: props.backgroundParticleCount ?? 44,
    backgroundColor: props.backgroundColor ?? "#000000",
    particleColor: props.particleColor ?? "#D9DEE8",
  };
}
/**
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight any-prefer-fixed
 */ export default function NeuralBrain(props) {
  const canvasRef = React.useRef(null);
  const wrapRef = React.useRef(null);
  const isStaticRenderer = props.still;
  const resolvedProps = getResolvedProps(props);
  const propsRef = React.useRef(resolvedProps);
  propsRef.current = resolvedProps;
  const staticRenderKey = isStaticRenderer
    ? JSON.stringify(propsRef.current)
    : "";
  React.useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    if (typeof window === "undefined") return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const meshCanvas = document.createElement("canvas");
    const meshCtx = meshCanvas.getContext("2d");
    if (!meshCtx) return;
    const meshVertsSrc = brainMeshVertices;
    const meshFacesSrc = brainMeshFaces;
    const points = brainWireVertices;
    const edges = buildUniqueEdges(brainWireFaces);
    const valid =
      Array.isArray(points) &&
      points.length > 0 &&
      Array.isArray(edges) &&
      edges.length > 0;
    let extent = 1;
    const adjacencyTemp = Array.from({ length: points.length }, () => []);
    if (valid) {
      extent = 0;
      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        extent = Math.max(
          extent,
          Math.abs(p[0]),
          Math.abs(p[1]),
          Math.abs(p[2]),
        );
      }
      for (let i = 0; i < edges.length; i++) {
        const a = edges[i][0];
        const b = edges[i][1];
        adjacencyTemp[a].push(b);
        adjacencyTemp[b].push(a);
      }
    }
    const adjacency = adjacencyTemp.map((arr) => Int32Array.from(arr));
    const n = points.length;
    const dissolveRaw = new Float32Array(n);
    let dissolveMin = Infinity;
    let dissolveMax = -Infinity;
    for (let i = 0; i < n; i++) {
      const p = points[i];
      const v =
        p[0] * DISSOLVE_DIR_X + p[1] * DISSOLVE_DIR_Y + p[2] * DISSOLVE_DIR_Z;
      dissolveRaw[i] = v;
      if (v < dissolveMin) dissolveMin = v;
      if (v > dissolveMax) dissolveMax = v;
    }
    const dissolveNorm = new Float32Array(n);
    const dissolveRange = Math.max(1e-4, dissolveMax - dissolveMin);
    for (let i = 0; i < n; i++) {
      dissolveNorm[i] = (dissolveRaw[i] - dissolveMin) / dissolveRange;
    }
    const scatterDirX = new Float32Array(n);
    const scatterDirY = new Float32Array(n);
    const scatterMag = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const ang = seedHash(4e4 + i * 7) * Math.PI * 2;
      scatterDirX[i] = Math.cos(ang);
      scatterDirY[i] = Math.sin(ang);
      scatterMag[i] = seedHash(41e3 + i * 11);
    }
    const projX = new Float32Array(n);
    const projY = new Float32Array(n);
    const projZ = new Float32Array(n);
    const depth = new Float32Array(n);
    const dispX = new Float32Array(n);
    const dispY = new Float32Array(n);
    const jitterPhase = new Float32Array(n);
    const jitterDirX = new Float32Array(n);
    const jitterDirY = new Float32Array(n);
    const jitterDirZ = new Float32Array(n);
    const nodeSizeMult = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      jitterPhase[i] = seedHash(7e3 + i) * Math.PI * 2;
      jitterDirX[i] = seedHash(8e3 + i) * 2 - 1;
      jitterDirY[i] = seedHash(9e3 + i) * 2 - 1;
      jitterDirZ[i] = seedHash(1e4 + i) * 2 - 1;
      nodeSizeMult[i] = pickSizeTier(seedHash(6e3 + i));
    }
    const nodeDelay = new Float32Array(n);
    const nodePulse = new Float32Array(n);
    const queue = new Int32Array(n);
    const edgeIndices = [];
    const edgePaths = Array.from({ length: EDGE_BUCKETS }, () => new Path2D());
    const edgeBucketAlpha = new Float32Array(EDGE_BUCKETS);
    const pulsePaths = Array.from(
      { length: PULSE_LINE_BUCKETS },
      () => new Path2D(),
    );
    const pulseBucketAlpha = new Float32Array(PULSE_LINE_BUCKETS);
    const nodePaths = Array.from({ length: NODE_BUCKETS }, () => new Path2D());
    const nodeBucketAlpha = new Float32Array(NODE_BUCKETS);
    const pointDist = new Float32Array(n);
    const pointBucket = new Int32Array(n);
    const edgeFactor = new Float32Array(n);
    const bucketMax = new Float32Array(EDGE_GLOW_BUCKETS);
    const dissolveFade = new Float32Array(n);
    const densifyBoost = new Float32Array(n);
    const meshVertCount = meshVertsSrc.length;
    const meshProjX = new Float32Array(meshVertCount);
    const meshProjY = new Float32Array(meshVertCount);
    const meshProjZ = new Float32Array(meshVertCount);
    const meshFaceOrder = Array.from(
      { length: meshFacesSrc.length },
      (_, i) => i,
    );
    const meshFaceDepth = new Float32Array(meshFacesSrc.length);
    const meshUpdateState = { lastUpdate: -Infinity };
    const rotation = {
      yaw: INITIAL_YAW,
      pitch: INITIAL_PITCH,
      vyaw: 0,
      vpitch: 0,
    };
    const pointer = {
      down: false,
      moved: false,
      id: -1,
      x: -9999,
      y: -9999,
      lastX: 0,
      lastY: 0,
      lastT: 0,
    };
    const interaction = {
      lastInteractionTs: 0,
      resetting: false,
      resetStart: 0,
      fromYaw: 0,
      fromPitch: 0,
    };
    const impulse = { active: false, startTs: 0, lastLaunch: 0 };
    const enterAnim = { startTs: -1, done: false };
    const size = { width: 1, height: 1, dpr: 1 };
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const visible = { current: true };
    let rafId = null;
    let running = false;
    let densityKey = -1;
    let particleCountKey = -1;
    const bgParticles = [];
    const rebuildBackground = (count) => {
      bgParticles.length = 0;
      for (let i = 0; i < count; i++) {
        bgParticles.push({
          x: seedHash(13e3 + i * 13),
          y: seedHash(14e3 + i * 29),
          z: seedHash(15e3 + i * 17),
          size: 0.5 + seedHash(16e3 + i * 7) * 1.6,
          speed: 0.02 + seedHash(17e3 + i * 19) * 0.06,
        });
      }
    };
    const rebuildEdgeFilter = (
      densityValue,
      dissolveAmount,
      dissolveCenter,
      dissolveWidth,
    ) => {
      edgeIndices.length = 0;
      const d = clamp(densityValue, 0.02, 1);
      for (let i = 0; i < edges.length; i++) {
        const a = edges[i][0];
        const b = edges[i][1];
        const avgDissolve = (dissolveNorm[a] + dissolveNorm[b]) * 0.5;
        const dissolveT = smoothstep(
          dissolveCenter - dissolveWidth * 0.5,
          dissolveCenter + dissolveWidth * 0.5,
          avgDissolve,
        );
        const effectiveThreshold = d * (1 - dissolveAmount * dissolveT);
        if (seedHash(2e4 + i * 3) <= effectiveThreshold) edgeIndices.push(i);
      }
    };
    const triggerImpulse = (startNode, now) => {
      nodeDelay.fill(Infinity);
      let qh = 0;
      let qt = 0;
      queue[qt++] = startNode;
      nodeDelay[startNode] = 0;
      while (qh < qt) {
        const v = queue[qh++];
        const dv = nodeDelay[v];
        const adj = adjacency[v];
        for (let i = 0; i < adj.length; i++) {
          const nb = adj[i];
          if (nodeDelay[nb] === Infinity) {
            nodeDelay[nb] = dv + 1;
            queue[qt++] = nb;
          }
        }
      }
      let maxHop = 0;
      for (let i = 0; i < n; i++)
        if (nodeDelay[i] !== Infinity && nodeDelay[i] > maxHop)
          maxHop = nodeDelay[i];
      const targetDurationMs =
        1050 / Math.max(0.2, propsRef.current.pulseSpeed);
      const hopMs = maxHop > 0 ? targetDurationMs / maxHop : targetDurationMs;
      for (let i = 0; i < n; i++)
        if (nodeDelay[i] !== Infinity) nodeDelay[i] *= hopMs;
      impulse.startTs = now;
      impulse.active = true;
      impulse.lastLaunch = now;
    };
    const stopLoop = () => {
      running = false;
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    };
    const startLoop = () => {
      if (running) return;
      running = true;
      rafId = requestAnimationFrame(render);
    };
    const applySize = () => {
      const rect = wrap.getBoundingClientRect();
      size.width = Math.max(1, rect.width);
      size.height = Math.max(1, rect.height);
      size.dpr = Math.min(1.5, window.devicePixelRatio || 1);
      canvas.width = Math.round(size.width * size.dpr);
      canvas.height = Math.round(size.height * size.dpr);
      canvas.style.width = `${size.width}px`;
      canvas.style.height = `${size.height}px`;
      meshCanvas.width = canvas.width;
      meshCanvas.height = canvas.height;
      meshUpdateState.lastUpdate = -Infinity;
    };
    const drawFallbackRing = (now) => {
      const [fr, fg, fb] = parseHexColor(propsRef.current.particleColor);
      for (let i = 0; i < 18; i++) {
        const a = (i / 18) * Math.PI * 2 + now * 35e-5;
        const r = Math.min(size.width, size.height) * (0.09 + (i % 4) * 0.018);
        ctx.fillStyle = `rgba(${fr},${fg},${fb},0.22)`;
        ctx.beginPath();
        ctx.arc(
          size.width * 0.5 + Math.cos(a) * r,
          size.height * 0.5 + Math.sin(a) * r,
          1.15,
          0,
          Math.PI * 2,
        );
        ctx.fill();
      }
    };
    const render = (now, scheduleNextFrame = true) => {
      if (scheduleNextFrame && !running) return;
      const p = propsRef.current;
      if (!p.enterAnimEnabled) enterAnim.done = true;
      if (enterAnim.startTs < 0) enterAnim.startTs = now;
      let effectiveDissolveCenter = p.dissolveCenter;
      if (!enterAnim.done) {
        const durationMs = Math.max(200, p.enterAnimDuration * 1e3);
        const elapsed = now - enterAnim.startTs;
        const t = clamp(elapsed / durationMs, 0, 1);
        const eased = easeInOutCubic(t);
        effectiveDissolveCenter =
          ENTER_ANIM_START_CENTER +
          (p.dissolveCenter - ENTER_ANIM_START_CENTER) * eased;
        if (t >= 1) enterAnim.done = true;
      }
      if (particleCountKey !== p.backgroundParticleCount) {
        particleCountKey = p.backgroundParticleCount;
        rebuildBackground(Math.max(0, Math.floor(p.backgroundParticleCount)));
      }
      const filterSig =
        effectiveDissolveCenter * 100 +
        p.connectionDensity * 1e5 +
        p.dissolveAmount * 1e3 +
        p.dissolveWidth * 10;
      if (densityKey !== filterSig || !enterAnim.done) {
        densityKey = filterSig;
        rebuildEdgeFilter(
          p.connectionDensity,
          p.dissolveAmount,
          effectiveDissolveCenter,
          p.dissolveWidth,
        );
      }
      ctx.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
      ctx.clearRect(0, 0, size.width, size.height);
      ctx.fillStyle = p.backgroundColor;
      ctx.fillRect(0, 0, size.width, size.height);
      if (!valid) {
        drawFallbackRing(now);
        if (scheduleNextFrame) rafId = requestAnimationFrame(render);
        return;
      }
      if (!visible.current) {
        stopLoop();
        return;
      }
      if (interaction.resetting) {
        const t = clamp((now - interaction.resetStart) / 520, 0, 1);
        const e = 1 - Math.pow(1 - t, 3);
        rotation.yaw =
          interaction.fromYaw + (INITIAL_YAW - interaction.fromYaw) * e;
        rotation.pitch =
          interaction.fromPitch + (INITIAL_PITCH - interaction.fromPitch) * e;
        if (t >= 1) interaction.resetting = false;
      }
      if (!pointer.down) {
        rotation.yaw += rotation.vyaw;
        rotation.pitch = clamp(
          rotation.pitch + rotation.vpitch,
          -MAX_PITCH,
          MAX_PITCH,
        );
        rotation.vyaw *= p.dragInertia;
        rotation.vpitch *= p.dragInertia;
        if (Math.abs(rotation.vyaw) < 1e-6) rotation.vyaw = 0;
        if (Math.abs(rotation.vpitch) < 1e-6) rotation.vpitch = 0;
      }
      const canAutoRotate =
        p.autoRotation &&
        !pointer.down &&
        now - interaction.lastInteractionTs > IDLE_RESUME_DELAY_MS &&
        (!reducedMotion || p.autoRotationSpeed <= 0.01);
      if (canAutoRotate) rotation.yaw += p.autoRotationSpeed * 0.0018;
      const sx = Math.sin(rotation.yaw);
      const cx = Math.cos(rotation.yaw);
      const sp = Math.sin(rotation.pitch);
      const cp = Math.cos(rotation.pitch);
      const worldScale =
        (Math.min(size.width, size.height) * 0.6 * p.brainScale) / (2 * extent);
      const camDistance = 3.5 * worldScale;
      const time = now * 0.001;
      const hasPointer = pointer.x > -1e3 && pointer.y > -1e3;
      const denseEdge1 = effectiveDissolveCenter - p.dissolveWidth * 0.5;
      const denseEdge0 = denseEdge1 - p.dissolveWidth;
      for (let i = 0; i < n; i++) {
        const dissolveT = smoothstep(
          effectiveDissolveCenter - p.dissolveWidth * 0.5,
          effectiveDissolveCenter + p.dissolveWidth * 0.5,
          dissolveNorm[i],
        );
        dissolveFade[i] = dissolveT * p.dissolveAmount;
        const denseT = 1 - smoothstep(denseEdge0, denseEdge1, dissolveNorm[i]);
        densifyBoost[i] = 1 + p.densifyAmount * denseT;
      }
      let minDepth = Infinity;
      let maxDepth = -Infinity;
      for (let i = 0; i < n; i++) {
        const src = points[i];
        const j =
          p.pointJitter *
          0.015 *
          extent *
          Math.sin(time * 1.1 + jitterPhase[i]);
        const scatterAmt = dissolveFade[i] * scatterMag[i] * extent * 0.35;
        const px = src[0] + jitterDirX[i] * j + scatterDirX[i] * scatterAmt;
        const py = src[1] + jitterDirY[i] * j + scatterDirY[i] * scatterAmt;
        const pz = src[2] + jitterDirZ[i] * j;
        const x1 = px * cx - pz * sx;
        const z1 = px * sx + pz * cx;
        const y2 = py * cp - z1 * sp;
        const z2 = py * sp + z1 * cp;
        projZ[i] = z2;
        if (z2 < minDepth) minDepth = z2;
        if (z2 > maxDepth) maxDepth = z2;
        const perspective = camDistance / (camDistance + z2 * worldScale * 0.3);
        projX[i] = size.width * 0.5 + x1 * worldScale * perspective;
        projY[i] = size.height * 0.5 - y2 * worldScale * perspective;
      }
      const depthRange = Math.max(1e-4, maxDepth - minDepth);
      for (let i = 0; i < n; i++) {
        const depthNorm = 1 - (projZ[i] - minDepth) / depthRange;
        depth[i] = depthNorm;
        let targetX = 0;
        let targetY = 0;
        if (hasPointer) {
          const dx = projX[i] - pointer.x;
          const dy = projY[i] - pointer.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < p.hoverRadius * p.hoverRadius) {
            const d = Math.sqrt(Math.max(1e-4, d2));
            const f =
              (1 - d / p.hoverRadius) * p.hoverStrength * (6 + 6 * depthNorm);
            targetX = (dx / d) * f;
            targetY = (dy / d) * f;
          }
        }
        dispX[i] += (targetX - dispX[i]) * 0.35;
        dispY[i] += (targetY - dispY[i]) * 0.35;
        if (!hasPointer) {
          dispX[i] *= 0.82;
          dispY[i] *= 0.82;
        }
      }
      let ecx = 0;
      let ecy = 0;
      for (let i = 0; i < n; i++) {
        ecx += projX[i] + dispX[i];
        ecy += projY[i] + dispY[i];
      }
      ecx /= n;
      ecy /= n;
      const edgeBucketSize = (2 * Math.PI) / EDGE_GLOW_BUCKETS;
      const bucketDists = Array.from({ length: EDGE_GLOW_BUCKETS }, () => []);
      for (let i = 0; i < n; i++) {
        const x = projX[i] + dispX[i];
        const y = projY[i] + dispY[i];
        const dx = x - ecx;
        const dy = y - ecy;
        const ang = Math.atan2(dy, dx);
        const dist = Math.sqrt(dx * dx + dy * dy);
        let b = Math.floor((ang + Math.PI) / edgeBucketSize);
        if (b >= EDGE_GLOW_BUCKETS) b = EDGE_GLOW_BUCKETS - 1;
        if (b < 0) b = 0;
        pointDist[i] = dist;
        pointBucket[i] = b;
        bucketDists[b].push(dist);
      }
      for (let b = 0; b < EDGE_GLOW_BUCKETS; b++) {
        if (bucketDists[b].length === 0) {
          bucketMax[b] = 1;
          continue;
        }
        bucketDists[b].sort((a, c) => a - c);
        const idx = Math.min(
          bucketDists[b].length - 1,
          Math.floor(bucketDists[b].length * EDGE_GLOW_PERCENTILE),
        );
        bucketMax[b] = Math.max(1e-4, bucketDists[b][idx]);
      }
      for (let i = 0; i < n; i++) {
        edgeFactor[i] = clamp(pointDist[i] / bucketMax[pointBucket[i]], 0, 1);
      }
      if (p.pulseEnabled) {
        const intervalMs = p.pulseInterval * 1e3;
        if (!impulse.active && now - impulse.lastLaunch >= intervalMs) {
          const regionX = seedHash((now / 1e3) | 0) * 2 - 1;
          let pick = Math.floor(seedHash(((now / 117) | 0) + 991) * n);
          for (let i = 0; i < 8; i++) {
            const idx = (pick + i * 53) % n;
            if (points[idx][0] >= 0 === regionX >= 0) {
              pick = idx;
              break;
            }
          }
          triggerImpulse(pick, now);
        }
      }
      nodePulse.fill(0);
      if (impulse.active) {
        let activeCount = 0;
        for (let i = 0; i < n; i++) {
          const delay = nodeDelay[i];
          if (delay === Infinity) continue;
          const dt = now - impulse.startTs - delay;
          if (dt > -IMPULSE_LEAD_MS && dt < IMPULSE_TRAIL_MS) {
            activeCount++;
            const leader = Math.exp(-Math.abs(dt) / 80);
            const trail = dt > 0 ? Math.exp(-dt / 140) * 0.75 : 0;
            nodePulse[i] = clamp((leader + trail) * p.pulseBrightness, 0, 2.5);
          }
        }
        if (activeCount === 0) impulse.active = false;
      }
      const [pr, pg, pb] = parseHexColor(p.particleColor);
      for (let i = 0; i < bgParticles.length; i++) {
        const b = bgParticles[i];
        const drift = (time * b.speed) % 1;
        ctx.fillStyle = `rgba(${pr},${pg},${pb},${0.12 + b.z * 0.16})`;
        ctx.beginPath();
        ctx.arc(
          ((b.x + drift) % 1) * size.width,
          b.y * size.height,
          b.size,
          0,
          Math.PI * 2,
        );
        ctx.fill();
      }
      if (now - meshUpdateState.lastUpdate > MESH_UPDATE_INTERVAL_MS) {
        meshUpdateState.lastUpdate = now;
        meshCtx.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
        meshCtx.clearRect(0, 0, size.width, size.height);
        for (let i = 0; i < meshVertCount; i++) {
          const src = meshVertsSrc[i];
          const mx1 = src[0] * cx - src[2] * sx;
          const mz1 = src[0] * sx + src[2] * cx;
          const my2 = src[1] * cp - mz1 * sp;
          const mz2 = src[1] * sp + mz1 * cp;
          const mPerspective =
            camDistance / (camDistance + mz2 * worldScale * 0.3);
          meshProjX[i] = size.width * 0.5 + mx1 * worldScale * mPerspective;
          meshProjY[i] = size.height * 0.5 - my2 * worldScale * mPerspective;
          meshProjZ[i] = mz2;
        }
        for (let i = 0; i < meshFacesSrc.length; i++) {
          const face = meshFacesSrc[i];
          meshFaceDepth[i] =
            (meshProjZ[face[0]] + meshProjZ[face[1]] + meshProjZ[face[2]]) / 3;
        }
        meshFaceOrder.sort((a, b) => meshFaceDepth[b] - meshFaceDepth[a]);
        const [mr, mg, mb] = parseHexColor(p.meshColor);
        meshCtx.fillStyle = `rgba(${mr},${mg},${mb},${clamp(p.meshOpacity, 0, 1)})`;
        for (let i = 0; i < meshFaceOrder.length; i++) {
          const face = meshFacesSrc[meshFaceOrder[i]];
          meshCtx.beginPath();
          meshCtx.moveTo(meshProjX[face[0]], meshProjY[face[0]]);
          meshCtx.lineTo(meshProjX[face[1]], meshProjY[face[1]]);
          meshCtx.lineTo(meshProjX[face[2]], meshProjY[face[2]]);
          meshCtx.closePath();
          meshCtx.fill();
        }
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(meshCanvas, 0, 0);
      ctx.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
      edgeBucketAlpha.fill(0);
      for (let i = 0; i < EDGE_BUCKETS; i++) edgePaths[i] = new Path2D();
      pulseBucketAlpha.fill(0);
      for (let i = 0; i < PULSE_LINE_BUCKETS; i++) pulsePaths[i] = new Path2D();
      for (let i = 0; i < edgeIndices.length; i++) {
        const edge = edges[edgeIndices[i]];
        const a = edge[0];
        const b = edge[1];
        const x1 = projX[a] + dispX[a];
        const y1 = projY[a] + dispY[a];
        const x2 = projX[b] + dispX[b];
        const y2 = projY[b] + dispY[b];
        const dep = (depth[a] + depth[b]) * 0.5;
        const pulse = Math.max(nodePulse[a], nodePulse[b]);
        const ef = (edgeFactor[a] + edgeFactor[b]) * 0.5;
        const fade = 1 - (dissolveFade[a] + dissolveFade[b]) * 0.5;
        const boost = (densifyBoost[a] + densifyBoost[b]) * 0.5;
        const alpha = clamp(
          (0.05 + dep * 0.32) *
            p.lineBrightness *
            (1 + p.edgeGlow * ef) *
            fade *
            boost +
            pulse * 0.35,
          0.02,
          0.9,
        );
        const bucket = clamp(
          Math.floor(alpha * EDGE_BUCKETS),
          0,
          EDGE_BUCKETS - 1,
        );
        edgeBucketAlpha[bucket] = Math.max(edgeBucketAlpha[bucket], alpha);
        edgePaths[bucket].moveTo(x1, y1);
        edgePaths[bucket].lineTo(x2, y2);
        if (pulse > 0.04) {
          const pulseNorm = clamp(pulse / 2.5, 0, 1);
          const pulseAlpha = clamp(0.15 + pulseNorm * 0.8, 0.1, 0.95);
          const pBucket = clamp(
            Math.floor(pulseNorm * PULSE_LINE_BUCKETS),
            0,
            PULSE_LINE_BUCKETS - 1,
          );
          pulseBucketAlpha[pBucket] = Math.max(
            pulseBucketAlpha[pBucket],
            pulseAlpha,
          );
          pulsePaths[pBucket].moveTo(x1, y1);
          pulsePaths[pBucket].lineTo(x2, y2);
        }
      }
      ctx.globalCompositeOperation = "lighter";
      ctx.lineWidth = p.lineWidth;
      for (let b = 0; b < EDGE_BUCKETS; b++) {
        if (edgeBucketAlpha[b] <= 0) continue;
        ctx.strokeStyle = `rgba(${pr},${pg},${pb},${edgeBucketAlpha[b]})`;
        ctx.stroke(edgePaths[b]);
      }
      const [pulR, pulG, pulB] = parseHexColor(p.pulseColor);
      for (let b = 0; b < PULSE_LINE_BUCKETS; b++) {
        if (pulseBucketAlpha[b] <= 0) continue;
        const widthMult =
          1 + ((b + 1) / PULSE_LINE_BUCKETS) * (p.pulseLineWidthMult - 1);
        ctx.lineWidth = p.lineWidth * widthMult;
        ctx.strokeStyle = `rgba(${pulR},${pulG},${pulB},${pulseBucketAlpha[b]})`;
        ctx.stroke(pulsePaths[b]);
      }
      ctx.globalCompositeOperation = "source-over";
      nodeBucketAlpha.fill(0);
      for (let i = 0; i < NODE_BUCKETS; i++) nodePaths[i] = new Path2D();
      for (let i = 0; i < n; i++) {
        const d = depth[i];
        const pulse = nodePulse[i];
        const fade = 1 - dissolveFade[i];
        const alpha = clamp(
          (0.22 + d * 0.7) *
            p.nodeBrightness *
            (1 + p.edgeGlow * edgeFactor[i]) *
            fade *
            densifyBoost[i] +
            pulse * 0.35,
          0,
          1,
        );
        if (alpha <= 0.01) continue;
        const radius =
          p.nodeSize *
          nodeSizeMult[i] *
          (0.8 + d * 0.5) *
          (1 + (densifyBoost[i] - 1) * 0.35);
        const bucket = clamp(
          Math.floor(alpha * NODE_BUCKETS),
          0,
          NODE_BUCKETS - 1,
        );
        nodeBucketAlpha[bucket] = Math.max(nodeBucketAlpha[bucket], alpha);
        const px = projX[i] + dispX[i];
        const py = projY[i] + dispY[i];
        nodePaths[bucket].moveTo(px + radius, py);
        nodePaths[bucket].arc(px, py, radius, 0, Math.PI * 2);
      }
      for (let b = 0; b < NODE_BUCKETS; b++) {
        if (nodeBucketAlpha[b] <= 0) continue;
        ctx.fillStyle = `rgba(${pr},${pg},${pb},${nodeBucketAlpha[b]})`;
        ctx.fill(nodePaths[b]);
      }
      if (scheduleNextFrame) rafId = requestAnimationFrame(render);
    };
    applySize();
    canvas.style.cursor = "grab";
    rebuildBackground(
      Math.max(0, Math.floor(propsRef.current.backgroundParticleCount)),
    );
    rebuildEdgeFilter(
      propsRef.current.connectionDensity,
      propsRef.current.dissolveAmount,
      propsRef.current.enterAnimEnabled
        ? ENTER_ANIM_START_CENTER
        : propsRef.current.dissolveCenter,
      propsRef.current.dissolveWidth,
    );
    if (isStaticRenderer) {
      enterAnim.done = true;
      const drawStill = () => {
        applySize();
        render(0, false);
      };
      drawStill();
      const observer = new ResizeObserver(drawStill);
      observer.observe(wrap);
      return () => observer.disconnect();
    }
    const onPointerDown = (event) => {
      event.preventDefault();
      pointer.down = true;
      pointer.moved = false;
      pointer.id = event.pointerId;
      pointer.x = event.offsetX;
      pointer.y = event.offsetY;
      pointer.lastX = event.offsetX;
      pointer.lastY = event.offsetY;
      pointer.lastT = performance.now();
      interaction.lastInteractionTs = pointer.lastT;
      rotation.vyaw = 0;
      rotation.vpitch = 0;
      canvas.style.cursor = "grabbing";
      if (canvas.setPointerCapture) canvas.setPointerCapture(event.pointerId);
    };
    const onPointerMove = (event) => {
      pointer.x = event.offsetX;
      pointer.y = event.offsetY;
      if (!pointer.down || pointer.id !== event.pointerId) return;
      const now = performance.now();
      const dx = event.offsetX - pointer.lastX;
      const dy = event.offsetY - pointer.lastY;
      if (Math.abs(dx) + Math.abs(dy) > 1.2) pointer.moved = true;
      const sensitivity = propsRef.current.dragSensitivity;
      rotation.yaw += dx * sensitivity;
      rotation.pitch = clamp(
        rotation.pitch - dy * sensitivity,
        -MAX_PITCH,
        MAX_PITCH,
      );
      const dt = Math.max(1, now - pointer.lastT);
      rotation.vyaw = (dx * sensitivity * 16.67) / dt;
      rotation.vpitch = (-dy * sensitivity * 16.67) / dt;
      pointer.lastX = event.offsetX;
      pointer.lastY = event.offsetY;
      pointer.lastT = now;
      interaction.lastInteractionTs = now;
    };
    const onPointerUp = (event) => {
      if (!pointer.down || pointer.id !== event.pointerId) return;
      pointer.down = false;
      interaction.lastInteractionTs = performance.now();
      if (!pointer.moved && valid) {
        let nearest = -1;
        let best = Infinity;
        for (let i = 0; i < n; i++) {
          const dx = projX[i] + dispX[i] - pointer.x;
          const dy = projY[i] + dispY[i] - pointer.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < best) {
            best = d2;
            nearest = i;
          }
        }
        if (nearest >= 0) triggerImpulse(nearest, performance.now());
      }
      if (pointer.moved && propsRef.current.snapBackEnabled) {
        interaction.resetting = true;
        interaction.resetStart = performance.now();
        interaction.fromYaw = rotation.yaw;
        interaction.fromPitch = rotation.pitch;
        rotation.vyaw = 0;
        rotation.vpitch = 0;
      }
      if (
        canvas.releasePointerCapture &&
        canvas.hasPointerCapture(event.pointerId)
      )
        canvas.releasePointerCapture(event.pointerId);
      canvas.style.cursor = "grab";
    };
    const onPointerLeave = () => {
      pointer.x = -9999;
      pointer.y = -9999;
      if (!pointer.down) canvas.style.cursor = "grab";
    };
    const onDoubleClick = () => {
      interaction.resetting = true;
      interaction.resetStart = performance.now();
      interaction.fromYaw = rotation.yaw;
      interaction.fromPitch = rotation.pitch;
    };
    const resizeObserver = new ResizeObserver(applySize);
    resizeObserver.observe(wrap);
    const intersectionObserver = new IntersectionObserver(
      (entries) => {
        visible.current = !!entries[0]?.isIntersecting;
        if (visible.current) startLoop();
        else stopLoop();
      },
      { threshold: 0.02 },
    );
    intersectionObserver.observe(wrap);
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerLeave);
    canvas.addEventListener("dblclick", onDoubleClick);
    startLoop();
    return () => {
      stopLoop();
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      canvas.removeEventListener("dblclick", onDoubleClick);
      if (
        pointer.down &&
        pointer.id >= 0 &&
        canvas.releasePointerCapture &&
        canvas.hasPointerCapture(pointer.id)
      ) {
        canvas.releasePointerCapture(pointer.id);
      }
    };
  }, [isStaticRenderer, staticRenderKey]);
  return /*#__PURE__*/ _jsx("div", {
    ref: wrapRef,
    style: {
      ...props.style,
      position: "relative",
      width: "100%",
      height: "100%",
      overflow: "hidden",
      background: props.backgroundColor ?? "#000000",
    },
    children: /*#__PURE__*/ _jsx("canvas", {
      ref: canvasRef,
      style: {
        position: "relative",
        display: "block",
        width: "100%",
        height: "100%",
        cursor: "grab",
      },
    }),
  });
}
