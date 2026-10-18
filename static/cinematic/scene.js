/* SilentHelp cinematic landing — WebGL layer (Three.js r170, vendored).
   Act 1: gallery ceiling light → tilt down → black marble room, glowing
          plinth, brushed-metal SilentHelp medallion.
   Act 3: floating desaturated photo grid + the medallion spinning ~180°. */
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RectAreaLightUniformsLib } from "three/addons/lights/RectAreaLightUniformsLib.js";

const S = window.SHScroll;
const canvas = document.getElementById("gl");
const veil = document.getElementById("veil");
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const lerp = (a, b, t) => a + (b - a) * t;

const small = Math.min(window.innerWidth, window.innerHeight) < 700 || window.innerWidth < 800;
const lowPower = small || (navigator.hardwareConcurrency || 8) <= 4;

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: !small, alpha: false, powerPreference: "high-performance" });
} catch (e) {
  console.warn("[cinematic] WebGL unavailable", e);
  veil.classList.add("off"); S.ready();
  throw e;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.5 : 1.75));
renderer.setSize(window.innerWidth, window.innerHeight, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1;
renderer.setClearColor(0x000000, 1);
RectAreaLightUniformsLib.init();

const pmrem = new THREE.PMREMGenerator(renderer);
const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

/* ───────────────────────── procedural textures ───────────────────────── */
function makeNoise(seed) {
  const p = new Uint8Array(512);
  let s = seed >>> 0;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  const perm = Array.from({ length: 256 }, (_, i) => i);
  for (let i = 255; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [perm[i], perm[j]] = [perm[j], perm[i]]; }
  for (let i = 0; i < 512; i++) p[i] = perm[i & 255];
  const val = new Float32Array(256).map(() => rnd());
  return function (x, y) {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const X = xi & 255, Y = yi & 255;
    const a = val[p[p[X] + Y]], b = val[p[p[X + 1] + Y]], c = val[p[p[X] + Y + 1]], d = val[p[p[X + 1] + Y + 1]];
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  };
}

function marbleCanvas(size, seed) {
  const n = makeNoise(seed), n2 = makeNoise(seed * 7 + 3);
  const cv = document.createElement("canvas"); cv.width = cv.height = size;
  const ctx = cv.getContext("2d"); const img = ctx.createImageData(size, size); const D = img.data;
  const fbm = (x, y, f) => { let a = 0, amp = 0.5; for (let o = 0; o < f; o++) { a += amp * f2(x, y); x *= 2.03; y *= 2.03; amp *= 0.5; } return a; };
  let f2 = n;
  for (let j = 0; j < size; j++) {
    for (let i = 0; i < size; i++) {
      const x = (i / size) * 4, y = (j / size) * 4;
      f2 = n; const t = fbm(x, y, 5);
      f2 = n2; const t2 = fbm(x * 1.7 + 9, y * 1.7 + 4, 4);
      const v1 = Math.abs(Math.sin((x * 1.1 + y * 0.6) * 2.2 + t * 7.5));
      const v2 = Math.abs(Math.sin((x * -0.5 + y * 1.3) * 3.1 + t2 * 9.0));
      const amp = 0.25 + 0.75 * smooth(0.35, 0.75, t2);      // veins fade in and out
      let vein = (Math.pow(1 - v1, 60) * 0.85 + Math.pow(1 - v1, 9) * 0.07) * amp;
      vein += (Math.pow(1 - v2, 90) * 0.45 + Math.pow(1 - v2, 14) * 0.03) * (1 - amp * 0.6);
      const cloud = 0.025 + t * 0.04 + t2 * 0.015;
      const L = Math.min(1, cloud + vein * 0.95);
      const k = (j * size + i) * 4, c = Math.round(L * 255);
      D[k] = c; D[k + 1] = c; D[k + 2] = Math.min(255, c + 2); D[k + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return cv;
}

function brushedCanvas(size, concentric) {
  const cv = document.createElement("canvas"); cv.width = cv.height = size;
  const ctx = cv.getContext("2d");
  ctx.fillStyle = "rgb(120,120,120)"; ctx.fillRect(0, 0, size, size);
  const lines = concentric ? 900 : 1400;
  for (let k = 0; k < lines; k++) {
    const g = 90 + Math.random() * 80;
    ctx.strokeStyle = `rgba(${g},${g},${g},${0.25 + Math.random() * 0.35})`;
    ctx.lineWidth = 0.5 + Math.random() * 1.2;
    ctx.beginPath();
    if (concentric) {
      const r = Math.random() * size * 0.5;
      const a0 = Math.random() * Math.PI * 2;
      ctx.arc(size / 2, size / 2, r, a0, a0 + 0.5 + Math.random() * 5.5);
    } else {
      const y = Math.random() * size; const x0 = Math.random() * size;
      ctx.moveTo(x0 - size, y); ctx.lineTo(x0 + size * Math.random(), y);
    }
    ctx.stroke();
  }
  return cv;
}

function glowTexture() {
  const cv = document.createElement("canvas"); cv.width = cv.height = 256;
  const ctx = cv.getContext("2d");
  const g = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.25, "rgba(255,255,255,.35)");
  g.addColorStop(0.6, "rgba(255,255,255,.06)"); g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; return t;
}
const GLOW = glowTexture();

function loadImage(src) {
  return new Promise((res, rej) => { const im = new Image(); im.decoding = "async"; im.onload = () => res(im); im.onerror = rej; im.src = src; });
}

/* Logo face: real SilentHelp badge → luminance → brushed silver + engraving */
async function logoFaceMaps() {
  const im = await loadImage("/static/cinematic/img/logo-face.png");
  const N = small ? 512 : 1024;
  const cv = document.createElement("canvas"); cv.width = cv.height = N;
  const ctx = cv.getContext("2d");
  ctx.drawImage(im, 0, 0, N, N);
  const src = ctx.getImageData(0, 0, N, N);
  const brushed = brushedCanvas(N, true).getContext("2d").getImageData(0, 0, N, N).data;
  const col = ctx.createImageData(N, N), bump = ctx.createImageData(N, N), rough = ctx.createImageData(N, N);
  for (let k = 0; k < src.data.length; k += 4) {
    const r = src.data[k], g = src.data[k + 1], b = src.data[k + 2];
    let L = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    // coloured strokes (the brain's red/blue lines) read as raised polished silver
    const chroma = (Math.max(r, g, b) - Math.min(r, g, b)) / 255;
    L = Math.max(L, chroma * 0.95);
    const br = brushed[k] / 255;
    const metal = lerp(0.16, 0.92, Math.pow(L, 0.9)) * (0.9 + br * 0.2);
    const c = clamp(Math.round(metal * 255), 0, 255);
    col.data[k] = c; col.data[k + 1] = c; col.data[k + 2] = Math.min(255, c + 3); col.data[k + 3] = 255;
    const bv = Math.round(L * 255); bump.data[k] = bump.data[k + 1] = bump.data[k + 2] = bv; bump.data[k + 3] = 255;
    const rv = Math.round(clamp(0.22 + (1 - L) * 0.3 + (br - 0.5) * 0.18, 0.08, 0.7) * 255);
    rough.data[k] = rough.data[k + 1] = rough.data[k + 2] = rv; rough.data[k + 3] = 255;
  }
  const mk = (data, srgb) => {
    const c2 = document.createElement("canvas"); c2.width = c2.height = N;
    c2.getContext("2d").putImageData(data, 0, 0);
    const t = new THREE.CanvasTexture(c2); if (srgb) t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = renderer.capabilities.getMaxAnisotropy(); return t;
  };
  return { map: mk(col, true), bumpMap: mk(bump, false), roughnessMap: mk(rough, false) };
}

function makeMedallion(maps) {
  const R = 0.42, T = 0.075, seg = small ? 72 : 128;
  const grp = new THREE.Group();
  const brushedSide = new THREE.CanvasTexture(brushedCanvas(512, false));
  brushedSide.wrapS = brushedSide.wrapT = THREE.RepeatWrapping; brushedSide.repeat.set(3, 1);
  const sideMat = new THREE.MeshPhysicalMaterial({ color: 0xc9ced1, metalness: 1, roughness: 0.38, roughnessMap: brushedSide, envMapIntensity: 1.0 });
  const faceMat = new THREE.MeshPhysicalMaterial({
    color: 0xffffff, metalness: 1, roughness: 1, map: maps.map, roughnessMap: maps.roughnessMap,
    bumpMap: maps.bumpMap, bumpScale: 1.6, envMapIntensity: 1.05, clearcoat: 0.15, clearcoatRoughness: 0.4,
  });
  const side = new THREE.Mesh(new THREE.CylinderGeometry(R, R, T, seg, 1, true), sideMat);
  side.rotation.x = Math.PI / 2; grp.add(side);
  const faceG = new THREE.CircleGeometry(R, seg);
  const front = new THREE.Mesh(faceG, faceMat); front.position.z = T / 2; grp.add(front);
  const back = new THREE.Mesh(faceG, faceMat); back.position.z = -T / 2; back.rotation.y = Math.PI; grp.add(back);
  const rimG = new THREE.TorusGeometry(R - 0.006, 0.011, 10, seg);
  const rimF = new THREE.Mesh(rimG, sideMat); rimF.position.z = T / 2; grp.add(rimF);
  const rimB = new THREE.Mesh(rimG, sideMat); rimB.position.z = -T / 2; grp.add(rimB);
  grp.userData = { R, T, sideMat, faceMat };
  return grp;
}

/* ───────────────────────── ACT 1 · hero room ───────────────────────── */
const hero = new THREE.Scene();
hero.background = new THREE.Color(0x000000);
hero.fog = new THREE.FogExp2(0x000000, 0.055);
hero.environment = envTex;
hero.environmentIntensity = 0.35;
const room = new THREE.Group(); hero.add(room);

const W = 11, H = 7.2, Dp = 17, ZB = -6.5;
const marbleSize = small ? 512 : 1024;
const marbleTex = new THREE.CanvasTexture(marbleCanvas(marbleSize, 11));
marbleTex.colorSpace = THREE.SRGBColorSpace;
marbleTex.wrapS = marbleTex.wrapT = THREE.MirroredRepeatWrapping;
marbleTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
const wallMat = new THREE.MeshStandardMaterial({ map: marbleTex, color: 0xd4d4d4, roughness: 0.22, metalness: 0.0, envMapIntensity: 0.55 });
const floorTex = marbleTex.clone(); floorTex.repeat.set(1, 1.3); floorTex.needsUpdate = true;
const floorMat = new THREE.MeshStandardMaterial({ map: floorTex, color: 0x9a9a9a, roughness: 0.3, metalness: 0.0, envMapIntensity: 0.8 });

function plane(w, h, mat) { return new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat); }
const back = plane(W, H, wallMat); back.position.set(0, H / 2, ZB); room.add(back);
const left = plane(Dp, H, wallMat); left.rotation.y = Math.PI / 2; left.position.set(-W / 2, H / 2, ZB + Dp / 2); room.add(left);
const right = plane(Dp, H, wallMat); right.rotation.y = -Math.PI / 2; right.position.set(W / 2, H / 2, ZB + Dp / 2); room.add(right);
const floor = plane(W, Dp, floorMat); floor.rotation.x = -Math.PI / 2; floor.position.set(0, 0, ZB + Dp / 2); room.add(floor);
const ceilMat = new THREE.MeshStandardMaterial({ color: 0x0a0a0b, roughness: 0.9 });
const ceil = plane(W, Dp, ceilMat); ceil.rotation.x = Math.PI / 2; ceil.position.set(0, H, ZB + Dp / 2); room.add(ceil);

// overhead light panel (gallery ceiling)
const panelW = 3.4, panelD = 2.0;
const panel = plane(panelW, panelD, new THREE.MeshBasicMaterial({ color: new THREE.Color(1, 1, 1).multiplyScalar(9) }));
panel.rotation.x = Math.PI / 2; panel.position.set(0, H - 0.01, 0); room.add(panel);
const frame = plane(panelW + 0.16, panelD + 0.16, new THREE.MeshBasicMaterial({ color: 0x151719 }));
frame.rotation.x = Math.PI / 2; frame.position.set(0, H - 0.005, 0); room.add(frame);
const panelGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, color: 0xffffff, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false, fog: false }));
panelGlow.scale.set(9, 6, 1); panelGlow.position.set(0, H - 0.25, 0); room.add(panelGlow);

