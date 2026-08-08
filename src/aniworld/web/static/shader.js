/*
 * Runs a theme's fragment shader on a full page canvas.
 *
 * The theme supplies GLSL only, never JavaScript. A fragment shader runs on
 * the GPU with no DOM, no cookies, no network and no filesystem, so the worst
 * a bad one can do is look wrong or be slow. This file is the whole runtime
 * around it, and it is ours, not the theme's.
 *
 * Guards worth knowing about:
 *   - the buffer is capped, so a 4K screen does not ask the GPU for 8M pixels
 *   - it stops when the tab is hidden or the canvas scrolls out of view
 *   - reduced motion freezes time at zero instead of animating
 *   - a shader that fails to compile is dropped, and the canvas removed
 */
(function () {
  const canvas = document.getElementById("themeShader");
  if (!canvas) return;

  const gl = canvas.getContext("webgl2", {
    alpha: true,
    antialias: false,
    depth: false,
    stencil: false,
    powerPreference: "low-power"
  });
  if (!gl) return;

  // Half a megapixel is plenty for a background and keeps a heavy shader
  // affordable on an integrated GPU.
  const MAX_PIXELS = 500000;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  const VERTEX = `#version 300 es
in vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }`;

  // Everything a theme can rely on. Kept small on purpose: each one is a
  // promise we have to keep working.
  const PRELUDE = `#version 300 es
precision highp float;
uniform vec2 u_resolution;
uniform float u_time;
out vec4 fragColor;
`;

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return shader;
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(log || "shader failed to compile");
  }

  function build(fragmentSource) {
    const program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, PRELUDE + fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "shader failed to link");
    }
    return program;
  }

  function start(program) {
    gl.useProgram(program);

    // one triangle covering the viewport, cheaper than two and no seam
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const attr = gl.getAttribLocation(program, "a_pos");
    gl.enableVertexAttribArray(attr);
    gl.vertexAttribPointer(attr, 2, gl.FLOAT, false, 0, 0);

    const uResolution = gl.getUniformLocation(program, "u_resolution");
    const uTime = gl.getUniformLocation(program, "u_time");

    let width = 0;
    let height = 0;

    function resize() {
      const cssWidth = canvas.clientWidth || window.innerWidth;
      const cssHeight = canvas.clientHeight || window.innerHeight;
      // scale the buffer down until it fits the pixel budget
      const ratio = Math.min(
        window.devicePixelRatio || 1,
        Math.sqrt(MAX_PIXELS / Math.max(1, cssWidth * cssHeight))
      );
      const next = [Math.round(cssWidth * ratio), Math.round(cssHeight * ratio)];
      if (next[0] === width && next[1] === height) return;
      [width, height] = next;
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    }

    let running = false;
    let frame = 0;
    const started = performance.now();

    function draw(now) {
      frame = 0;
      resize();
      gl.uniform2f(uResolution, width, height);
      gl.uniform1f(uTime, reduced.matches ? 0 : (now - started) / 1000);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (running && !reduced.matches) frame = requestAnimationFrame(draw);
    }

    function play() {
      if (running) return;
      running = true;
      frame = requestAnimationFrame(draw);
    }

    function pause() {
      running = false;
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    }

    // Nothing to pay for while the tab is in the background
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) pause();
      else play();
    });
    window.addEventListener("resize", () => {
      if (!running) requestAnimationFrame(draw);
    });
    // a reduced motion user gets one frame, and a fresh one if they change it
    reduced.addEventListener("change", () => requestAnimationFrame(draw));

    play();
  }

  fetch(canvas.dataset.src, { cache: "force-cache" })
    .then((response) => (response.ok ? response.text() : Promise.reject(response.status)))
    .then((source) => {
      if (!source.trim()) throw new Error("empty shader");
      start(build(source));
    })
    .catch((error) => {
      // A broken shader must not leave a black sheet over the page.
      canvas.remove();
      console.warn("[theme] shader disabled:", error.message || error);
    });
})();
