/*
 * SpecularButton — vanilla WebGL2 port
 * ===================================
 * A port of the React Bits <SpecularButton /> for this codebase, which is
 * vanilla Flask + HTML with no bundler. The original needs React + the `ogl`
 * npm package; adding a React toolchain to render one button would be a large
 * change for a small gain, so the shader is ported directly and `ogl` is
 * replaced with ~40 lines of raw WebGL2 (it was only used for context setup,
 * a fullscreen triangle, and hex->rgb).
 *
 * The fragment shader is unchanged from the original: a rounded-rect SDF with
 * a specular streak whose angle follows the pointer and whose brightness fades
 * in with proximity.
 *
 * Usage — mark up a button and call Specular.attach():
 *   <button class="specular-button specular-button--lg">
 *     <span class="specular-button__fx"></span>
 *     <span class="specular-button__label">Get started</span>
 *   </button>
 *
 *   Specular.attach(el, { lineColor:'#7fb2ff', baseColor:'#2a3550', radius:18 });
 *
 * Degrades gracefully: if WebGL2 is unavailable the button still renders and
 * clicks — only the moving highlight is missing.
 */
(function (global) {
  'use strict';

  var PAD = 20;

  var VERT =
    '#version 300 es\n' +
    'in vec2 position;\n' +
    'void main(){ gl_Position = vec4(position, 0.0, 1.0); }\n';

  var FRAG =
    '#version 300 es\n' +
    'precision highp float;\n' +
    'uniform vec2 uCenter;\n' +
    'uniform vec2 uHalfSize;\n' +
    'uniform float uRadius;\n' +
    'uniform float uAngle;\n' +
    'uniform float uPx;\n' +
    'uniform vec3 uLineColor;\n' +
    'uniform vec3 uBaseColor;\n' +
    'uniform float uIntensity;\n' +
    'uniform float uShineSize;\n' +
    'uniform float uShineFade;\n' +
    'uniform float uThickness;\n' +
    'uniform float uBaseWidth;\n' +
    'out vec4 fragColor;\n' +
    'float sdRoundedRect(vec2 p, vec2 b, float r){\n' +
    '  vec2 q = abs(p) - b + r;\n' +
    '  return length(max(q,0.0)) + min(max(q.x,q.y),0.0) - r;\n' +
    '}\n' +
    'float gaussianLine(float d, float sigma){\n' +
    '  float x = d / (sigma + 1e-6);\n' +
    '  float k = mix(1.0, 1.6, smoothstep(0.0, 1.5, x));\n' +
    '  return exp(-k * x * x);\n' +
    '}\n' +
    'void main(){\n' +
    '  vec2 p = gl_FragCoord.xy - uCenter;\n' +
    '  float d = sdRoundedRect(p, uHalfSize, uRadius);\n' +
    '  vec2 L = vec2(cos(uAngle), sin(uAngle));\n' +
    '  float base = (1.0 - smoothstep(0.0, uBaseWidth, abs(d))) * 0.45;\n' +
    '  vec2 nEll = normalize(p / (uHalfSize * uHalfSize) + 1e-6);\n' +
    '  float phi = acos(clamp(abs(dot(nEll, L)), 0.0, 1.0));\n' +
    '  float rim = 1.0 - smoothstep(uShineSize - uShineFade, uShineSize + uShineFade + 1e-4, phi);\n' +
    '  float line = gaussianLine(d, uThickness);\n' +
    '  float edgeClamp = 1.0 - smoothstep(0.5 * uPx, 3.0 * uPx, abs(d));\n' +
    '  float hi = line * rim * edgeClamp * uIntensity;\n' +
    '  vec3 col = uBaseColor * base + uLineColor * hi;\n' +
    '  float a = clamp(base + hi, 0.0, 1.0);\n' +
    '  fragColor = vec4(col, a);\n' +
    '}\n';

  function hexToRgb(hex) {
    var h = String(hex).replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }

  function compile(gl, type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn('specular shader:', gl.getShaderInfoLog(s));
      return null;
    }
    return s;
  }

  function attach(btn, opts) {
    opts = opts || {};
    var o = {
      radius: opts.radius != null ? opts.radius : 18,
      lineColor: opts.lineColor || '#ffffff',
      baseColor: opts.baseColor || '#525252',
      intensity: opts.intensity != null ? opts.intensity : 1,
      shineSize: opts.shineSize != null ? opts.shineSize : 10,
      shineFade: opts.shineFade != null ? opts.shineFade : 40,
      thickness: opts.thickness != null ? opts.thickness : 1,
      speed: opts.speed != null ? opts.speed : 0.35,
      followMouse: opts.followMouse !== false,
      proximity: opts.proximity != null ? opts.proximity : 250,
      autoAnimate: !!opts.autoAnimate
    };

    var fx = btn.querySelector('.specular-button__fx');
    if (!fx) return;

    // Respect the OS reduced-motion setting: keep the button, drop the sweep.
    var reduce = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var canvas = document.createElement('canvas');
    var gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: true, antialias: true });
    if (!gl) return; // no WebGL2 → plain button, still fully usable

    var dpr = Math.min(global.devicePixelRatio || 1, 2);
    var vs = compile(gl, gl.VERTEX_SHADER, VERT);
    var fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;
    var prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    // Fullscreen triangle (replaces ogl's Triangle geometry).
    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, 'position');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

    var U = {};
    ['uCenter','uHalfSize','uRadius','uAngle','uPx','uLineColor','uBaseColor',
     'uIntensity','uShineSize','uShineFade','uThickness','uBaseWidth'
    ].forEach(function (n) { U[n] = gl.getUniformLocation(prog, n); });

    fx.appendChild(canvas);

    var W = 1, H = 1;
    function resize() {
      var r = btn.getBoundingClientRect();
      W = r.width; H = r.height;
      var cw = W + PAD * 2, ch = H + PAD * 2;
      canvas.width = Math.round(cw * dpr);
      canvas.height = Math.round(ch * dpr);
      canvas.style.width = cw + 'px';
      canvas.style.height = ch + 'px';
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(U.uCenter, (PAD + W / 2) * dpr, (PAD + H / 2) * dpr);
      gl.uniform2f(U.uHalfSize, (W / 2) * dpr, (H / 2) * dpr);
    }
    var ro = new ResizeObserver(resize);
    ro.observe(btn);
    resize();

    var pointerAngle = null, proximityT = 0;
    function onMove(e) {
      var r = btn.getBoundingClientRect();
      var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      var dx = Math.max(r.left - e.clientX, 0, e.clientX - r.right);
      var dy = Math.max(r.top - e.clientY, 0, e.clientY - r.bottom);
      var dist = Math.hypot(dx, dy);
      if (dist === 0) {
        var nx = (e.clientX - cx) / (r.width / 2);
        var ny = (cy - e.clientY) / (r.height / 2);
        pointerAngle = Math.atan2(2 / r.height, -2 / r.width) + nx * 0.3 + ny * 0.15;
      } else {
        pointerAngle = Math.atan2(cy - e.clientY, e.clientX - cx);
      }
      var t = Math.max(0, 1 - dist / Math.max(o.proximity, 1));
      proximityT = t * t * (3 - 2 * t);
    }
    global.addEventListener('pointermove', onMove, { passive: true });

    var angle = 2.4, idleAngle = 2.4, bright = 0, last = performance.now(), raf = 0;
    var lc = hexToRgb(o.lineColor), bc = hexToRgb(o.baseColor);

    function frame(now) {
      raf = requestAnimationFrame(frame);
      var dt = Math.min((now - last) / 1000, 0.05); last = now;
      idleAngle += o.speed * dt;
      var steer = o.followMouse && pointerAngle != null && (!o.autoAnimate || proximityT > 0);
      var target = steer ? pointerAngle : idleAngle;
      var diff = ((target - angle + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
      angle += diff * (1 - Math.exp(-dt * 7));
      var bt = o.autoAnimate ? 1 : proximityT;
      bright += (bt - bright) * (1 - Math.exp(-dt * 8));

      gl.uniform1f(U.uAngle, angle);
      gl.uniform1f(U.uRadius, Math.min(o.radius, Math.min(W, H) / 2) * dpr);
      gl.uniform1f(U.uPx, dpr);
      gl.uniform1f(U.uBaseWidth, dpr);
      gl.uniform3f(U.uLineColor, lc[0], lc[1], lc[2]);
      gl.uniform3f(U.uBaseColor, bc[0], bc[1], bc[2]);
      gl.uniform1f(U.uIntensity, o.intensity * bright);
      gl.uniform1f(U.uShineSize, (o.shineSize * Math.PI) / 180);
      gl.uniform1f(U.uShineFade, (o.shineFade * Math.PI) / 180);
      gl.uniform1f(U.uThickness, o.thickness * dpr);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    if (reduce) {
      // Static edge stroke only — no animation loop.
      bright = 0; frame(performance.now()); cancelAnimationFrame(raf);
    } else {
      raf = requestAnimationFrame(frame);
    }
  }

  global.Specular = { attach: attach };
})(window);