const rect = new THREE.RectAreaLight(0xffffff, 6.5, panelW, panelD);
rect.position.set(0, H - 0.02, 0); rect.lookAt(0, 0, 0); room.add(rect);

// plinth / light box
const PW = 0.68, PH = 0.96;
const plinthGrad = (() => {
  const cv = document.createElement("canvas"); cv.width = 8; cv.height = 256;
  const ctx = cv.getContext("2d"); const g = ctx.createLinearGradient(0, 0, 0, 256);
  g.addColorStop(0, "#ffffff"); g.addColorStop(0.55, "#d9d9d9"); g.addColorStop(1, "#8c8c8c");
  ctx.fillStyle = g; ctx.fillRect(0, 0, 8, 256);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; return t;
})();
const plinthMat = new THREE.MeshStandardMaterial({ color: 0xeeeeee, emissive: 0xffffff, emissiveMap: plinthGrad, emissiveIntensity: 0.75, roughness: 0.55 });
const plinth = new THREE.Mesh(new THREE.BoxGeometry(PW, PH, PW), plinthMat);
plinth.position.set(0, PH / 2, 0); room.add(plinth);
const plinthTop = plane(PW, PW, new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.9, roughness: 0.5 }));
plinthTop.rotation.x = -Math.PI / 2; plinthTop.position.set(0, PH + 0.001, 0); room.add(plinthTop);
const plinthGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, color: 0xffffff, transparent: true, opacity: 0.32, blending: THREE.AdditiveBlending, depthWrite: false }));
plinthGlow.scale.set(3.4, 3.0, 1); plinthGlow.position.set(0, PH * 0.55, 0.1); room.add(plinthGlow);
const pool = plane(3.6, 3.6, new THREE.MeshBasicMaterial({ map: GLOW, color: 0xffffff, transparent: true, opacity: 0.38, blending: THREE.AdditiveBlending, depthWrite: false }));
pool.rotation.x = -Math.PI / 2; pool.position.set(0, 0.004, 0.05); room.add(pool);
const plinthLight = new THREE.PointLight(0xffffff, 1.6, 3, 2); plinthLight.position.set(0, 0.35, 0.7); room.add(plinthLight);

