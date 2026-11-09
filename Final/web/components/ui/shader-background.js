"use client";

// ShaderBackground: a slow "silk" WebGL background (from the 21st.dev Shader
// Builder, ported to JavaScript). One canvas that fills its parent; put it
// behind content: <section className="relative isolate"><ShaderBackground
// className="absolute inset-0 -z-10" />…</section>
//
// Colours come from the `colors` prop (2–8 hex values, dark → highlight → dark
// reads best); the default is the original green preset. The loop pauses
// off-screen and in hidden tabs, draws one still frame with reduced motion, and
// if WebGL is missing the canvas stays transparent so the parent's background
// shows instead.

import { useEffect, useRef } from "react";

const VERT = `attribute vec2 a_position;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
}`;

const FRAG = `#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform vec3 u_colors[8];
uniform vec4 u_scene;      // resolution.xy, time, colour count
uniform vec4 u_shape;      // scale, intensity, paramA, warp
uniform vec4 u_surface;    // detail, contrast, brightness, saturation
uniform vec4 u_finish;     // hue, vignette, blur, grain
uniform vec4 u_transform;  // seed, rotation, drift, OKLab toggle
uniform vec4 u_space;      // offset.xy, pointer.xy
uniform vec4 u_cursor;

#define u_resolution u_scene.xy
#define u_time u_scene.z
#define u_colorCount u_scene.w
#define u_scale u_shape.x
#define u_intensity u_shape.y
#define u_paramA u_shape.z
#define u_warp u_shape.w
#define u_detail u_surface.x
#define u_contrast u_surface.y
#define u_brightness u_surface.z
#define u_saturation u_surface.w
#define u_hue u_finish.x
#define u_vignette u_finish.y
#define u_blur u_finish.z
#define u_grain u_finish.w
#ifdef GL_FRAGMENT_PRECISION_HIGH
#define u_seed u_transform.x
#else
#define u_seed mod(u_transform.x, 31.0)
#endif
#define u_rotate u_transform.y
#define u_drift u_transform.z
#define u_oklab u_transform.w
#define u_offset u_space.xy
#define u_mouse u_space.zw
#define u_cursorPresence u_cursor.x
#define u_cursorEffect u_cursor.y
#define u_cursorStrength u_cursor.z
#define u_cursorRadius u_cursor.w

float hash21(vec2 p) {
#ifndef GL_FRAGMENT_PRECISION_HIGH
  p = mod(p, 31.0);
#endif
  p = fract(p * vec2(234.34, 435.345));
  p += dot(p, p + 34.23);
  return fract(p.x * p.y);
}

float grainHash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash21(i), hash21(i + vec2(1.0, 0.0)), u.x),
    mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), u.x),
    u.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p = p * 2.03 + vec2(17.0, 9.2);
    a *= 0.5;
  }
  return v;
}

vec3 srgbToLinear(vec3 c) {
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}
vec3 linearToSrgb(vec3 c) {
  return mix(c * 12.92, 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}
vec3 linToOklab(vec3 c) {
  float l = 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b;
  float m = 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b;
  float s = 0.0883024619 * c.r + 0.2817188376 * c.g + 0.6299787005 * c.b;
  l = pow(max(l, 0.0), 1.0 / 3.0);
  m = pow(max(m, 0.0), 1.0 / 3.0);
  s = pow(max(s, 0.0), 1.0 / 3.0);
  return vec3(
    0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s);
}
vec3 oklabToLin(vec3 c) {
  float l = c.x + 0.3963377774 * c.y + 0.2158037573 * c.z;
  float m = c.x - 0.1055613458 * c.y - 0.0638541728 * c.z;
  float s = c.x - 0.0894841775 * c.y - 1.2914855480 * c.z;
  l = l * l * l; m = m * m * m; s = s * s * s;
  return vec3(
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s);
}
vec3 mixColour(vec3 a, vec3 b, float t) {
  if (u_oklab > 0.5) {
    vec3 la = linToOklab(srgbToLinear(a));
    vec3 lb = linToOklab(srgbToLinear(b));
    return clamp(linearToSrgb(oklabToLin(mix(la, lb, t))), 0.0, 1.0);
  }
  return mix(a, b, t);
}

vec3 palette(float x) {
  float n = max(u_colorCount - 1.0, 1.0);
  float f = clamp(x, 0.0, 1.0) * n;
  vec3 col = u_colors[0];
  for (int i = 0; i < 7; i++) {
    if (float(i) < n)
      col = mixColour(col, u_colors[i + 1], smoothstep(0.0, 1.0, clamp(f - float(i), 0.0, 1.0)));
  }
  return col;
}

vec3 hueRotate(vec3 col, float a) {
  const mat3 toYIQ = mat3(0.299, 0.596, 0.211, 0.587, -0.274, -0.523, 0.114, -0.322, 0.312);
  const mat3 toRGB = mat3(1.0, 1.0, 1.0, 0.956, -0.272, -1.106, 0.621, -0.647, 1.703);
  vec3 yiq = toYIQ * col;
  float ca = cos(a), sa = sin(a);
  yiq = vec3(yiq.x, yiq.y * ca - yiq.z * sa, yiq.y * sa + yiq.z * ca);
  return toRGB * yiq;
}

vec3 shade(vec2 uv, vec2 p, float t) {
  vec2 q = p * 1.6;
  float amp = 0.25 + u_intensity * 0.85;
  for (float i = 1.0; i < 5.0; i += 1.0) {
    q.x += amp / i * cos(i * 2.4 * q.y + t * 0.8 + u_seed);
    q.y += amp / i * cos(i * 1.7 * q.x + t * 0.6);
  }
  return palette(0.5 + 0.5 * sin(q.x + q.y));
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution.xy;
  vec2 screenUv = uv;
  vec2 p = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / min(u_resolution.x, u_resolution.y);
  float cursorMask = 0.0;

  if (u_cursorPresence > 0.001) {
    vec2 cursor = (0.5 * u_mouse * u_resolution.xy) / min(u_resolution.x, u_resolution.y);
    vec2 cursorDelta = p - cursor;
    if (u_cursorEffect < 0.5) {
      p += cursor * u_cursorPresence * u_cursorStrength * 0.55;
    } else {
      float cursorDistance = length(cursorDelta);
      vec2 cursorDirection = cursorDelta / max(cursorDistance, 0.0001);
      cursorMask = u_cursorPresence * (1.0 - smoothstep(0.0, u_cursorRadius, cursorDistance));
      if (u_cursorEffect < 1.5) {
        p -= cursorDirection * cursorMask * u_cursorStrength * 0.24;
      } else if (u_cursorEffect < 2.5) {
        float cursorAngle = cursorMask * u_cursorStrength * 2.2;
        float cc = cos(cursorAngle), cs = sin(cursorAngle);
        p = cursor + mat2(cc, -cs, cs, cc) * cursorDelta;
      } else if (u_cursorEffect < 3.5) {
        float ripple = sin(cursorDistance / max(u_cursorRadius, 0.001) * 18.0 - u_time * 5.0);
        p -= cursorDirection * ripple * cursorMask * u_cursorStrength * 0.07;
      }
    }
  }

  uv = p * min(u_resolution.x, u_resolution.y) / u_resolution.xy + 0.5;
  p *= u_scale;
  if (abs(u_rotate) > 0.0001) {
    float cr = cos(u_rotate), sr = sin(u_rotate);
    p = mat2(cr, -sr, sr, cr) * p;
  }
  p += u_offset;
  if (u_drift > 0.0001)
    p += u_drift * vec2(sin(u_time * 0.31), cos(u_time * 0.23));
  if (u_warp > 0.0) {
    p += u_warp * (vec2(fbm(p * u_detail + u_seed), fbm(p * u_detail + vec2(5.2, 1.3))) - 0.5);
  }
  vec3 col;
  if (u_blur > 0.0) {
    float e = u_blur;
    float pe = e * u_scale;
    vec2 uvE = vec2(e) * min(u_resolution.x, u_resolution.y) / u_resolution.xy;
    col  = shade(uv, p, u_time) * 0.36;
    col += shade(uv + vec2(uvE.x, 0.0), p + vec2(pe, 0.0), u_time) * 0.16;
    col += shade(uv - vec2(uvE.x, 0.0), p - vec2(pe, 0.0), u_time) * 0.16;
    col += shade(uv + vec2(0.0, uvE.y), p + vec2(0.0, pe), u_time) * 0.16;
    col += shade(uv - vec2(0.0, uvE.y), p - vec2(0.0, pe), u_time) * 0.16;
  } else {
    col = shade(uv, p, u_time);
  }
  if (abs(u_contrast - 1.0) > 0.0001)
    col = (col - 0.5) * u_contrast + 0.5;
  if (abs(u_saturation - 1.0) > 0.0001) {
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(luma), col, u_saturation);
  }
  if (abs(u_hue) > 0.0001)
    col = hueRotate(col, u_hue);
  if (abs(u_brightness) > 0.0001)
    col += u_brightness;
  if (u_vignette > 0.0001) {
    float vd = length(screenUv - 0.5) * 1.41421356;
    col *= 1.0 - u_vignette * smoothstep(0.35, 1.0, vd);
  }
  if (u_cursorPresence > 0.001 && u_cursorEffect > 3.5)
    col += (vec3(0.18) + col * 0.12) * cursorMask * u_cursorStrength;
  if (u_grain > 0.0001)
    col += (grainHash(gl_FragCoord.xy + vec2(u_seed * 17.0, u_seed * 31.0)) - 0.5) * u_grain;
  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
`;

