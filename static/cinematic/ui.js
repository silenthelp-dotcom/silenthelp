/* SilentHelp cinematic landing — DOM layer: smoothed scroll, status row,
   demo-device choreography, chips, beam, fade-ins. Pairs with scene.js. */
(function () {
  "use strict";
  var RM = window.matchMedia("(prefers-reduced-motion: reduce)");
  var reduced = RM.matches;
  var S = (window.SHScroll = { y: window.scrollY, target: window.scrollY, reduced: reduced, t: 0 });
  RM.addEventListener && RM.addEventListener("change", function (e) { reduced = S.reduced = e.matches; });

  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function smooth(a, b, v) { var t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); }
  function ease(t) { return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function $(s) { return document.querySelector(s); }
  S.clamp = clamp; S.smooth = smooth; S.ease = ease;

  /* section progress: 0 when pinned, 1 when unpinned; can go <0 / >1 */
  var secs = {};
  function measure() {
    ["top", "demo", "beginning"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      secs[id] = { top: el.offsetTop, h: el.offsetHeight };
    });
    S.vh = window.innerHeight; S.vw = window.innerWidth;
    var c = document.querySelector(".content");
    S.contentTop = c ? c.offsetTop : 1e9;
  }
  S.raw = function (id, y) {
    var s = secs[id]; if (!s) return 0;
    var range = Math.max(1, s.h - S.vh);
    return (y - s.top) / range;
  };
  measure();
  window.addEventListener("resize", measure);
  window.addEventListener("load", measure);

  /* ── live status row (facts from silenthelp.org; the local time ticks) ── */
  var tf = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit", hour12: true });
  var statusEls = Array.prototype.slice.call(document.querySelectorAll("[data-status]"));
  statusEls.forEach(function (el) {
    el.innerHTML =
      '<span class="live" data-k="device"><i></i>On-device · 0 bytes of raw text sent</span>' +
      '<span data-k="scan"><b>Scan</b>&lt;1 ms</span>' +
      '<span data-k="layers"><b>4 layers</b>watching quietly</span>' +
      '<span data-k="988"><b>988</b>call or text</span>' +
      '<span data-k="time"><b>Your time</b><time></time></span>';
  });
  function tick() {
    var t = tf.format(new Date());
    statusEls.forEach(function (el) { var x = el.querySelector("time"); if (x) x.textContent = t; });
  }
  tick(); setInterval(tick, 1000);

  /* ── feature cards: hover / focus / tap plays that card's demo (as on silenthelp.org) ── */
  (function () {
    var wrap = document.getElementById("cards");
    if (!wrap) return;
    var cards = Array.prototype.slice.call(wrap.querySelectorAll(".dcard"));
    var active = null;
    /* replay the build-in from step one, as silenthelp.org does (clone the scene) */
    function restart(card) {
      if (reduced) return;
      var ui = card.querySelector(".dm-ui");
      if (ui) ui.parentNode.replaceChild(ui.cloneNode(true), ui);
    }
    function setActive(i) {
      if (i === active) return;
      active = i;
      wrap.classList.toggle("has-active", i !== null);
      cards.forEach(function (card, idx) {
        var on = i === idx;
        if (on) restart(card);
        card.classList.toggle("is-active", on);
        card.classList.toggle("is-before", i !== null && idx < i);
        card.classList.toggle("is-after", i !== null && idx > i);
        card.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }
    S.setCard = setActive;
    cards.forEach(function (card, idx) {
      card.addEventListener("mouseenter", function () { setActive(idx); });
      card.addEventListener("focus", function () { setActive(idx); });
      card.addEventListener("click", function (e) {
        if (e.target.closest && e.target.closest("a")) return;
        setActive(idx);
      });
      card.addEventListener("keydown", function (e) {
        if (e.target !== card) return;
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setActive(active === idx ? null : idx); }
        else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          var n = (idx + (e.key === "ArrowRight" ? 1 : cards.length - 1)) % cards.length;
          cards[n].focus(); setActive(n);
        } else if (e.key === "Escape") { setActive(null); }
      });
    });
    wrap.addEventListener("mouseleave", function () { if (!wrap.contains(document.activeElement)) setActive(null); });
    wrap.addEventListener("focusout", function (e) { if (!wrap.contains(e.relatedTarget)) setActive(null); });
    document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) setActive(null); });
  })();

  /* ── fade-ins ── */
  var fades = document.querySelectorAll(".fade");
  if ("IntersectionObserver" in window && !reduced) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    fades.forEach(function (f) { io.observe(f); });
  } else fades.forEach(function (f) { f.classList.add("in"); });

  /* hero copy reveal — scene.js calls SHScroll.ready(); fallback timer */
  var readied = false;
  S.ready = function () { if (readied) return; readied = true; document.body.classList.add("ready"); };
  setTimeout(S.ready, reduced ? 50 : 4200);

  /* ── demo device timeline (time-based loop while in view) ── */
  var typedEl = $("#typed"), caret = $("#caret"), checkin = $("#checkin"), ping = $("#ping");
  var lrs = document.querySelectorAll(".lr"), ld = $(".ld");
  var MSG = "i honestly can't do this anymore";
  var LOOP = 12.5, demoClock = 0, demoOn = false;
  function demoFrame(t) {
    if (reduced) t = 9; // static final state
    var startType = 0.8, cps = 15;
    var n = clamp(Math.floor((t - startType) * cps), 0, MSG.length);
    typedEl.textContent = MSG.slice(0, n);
    var done = startType + MSG.length / cps; // ~3s
    for (var i = 0; i < lrs.length; i++) lrs[i].classList.toggle("on", t > done + 0.35 + i * 0.55);
    ld.classList.toggle("on", t > done + 2.6);
    checkin.classList.toggle("on", t > done + 3.0 && t < LOOP - 0.9);
    caret.style.visibility = t > done + 3.0 ? "hidden" : "visible";
  }
  demoFrame(0);

  /* ── chips ── */
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip")).map(function (el, i) {
    return { el: el, d: parseFloat(el.getAttribute("data-d")) || 0.6, i: i };
  });

  var nav = $("#nav"), heroStick = $("#top .stick"), demoCopy = $("#demoCopy"), deviceWrap = $("#deviceWrap"),
      device = $("#device"), beam = $("#beam i"), galCopy = $("#galCopy"), galCta = $("#galCta");
  var pinged = false, last = performance.now();

  function frame(now) {
    var dt = Math.min(0.1, (now - last) / 1000); last = now; S.t += dt;
    S.target = window.scrollY;
    if (reduced) S.y = S.target;
    else S.y += (S.target - S.y) * (1 - Math.exp(-dt * 5.5));
    if (Math.abs(S.target - S.y) < 0.05) S.y = S.target;
    var y = S.y, vh = S.vh;

    /* hero overlay fades as the plinth rises away */
    var h = S.raw("top", y);
    var hf = 1 - smooth(0.42, 0.72, h);
    heroStick.style.opacity = hf.toFixed(3);
    heroStick.style.transform = reduced ? "" : "translate3d(0," + (-smooth(0.42, 0.9, h) * 6).toFixed(2) + "vh,0)";
    heroStick.style.visibility = hf < 0.002 ? "hidden" : "visible";

    /* demo */
    var d = S.raw("demo", y);
    var dvis = d > -0.6 && d < 1.2;
    if (dvis) {
      var cOp = smooth(-0.22, -0.02, d) * (1 - smooth(0.9, 1.04, d));
      demoCopy.style.opacity = cOp.toFixed(3);
      demoCopy.style.transform = reduced ? "" : "translate3d(0," + (-(clamp(d, -0.3, 1)) * 5).toFixed(2) + "vh,0)";

      var rise = reduced ? 1 : ease(smooth(-0.05, 0.42, d));
      var mobile = S.vw < 800;
      var finalTop = (mobile ? 0.6 : 0.6) * vh;
      var topPx = (vh + 40) + (finalTop - (vh + 40)) * rise;
      if (!reduced) topPx -= smooth(0.42, 1.0, d) * 0.07 * vh + Math.sin(S.t * 0.35) * 5;
      deviceWrap.style.transform = "translate3d(-50%," + (topPx - vh).toFixed(1) + "px,0)";
      device.style.transform = reduced ? "rotateX(4deg)" : "rotateX(" + (9 - 5 * rise).toFixed(2) + "deg) rotateZ(" + (Math.sin(S.t * 0.21) * 0.25).toFixed(3) + "deg)";

      // demo timeline runs once the device is up
      var wantOn = d > 0.18 && d < 1.1;
      if (wantOn && !demoOn) { demoOn = true; demoClock = 0; }
      if (!wantOn && demoOn) { demoOn = false; demoFrame(0); }
      if (demoOn) { demoClock = (demoClock + dt) % LOOP; demoFrame(demoClock); }
      if (reduced) demoFrame(9);

      // chips
      for (var i = 0; i < chips.length; i++) {
        var c = chips[i];
        var start = 0.22 + i * 0.055;
        var op = reduced ? smooth(0.1, 0.2, d) : smooth(start, start + 0.12, d) * (1 - smooth(0.92, 1.05, d));
        op *= 0.55 + 0.45 * c.d;
        var dy = reduced ? 0 : (1 - clamp(d, 0, 1)) * 140 * c.d + Math.sin(S.t * (0.18 + c.d * 0.12) + i * 1.7) * 7 * c.d;
        var dx = reduced ? 0 : Math.cos(S.t * 0.13 + i) * 5 * c.d;
        var sc = 0.86 + 0.22 * c.d;
        c.el.style.opacity = op.toFixed(3);
        c.el.style.transform = "translate3d(calc(-50% + var(--x) + " + dx.toFixed(1) + "px),calc(var(--y) + " + dy.toFixed(1) + "px),0) scale(" + sc.toFixed(3) + ")";
      }

      // light beam descending onto the screen
      var bp = reduced ? 0 : smooth(0.56, 0.8, d);
      var bOut = 1 - smooth(0.86, 0.96, d);
      var copyR = demoCopy.getBoundingClientRect();
      var beamTop = Math.min(copyR.bottom + 28, topPx - 20);
      var beamLen = Math.max(0, topPx + 18 - beamTop) * bp;
      beam.style.top = beamTop.toFixed(1) + "px";
      beam.style.height = beamLen.toFixed(1) + "px";
      beam.style.opacity = (bp > 0 ? bOut : 0).toFixed(3);
      beam.style.setProperty("--tip", (bp > 0.02 ? 1 : 0).toString());
      if (bp >= 0.999 && !pinged) { pinged = true; ping.classList.remove("go"); void ping.offsetWidth; ping.classList.add("go"); }
      if (bp < 0.6) pinged = false;
    }

    /* gallery copy */
    var g = S.raw("beginning", y);
    var gOp = smooth(0.1, 0.28, g) * (1 - smooth(0.86, 0.99, g));
    galCopy.style.opacity = gOp.toFixed(3);
    galCopy.style.transform = "translate3d(0," + (reduced ? 0 : (1 - smooth(0.1, 0.3, g)) * 22).toFixed(1) + "px,0)";
    galCta.style.opacity = (smooth(0.18, 0.34, g) * (1 - smooth(0.86, 0.99, g))).toFixed(3);

    nav.classList.toggle("solid", y > S.contentTop - 90);
    S.h = h; S.d = d; S.g = g;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