// raking spot across the medallion
const rake = new THREE.SpotLight(0xffffff, 55, 12, 0.32, 0.9, 2);
rake.position.set(-3.4, 3.6, 2.6); room.add(rake); room.add(rake.target);
const rim = new THREE.SpotLight(0xffffff, 26, 10, 0.4, 1, 2);
rim.position.set(2.6, 2.4, -2.2); room.add(rim); room.add(rim.target);
hero.add(new THREE.AmbientLight(0xffffff, 0.04));

// stand + medallion holder (filled once textures load)
const stand = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.045, 0.16), new THREE.MeshPhysicalMaterial({ color: 0x9aa0a4, metalness: 1, roughness: 0.35 }));
stand.position.set(0, PH + 0.0225, 0); room.add(stand);
const heroHolder = new THREE.Group(); room.add(heroHolder);

const heroCam = new THREE.PerspectiveCamera(32, window.innerWidth / window.innerHeight, 0.05, 60);

/* ───────────────────────── ACT 3 · photo gallery ───────────────────────── */
const gal = new THREE.Scene();
gal.background = new THREE.Color(0x000000);
gal.fog = new THREE.Fog(0x000000, 5, 21);
gal.environment = envTex;
gal.environmentIntensity = 0.5;
const galCam = new THREE.PerspectiveCamera(36, window.innerWidth / window.innerHeight, 0.05, 60);
const photos = new THREE.Group(); gal.add(photos);
const galHolder = new THREE.Group(); gal.add(galHolder);
const gKey = new THREE.SpotLight(0xffffff, 40, 12, 0.35, 0.9, 2); gKey.position.set(-2.4, 3.2, 3.2); gal.add(gKey); gal.add(gKey.target);
const gRim = new THREE.SpotLight(0xffffff, 22, 12, 0.5, 1, 2); gRim.position.set(2.8, -1.5, 2.0); gal.add(gRim); gal.add(gRim.target);
const gTop = new THREE.DirectionalLight(0xffffff, 0.35); gTop.position.set(0, 4, 2); gal.add(gTop);
gal.add(new THREE.AmbientLight(0xffffff, 0.05));
const galGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, color: 0xffffff, transparent: true, opacity: 0.06, blending: THREE.AdditiveBlending, depthWrite: false }));
galGlow.scale.set(5, 5, 1); galGlow.position.set(0, 0, -0.6); gal.add(galGlow);