/** The original "Silk" preset colours: near-black green, forest, lime highlight, near-black. */
export const SILK_GREEN = ["#0a0f00", "#13350d", "#d9fe9a", "#131801"];

const SETTINGS = {
  scale: 1.26,
  intensity: 0.09,
  paramA: 0.5,
  warp: 0,
  detail: 2.4,
  contrast: 1.113,
  brightness: 0,
  saturation: 1,
  hue: 0,
  vignette: 0,
  blur: 0,
  grain: 0.22,
  seed: 1581,
  rotate: 0,
  offsetX: -0.23,
  offsetY: 0,
  drift: 0,
  cursorEffect: 2,
  cursorStrength: 0.65,
  cursorRadius: 0.46,
  oklab: 0,
  timeScale: 0.309,
};

/** "#rrggbb" → [r, g, b] in 0..1. */
const toRgb = (hex) => {
  const n = parseInt(hex.replace("#", ""), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
};

// A canvas whose context is being released after unmount; a quick remount
// (Strict Mode) cancels the release and reuses it.
const pendingContextReleases = new WeakMap();
// Next keeps a page mounted but hidden while the user is elsewhere and runs this
// cleanup, so the same canvas can come back later with its context already
// released. The extension is kept to restore that context on the way back.
const releasedContexts = new WeakMap();
const restorable = new WeakSet();

/**
 * @param {object} props
 * @param {string} [props.className]
 * @param {string[]} [props.colors] 2–8 hex colours along the silk folds
 * @param {number} [props.grain] film grain amount (0 = none)
 * @param {number} [props.speed] motion speed multiplier (1 = the preset's pace)
 */
export function ShaderBackground({ className = "", colors = SILK_GREEN, grain = SETTINGS.grain, speed = 1 }) {
  const canvasRef = useRef(null);
  const colorKey = colors.join(",");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const pendingRelease = pendingContextReleases.get(canvas);
    if (pendingRelease !== undefined) window.clearTimeout(pendingRelease);
    pendingContextReleases.delete(canvas);
    const gl = canvas.getContext("webgl", { antialias: false, premultipliedAlpha: false });
    if (!gl) return undefined;

    // A context can only be restored if its "lost" event is cancelled.
    if (!restorable.has(canvas)) {
      restorable.add(canvas);
      canvas.addEventListener("webglcontextlost", (e) => e.preventDefault());
    }

    /** Builds the program and starts the loop; returns its cleanup. */
    const start = () => {
      const compile = (type, src) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        return s;
      };
      const program = gl.createProgram();
      const vertexShader = compile(gl.VERTEX_SHADER, VERT);
      const fragmentShader = compile(gl.FRAGMENT_SHADER, FRAG);
      gl.attachShader(program, vertexShader);
      gl.attachShader(program, fragmentShader);
      gl.linkProgram(program);
      gl.deleteShader(vertexShader);
      gl.deleteShader(fragmentShader);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        gl.deleteProgram(program);
        return undefined;
      }
      gl.useProgram(program);

      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(program, "a_position");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

      const at = (name) => gl.getUniformLocation(program, name);
      const uni = { scene: at("u_scene"), space: at("u_space") };
      const palette = colorKey.split(",").slice(0, 8).map(toRgb);
      const padded = [...palette, ...Array(8 - palette.length).fill(palette.at(-1))];
      gl.uniform3fv(at("u_colors"), new Float32Array(padded.flat()));
      const S = SETTINGS;
      gl.uniform4f(at("u_shape"), S.scale, S.intensity, S.paramA, S.warp);
      gl.uniform4f(at("u_surface"), S.detail, S.contrast, S.brightness, S.saturation);
      gl.uniform4f(at("u_finish"), S.hue, S.vignette, S.blur, grain);
      gl.uniform4f(at("u_transform"), S.seed, S.rotate, S.drift, S.oklab);
      // The pointer effect is off in this preset.
      gl.uniform4f(at("u_cursor"), 0, S.cursorEffect, S.cursorStrength, S.cursorRadius);
      gl.uniform4f(uni.space, S.offsetX, S.offsetY, 0, 0);

      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      let raf = 0;
      let visible = document.visibilityState === "visible";
      let inView = true;
      let disposed = false;
      const start = performance.now();

      const resizeCanvas = () => {
        const bounds = canvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const rawWidth = Math.max(1, Math.round(bounds.width * dpr));
        const rawHeight = Math.max(1, Math.round(bounds.height * dpr));
        // Cap the pixel count; the silk is soft, so a lower resolution is not visible.
        const pixelScale = Math.min(1, Math.sqrt(2_000_000 / Math.max(1, rawWidth * rawHeight)));
        const width = Math.max(1, Math.round(rawWidth * pixelScale));
        const height = Math.max(1, Math.round(rawHeight * pixelScale));
        if (canvas.width !== width || canvas.height !== height) {
          canvas.width = width;
          canvas.height = height;
          gl.viewport(0, 0, width, height);
        }
      };

      const draw = (now) => {
        resizeCanvas();
        gl.uniform4f(uni.scene, canvas.width, canvas.height, ((now - start) / 1000) * S.timeScale * speed, palette.length);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      };

      const render = (now) => {
        raf = 0;
        if (disposed || !visible || !inView) return;
        draw(now);
        if (!reduced) raf = requestAnimationFrame(render);
      };
      const requestRender = () => {
        if (!disposed && visible && inView && raf === 0) raf = requestAnimationFrame(render);
      };
      const stop = () => {
        if (raf !== 0) cancelAnimationFrame(raf);
        raf = 0;
      };

      const resizeObserver = new ResizeObserver(requestRender);
      resizeObserver.observe(canvas);
      const intersectionObserver = new IntersectionObserver(([entry]) => {
        inView = entry?.isIntersecting ?? true;
        if (inView) requestRender();
        else stop();
      });
      intersectionObserver.observe(canvas);
      const onVisibilityChange = () => {
        visible = document.visibilityState === "visible";
        if (visible) requestRender();
        else stop();
      };
      document.addEventListener("visibilitychange", onVisibilityChange);
      requestRender();

      return () => {
        disposed = true;
        stop();
        resizeObserver.disconnect();
        intersectionObserver.disconnect();
        document.removeEventListener("visibilitychange", onVisibilityChange);
        gl.deleteBuffer(buf);
        gl.deleteProgram(program);
        const releaseTimer = window.setTimeout(() => {
          if (pendingContextReleases.get(canvas) !== releaseTimer) return;
          pendingContextReleases.delete(canvas);
          const ext = gl.getExtension("WEBGL_lose_context");
          if (ext) {
            releasedContexts.set(canvas, ext);
            ext.loseContext();
          }
          canvas.width = 1;
          canvas.height = 1;
        }, 0);
        pendingContextReleases.set(canvas, releaseTimer);
      };
    };

    let stop = null;
    let cancelled = false;
    const onRestored = () => {
      if (!cancelled) stop = start();
    };
    if (gl.isContextLost()) {
      // Back on a page whose context was released: restore it, then draw again.
      const ext = releasedContexts.get(canvas);
      if (!ext) return undefined;
      canvas.addEventListener("webglcontextrestored", onRestored, { once: true });
      ext.restoreContext();
    } else {
      stop = start();
    }
    return () => {
      cancelled = true;
      canvas.removeEventListener("webglcontextrestored", onRestored);
      stop?.();
    };
  }, [colorKey, grain, speed]);

  return <canvas ref={canvasRef} aria-hidden="true" className={`block size-full ${className}`} />;
}