const PHOTO_FILES = Array.from({ length: 28 }, (_, i) => "s" + String(i + 1).padStart(2, "0"));
async function buildGallery() {
  const loader = new THREE.TextureLoader();
  const files = small ? PHOTO_FILES.filter((_, i) => i % 2 === 0) : PHOTO_FILES;
  const texs = await Promise.all(files.map((f) => new Promise((res) => {
    loader.load(`/static/cinematic/gal/${f}.webp`, (t) => { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; res(t); }, undefined, () => res(null));
  })));
  const good = texs.filter(Boolean);
  if (!good.length) return;
  // seeded layout so it is stable between loads
  let s = 7; const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const cols = small ? 5 : 11, rows = small ? 7 : 6, count = small ? 30 : 72;
  const geo = new THREE.PlaneGeometry(1, 1);
  let placed = 0, tries = 0;
  while (placed < count && tries < 600) {
    tries++;
    const cx = Math.floor(rnd() * cols), cy = Math.floor(rnd() * rows);
    const z = 2.2 - rnd() * 18;
    const spread = 1 + Math.max(0, -z) * 0.07;                      // wider further back
    const x = ((cx - (cols - 1) / 2) * (small ? 1.2 : 1.55) + (rnd() - 0.5) * 0.5) * spread;
    const y = ((cy - (rows - 1) / 2) * (small ? 1.35 : 1.2) + (rnd() - 0.5) * 0.4) * spread;
    if (Math.abs(x) < 1.5 && Math.abs(y) < 1.25 && z > -10) continue; // keep the logo clear
    if (z > 0 && Math.abs(x) < 2.6) continue;                         // near planes only at the edges
    const tex = good[placed % good.length];
    const ar = tex.image.width / tex.image.height;
    const w = 0.7 + rnd() * 0.6; const h = w / ar;
    const shade = 0.64 + rnd() * 0.2;   // softly graded, subject stays readable
    const m = new THREE.MeshBasicMaterial({ map: tex, color: new THREE.Color(shade, shade, shade), transparent: true, opacity: 1, depthWrite: true });
    const mesh = new THREE.Mesh(geo, m);
    mesh.scale.set(w, h, 1); mesh.position.set(x, y, z);
    mesh.userData = { base: mesh.position.clone(), ph: rnd() * 6.28, sp: 0.2 + rnd() * 0.3 };
    photos.add(mesh); placed++;
  }
}

/* ───────────────────────── build + loop ───────────────────────── */
let heroMedal = null, galMedal = null, assetsReady = false;
(async () => {
  try {
    const maps = await logoFaceMaps();
    heroMedal = makeMedallion(maps);
    heroMedal.position.set(0, PH + 0.045 + heroMedal.userData.R, 0);
    heroMedal.rotation.y = -0.38;
    heroHolder.add(heroMedal);
    rake.target.position.copy(heroMedal.position); rim.target.position.copy(heroMedal.position);
    galMedal = makeMedallion(maps);
    galMedal.scale.setScalar(small ? 0.95 : 1.22);
    galHolder.add(galMedal);
    gKey.target.position.set(0, 0, 0); gRim.target.position.set(0, 0, 0);
  } catch (e) { console.warn("[cinematic] logo texture failed", e); }
  await buildGallery().catch((e) => console.warn("[cinematic] gallery", e));
  renderer.compile(hero, heroCam); renderer.compile(gal, galCam);
  assetsReady = true;
  introStart = performance.now();
  veil.classList.add("off");
})();

let introStart = 0;
const INTRO_MS = 5200;
const lookA = new THREE.Vector3(0, H - 0.05, -0.2);  // ceiling panel
const lookB = new THREE.Vector3(0, 1.25, 0);         // plinth
const tmpV = new THREE.Vector3();
let pointerX = 0, pointerY = 0, px = 0, py = 0;
window.addEventListener("pointermove", (e) => { pointerX = e.clientX / window.innerWidth - 0.5; pointerY = e.clientY / window.innerHeight - 0.5; }, { passive: true });

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  heroCam.aspect = galCam.aspect = w / h;
  heroCam.updateProjectionMatrix(); galCam.updateProjectionMatrix();
}
window.addEventListener("resize", resize);

let clock = 0, lastT = performance.now(), wasBlank = false;
function loop(now) {
  requestAnimationFrame(loop);
  const dt = Math.min(0.1, (now - lastT) / 1000); lastT = now; clock += dt;
  if (!assetsReady) return;
  const reduced = S.reduced;
  const y = S.y;
  const h = S.raw("top", y), g = S.raw("beginning", y);
  const aspect = window.innerWidth / window.innerHeight;
  const distMul = aspect < 1 ? 1.15 + (1 - aspect) * 0.9 : 1;
  px += (pointerX - px) * (1 - Math.exp(-dt * 1.2)); py += (pointerY - py) * (1 - Math.exp(-dt * 1.2));

  // past the gallery the content layer covers the canvas — skip work
  if (y > S.contentTop + 40) { if (!wasBlank) { renderer.clear(); wasBlank = true; } return; }

  if (h < 1.02) {
    wasBlank = false;
    // intro tilt-down from the ceiling light
    let it = reduced ? 1 : clamp((now - introStart) / INTRO_MS, 0, 1);
    const tilt = ease(it);
    if (it > 0.55 || reduced) S.ready();
    const push = reduced ? 0 : ease(smooth(0, 0.55, h));
    // portrait screens: widen the lens instead of backing out of the room
    const fovH = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(16)) * distMul));
    if (Math.abs(heroCam.fov - fovH) > 0.01) { heroCam.fov = fovH; heroCam.updateProjectionMatrix(); }
    const camZ = lerp(8.6, 7.9, push);
    const camY = lerp(lerp(1.0, 1.42, tilt), 1.36, push);
    heroCam.position.set(reduced ? 0 : px * 0.18, camY + (reduced ? 0 : -py * 0.06), camZ);
    tmpV.lerpVectors(lookA, lookB, tilt);
    // scene rises away (screen-space lift + slight camera drop) and goes fully black
    const rise = reduced ? 0 : ease(smooth(0.42, 1.0, h));
    tmpV.y += push * 0.03 - rise * 0.35;
    heroCam.position.y -= rise * 0.2;
    heroCam.lookAt(tmpV);
    canvas.style.transform = rise > 0 ? `translate3d(0,${(-rise * 62).toFixed(2)}vh,0)` : "";
    const fadeOut = 1 - smooth(0.48, 0.92, h);
    renderer.toneMappingExposure = fadeOut * (reduced ? 1 : lerp(0.3, 1.0, smooth(0, 0.7, it)));
    if (heroMedal && !reduced) {
      heroMedal.rotation.y = -0.38 + Math.sin(clock * 0.12) * 0.06 + push * 0.12;
      rake.position.x = -3.4 + Math.sin(clock * 0.09) * 1.1;
    }
    renderer.render(hero, heroCam);
    return;
  }

  if (canvas.style.transform) canvas.style.transform = "";
  if (g > -0.6 && g < 1.15) {
    wasBlank = false;
    const enter = smooth(-0.45, -0.05, g);
    const leave = 1 - smooth(0.92, 1.12, g);
    renderer.toneMappingExposure = enter * leave * 1.05;
    const gp = clamp(g, -0.6, 1.1);
    const travel = reduced ? 0.3 : ease(clamp((gp + 0.6) / 1.7, 0, 1));
    galCam.position.set(reduced ? 0 : px * 0.35, reduced ? 0 : -py * 0.2, lerp(8.6, 4.3, travel) * distMul);
    galCam.lookAt(0, 0, -1);
    if (galMedal) {
      const spin = reduced ? 0 : smooth(-0.2, 1.0, g);
      galMedal.rotation.y = reduced ? -0.35 : -Math.PI / 2 + spin * Math.PI + Math.sin(clock * 0.2) * 0.03;
    }
    if (!reduced) {
      for (const m of photos.children) {
        const u = m.userData;
        m.position.y = u.base.y + Math.sin(clock * u.sp + u.ph) * 0.06;
        m.position.x = u.base.x + Math.cos(clock * u.sp * 0.7 + u.ph) * 0.04;
      }
    }
    renderer.render(gal, galCam);
    return;
  }
  if (!wasBlank) { renderer.clear(); wasBlank = true; }
}
requestAnimationFrame(loop);
