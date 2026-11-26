/* Mia Presence — 3D avatar layer.
 *
 * Runs inside the HUD as an ES module. It loads a Ready Player Me-compatible
 * GLB (Mixamo rig, ARKit 52 / Oculus 15 morph targets), adds a separate idle
 * clip, and drives face, gaze, breathing and wardrobe from the same events the
 * voice pipeline already emits. If anything fails, the caller keeps the 2D
 * reactor ring; this module never throws into the HUD.
 */

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const DEFAULTS = {
  enabled: true,
  model: '/hud/avatar/models/mia-female.glb',
  idle: '/hud/avatar/models/mia-female-idle.glb',
  hair: true,
  hairStyle: 'default',
  glasses: false,
  top: true,
  bottom: true,
  footwear: true,
  hairColor: '#3b2418',
  topColor: '#1d3f52',
  bottomColor: '#101820',
  footwearColor: '#101820',
  glassesColor: '#101820',
  skinTone: '#ffffff',
  camera: 'bust',
  quality: 'high',
  mood: 'neutral',
};

const VISEMES = ['sil', 'PP', 'FF', 'TH', 'DD', 'kk', 'CH', 'SS', 'nn', 'RR',
  'aa', 'E', 'I', 'O', 'U'];

const MOODS = {
  neutral: {},
  warm: { mouthSmileLeft: .22, mouthSmileRight: .22, cheekSquintLeft: .08,
    cheekSquintRight: .08, browInnerUp: .08 },
  happy: { mouthSmileLeft: .45, mouthSmileRight: .45, cheekSquintLeft: .18,
    cheekSquintRight: .18, browInnerUp: .12 },
  sad: { mouthFrownLeft: .35, mouthFrownRight: .35, browInnerUp: .35,
    browDownLeft: .15, browDownRight: .15, eyeSquintLeft: .1 },
  angry: { browDownLeft: .45, browDownRight: .45, mouthPressLeft: .2,
    mouthPressRight: .2, noseSneerLeft: .15, noseSneerRight: .15 },
  fearful: { browInnerUp: .45, browOuterUpLeft: .25, browOuterUpRight: .25,
    eyeWideLeft: .35, eyeWideRight: .35, mouthStretchLeft: .2,
    mouthStretchRight: .2 },
  disgust: { noseSneerLeft: .35, noseSneerRight: .35, mouthUpperUpLeft: .15,
    mouthUpperUpRight: .15 },
  love: { mouthSmileLeft: .3, mouthSmileRight: .3, cheekSquintLeft: .15,
    cheekSquintRight: .15, eyeSquintLeft: .2, eyeSquintRight: .2 },
  sleep: { eyesClosed: .85, eyeBlinkLeft: .85, eyeBlinkRight: .85,
    mouthClose: .3 },
};

const VIS_OPEN = { aa: .85, E: .55, I: .35, O: .72, U: .42, sil: 0,
  PP: 0, FF: .12, TH: .18, DD: .18, kk: .15, CH: .25, SS: .15,
  nn: .12, RR: .2 };

/* Procedural co-speech gestures. The free model ships one Mixamo idle clip and
 * no gesture library, so gestures are additive head/chest offsets driven by
 * the `[gesture:…]` tag that the server forwards with each sentence. */
const GESTURES = {
  nod: { dur: .7, head: { x: .07 } },
  shake: { dur: .8, head: { y: .07 }, cycles: 2 },
  tilt: { dur: .9, head: { z: .09 } },
  look: { dur: .9, head: { y: -.08 }, chest: { z: .02 } },
  wave: { dur: 1.2, head: { z: .05 }, chest: { z: .05, y: .04 } },
  shrug: { dur: 1.0, chest: { x: -.05, z: .03 } },
  point: { dur: .8, head: { y: .08 }, chest: { y: .03 } },
  bow: { dur: 1.3, head: { x: .12 }, chest: { x: .12 } },
};

const LOOKS = {
  user: 'pointer', camera: 'camera', away: 'away',
  left: [-.55, 0], right: [.55, 0], up: [0, -.35], down: [0, .35],
};

function clamp(v, lo = 0, hi = 1) { return Math.min(hi, Math.max(lo, v)); }
function lerp(a, b, t) { return a + (b - a) * t; }

function cacheBust(url) {
  const sep = url.includes('?') ? '&' : '?';
  return url + sep + 'v=' + Date.now();
}

function disposeTree(root) {
  root.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    const mats = Array.isArray(o.material) ? o.material : (o.material ? [o.material] : []);
    for (const m of mats) {
      for (const key of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'emissiveMap']) {
        if (m[key]) m[key].dispose();
      }
      m.dispose();
    }
  });
}

class MiaAvatar {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.model = null;
    this.mixer = null;
    this.head = null;
    this.eyes = [];
    this.teeth = null;
    this.bones = {};
    this.config = { ...DEFAULTS };
    this.state = 'standby';
    this.mood = 'neutral';
    this.hairMeshes = [];
    this.current = new Map();
    this.speech = null;
    this.gesture = null;
    this.look = null;
    this._loading = null;
    this.lastBlink = 0;
    this.nextBlink = 2 + Math.random() * 4;
    this.blinkUntil = 0;
    this.pointer = { x: 0, y: 0 };
    this.clock = new THREE.Clock();
    this.ready = false;
    this.failed = false;
    this.frameTime = 16;
    this.qualityScale = 1;
    this._bindEvents();
  }

  _bindEvents() {
    window.addEventListener('resize', () => this.resize());
    window.addEventListener('pointermove', (e) => {
      this.pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
      this.pointer.y = (e.clientY / window.innerHeight) * 2 - 1;
    });
    window.addEventListener('storage', (e) => {
      if (e.key === 'mia.avatar.config' && e.newValue) {
        try { this.configure(JSON.parse(e.newValue), false); } catch {}
      }
    });
    window.addEventListener('mia-avatar-configure', (e) => {
      if (e.detail) this.configure(e.detail, true);
    });
  }

  async init() {
    try {
      this.config = await this.loadConfig();
      const qp = new URLSearchParams(location.search);
      if (qp.get('model')) this.config.model = qp.get('model');
      if (!this.config.enabled) return;
      this.setupRenderer();
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(32, 1, 0.01, 30);
      this.setupLights();
      await this.loadModel();
      await this.loadIdle();
      this.applyConfig(this.config);
      this.ready = true;
      this.resize();
      this.canvas.classList.add('online');
      document.body.classList.add('avatar-ready');
      window.dispatchEvent(new CustomEvent('mia-avatar-ready'));
      this.loop();
    } catch (err) {
      this.failed = true;
      console.warn('[mia-avatar] falling back to reactor:', err);
      document.body.classList.remove('avatar-ready');
      window.dispatchEvent(new CustomEvent('mia-avatar-failed',
        { detail: String(err && err.message || err) }));
    }
  }

  async loadConfig() {
    try {
      const r = await fetch('/api/avatar/config', { cache: 'no-store' });
      if (!r.ok) throw new Error('config ' + r.status);
      const j = await r.json();
      return { ...DEFAULTS, ...(j.config || j || {}) };
    } catch {
      try {
        const local = JSON.parse(localStorage.getItem('mia.avatar.config') || 'null');
        if (local) return { ...DEFAULTS, ...local };
      } catch {}
      return { ...DEFAULTS };
    }
  }

  async saveConfig() {
    try {
      localStorage.setItem('mia.avatar.config', JSON.stringify(this.config));
    } catch {}
    try {
      await fetch('/api/avatar/config', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.config),
      });
    } catch {}
  }

  setupRenderer() {
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas, antialias: true, alpha: true,
      powerPreference: 'high-performance',
    });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.shadowMap.enabled = this.config.quality !== 'balanced';
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.sceneEnv = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  }

  setupLights() {
    this.scene.environment = this.sceneEnv;
    const hemi = new THREE.HemisphereLight(0x9fd8e8, 0x08111c, 1.5);
    this.scene.add(hemi);
    const key = new THREE.DirectionalLight(0xffe4c8, 3.2);
    key.position.set(2.2, 3.2, 2.4);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.near = .1;
    key.shadow.camera.far = 8;
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0x00e5ff, 2.4);
    rim.position.set(-2.4, 2.2, -1.8);
    this.scene.add(rim);
    const fill = new THREE.PointLight(0x19f0d8, 2.2, 6);
    fill.position.set(-1.1, 1.3, 1.4);
    this.scene.add(fill);
  }

  async loadModel() {
    this.eyes = []; this.morphMeshes = []; this.teeth = null; this.bones = {};
    this.hairMeshes = [];
    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(cacheBust(this.config.model));
    this.model = gltf.scene;
    this.model.traverse((o) => {
      if (o.isMesh || o.isSkinnedMesh) {
        o.castShadow = true;
        o.receiveShadow = true;
        o.frustumCulled = false;
        if (o.material) {
          o.material.envMapIntensity = .65;
          if (o.material.map) o.material.map.anisotropy = 4;
        }
      }
      if (o.isBone) this.bones[o.name] = o;
      if ((o.isMesh || o.isSkinnedMesh) && o.morphTargetDictionary)
        this.morphMeshes.push(o);
    });
    this.head = this.model.getObjectByName('Wolf3D_Head') || this._firstMorphMesh();
    this.teeth = this.model.getObjectByName('Wolf3D_Teeth');
    this.eyes = [];
    for (const name of ['EyeLeft', 'EyeRight', 'Wolf3D_Head', 'Wolf3D_Teeth']) {
      const m = this.model.getObjectByName(name);
      if (m && m.morphTargetDictionary) this.eyes.push(m);
    }
    this.model.traverse((o) => {
      if ((o.isMesh || o.isSkinnedMesh) && /hair/i.test(o.name) && o.geometry)
        this.hairMeshes.push(o);
    });
    this.hairMeshes.sort((a, b) => a.name.localeCompare(b.name));
    this.scene.add(this.model);
    this.frameModel();
  }

  /* Swap the avatar GLB without rebuilding the scene (used by /hud/avatar.html). */
  async reloadModel(url) {
    if (!url || !this.ready) return false;
    const previous = this.config.model;
    this.config.model = url;
    try {
      if (this._loading) return false;
      this._loading = url;
      if (this.mixer) { this.mixer.stopAllAction(); this.mixer = null; }
      if (this.model) {
        this.scene.remove(this.model);
        disposeTree(this.model);
        this.model = null;
      }
      this.speech = null; this.gesture = null; this.look = null;
      this.current.clear();
      await this.loadModel();
      await this.loadIdle();
      this.applyConfig(this.config);
      this.failed = false;
      this.canvas.classList.add('online');
      document.body.classList.add('avatar-ready');
      window.dispatchEvent(new CustomEvent('mia-avatar-ready'));
      return true;
    } catch (err) {
      console.warn('[mia-avatar] model swap failed:', err);
      this.config.model = previous;
      try {
        await this.loadModel();
        await this.loadIdle();
        this.applyConfig(this.config);
      } catch {}
      return false;
    } finally {
      this._loading = null;
    }
  }

  /* Hair styles available in the loaded GLB, in selection order. */
  hairStyles() {
    const out = this.hairMeshes.map((m, i) => ({
      id: i === 0 ? 'default' : (i === 1 ? 'alt' : 'alt' + i),
      label: i === 0 ? 'pričeska 1' : 'pričeska ' + (i + 1),
      mesh: m.name,
    }));
    out.push({ id: 'none', label: 'brez', mesh: null });
    return out;
  }

  _applyHair() {
    const mesh = this._hairTarget();
    for (const m of this.hairMeshes) m.visible = m === mesh;
  }

  _hairTarget() {
    if (this.config.hair === false || this.config.hairStyle === 'none') return null;
    const styles = this.hairStyles().filter((s) => s.id !== 'none');
    if (!styles.length) return null;
    const want = this.config.hairStyle && this.config.hairStyle !== 'default'
      ? styles.find((s) => s.id === this.config.hairStyle) : styles[0];
    const style = want || styles[0];
    return this.hairMeshes.find((m) => m.name === style.mesh) || this.hairMeshes[0];
  }

  async loadIdle() {
    if (!this.config.idle) return;
    try {
      const gltf = await new GLTFLoader().loadAsync(cacheBust(this.config.idle));
      if (!gltf.animations || !gltf.animations.length) return;
      this.mixer = new THREE.AnimationMixer(this.model);
      const action = this.mixer.clipAction(gltf.animations[0]);
      action.play();
    } catch (e) {
      console.warn('[mia-avatar] idle clip unavailable:', e);
    }
  }

  _firstMorphMesh() {
    let found = null;
    this.model.traverse((o) => {
      if (!found && o.isMesh && o.morphTargetDictionary) found = o;
    });
    return found;
  }

  frameModel() {
    const box = new THREE.Box3().setFromObject(this.model);
    const size = new THREE.Vector3();
    box.getSize(size);
    this.modelSize = size;
    this.modelCenter = box.getCenter(new THREE.Vector3());
    this.setCamera(this.config.camera || 'bust');
  }

  setCamera(view) {
    if (!this.camera || !this.modelSize) return;
    const c = this.modelCenter;
    const y = c.y;
    const views = {
      full: { y: y, z: Math.max(3.2, this.modelSize.y * 1.75), look: y },
      bust: { y: y + this.modelSize.y * 0.22, z: Math.max(2.35, this.modelSize.y * 1.32),
              look: y + this.modelSize.y * 0.22 },
      head: { y: y + this.modelSize.y * 0.32, z: 1.05,
              look: y + this.modelSize.y * 0.32 },
    };
    const v = views[view] || views.bust;
    this.camera.position.set(c.x, v.y, v.z);
    this.camera.lookAt(c.x, v.look, c.z * 0.02);
    this.camera.updateProjectionMatrix();
    this.resize();
  }

  resize() {
    if (!this.renderer || !this.camera) return;
    const parent = this.canvas.parentElement;
    const w = Math.max(64, parent ? parent.clientWidth : window.innerWidth);
    const h = Math.max(64, parent ? parent.clientHeight : window.innerHeight);
    const dpr = Math.min(window.devicePixelRatio || 1,
      this.qualityScale >= 1 ? 2 : 1.25);
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  applyConfig(cfg) {
    this.config = { ...this.config, ...cfg };
    if (!this.model) return;
    const vis = (name, on) => {
      const o = this.model.getObjectByName(name);
      if (o) o.visible = !!on;
    };
    this._applyHair();
    vis('Wolf3D_Glasses', !!this.config.glasses);
    vis('Wolf3D_Outfit_Top', this.config.top !== false);
    vis('Wolf3D_Outfit_Bottom', this.config.bottom !== false);
    vis('Wolf3D_Outfit_Footwear', this.config.footwear !== false);
    for (const m of this.hairMeshes) this.tintMesh(m, this.config.hairColor);
    this.tint('Wolf3D_Glasses', this.config.glassesColor);
    this.tint('Wolf3D_Outfit_Top', this.config.topColor);
    this.tint('Wolf3D_Outfit_Bottom', this.config.bottomColor);
    this.tint('Wolf3D_Outfit_Footwear', this.config.footwearColor);
    this.tint('Wolf3D_Body', this.config.skinTone);
    this.tint('Wolf3D_Head', this.config.skinTone);
    this.setMood(this.config.mood || this.mood);
    if (this.config.camera) this.setCamera(this.config.camera);
    this.qualityScale = this.config.quality === 'balanced' ? .75 :
      this.config.quality === 'high' ? 1 : 1.25;
    this.resize();
    document.body.classList.toggle('avatar-hair-off',
      this.config.hair === false || this.config.hairStyle === 'none');
  }

  tint(name, color) {
    const o = this.model && this.model.getObjectByName(name);
    if (o) this.tintMesh(o, color);
  }

  tintMesh(o, color) {
    if (!o || !color) return;
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      if (!m) continue;
      if (m.userData.__baseColor === undefined) {
        m.userData.__baseColor = m.color ? m.color.clone() : null;
      }
      if (m.color) m.color.set(color);
      m.needsUpdate = true;
    }
  }

  setMood(mood) {
    this.mood = MOODS[mood] ? mood : 'neutral';
    this.config.mood = this.mood;
  }

  setState(st) {
    const map = { standby: 'standby', listening: 'listening',
      thinking: 'thinking', tool: 'tool', tool_use: 'tool', speaking: 'speaking',
      error: 'error', stopped: 'standby' };
    this.state = map[st] || st || 'standby';
    if (this.state === 'thinking') this.setMood('neutral');
    if (this.state === 'listening') this.setMood('warm');
    if (this.state === 'error') this.setMood('sad');
    if (this.state === 'speaking') this.setMood(this._speechMood || 'warm');
    if (this.state !== 'speaking') this.stopSpeech();
    document.body.classList.toggle('avatar-speaking', this.state === 'speaking');
  }

  playGesture(name) {
    const gesture = GESTURES[name];
    if (!gesture || !this.ready) return false;
    this.gesture = { ...gesture, name, start: performance.now() / 1000 };
    return true;
  }

  setLook(look) {
    this.look = look && LOOKS[look] !== undefined ? look : null;
  }

  configure(patch, save = true) {
    this.applyConfig(patch || {});
    if (save) this.saveConfig();
  }

  /* payload: {visemes, times, durations, duration_ms, text, mood, gesture, look} */
  speak(payload) {
    if (!payload || !this.ready) return;
    const visemes = Array.isArray(payload.visemes) ? payload.visemes : [];
    const times = Array.isArray(payload.times) ? payload.times : [];
    const durations = Array.isArray(payload.durations) ? payload.durations : [];
    if (!visemes.length) return;
    this._speechMood = payload.mood || 'warm';
    this.setMood(this._speechMood);
    this.setLook(payload.look ? String(payload.look).toLowerCase() : null);
    if (payload.gesture) this.playGesture(String(payload.gesture).toLowerCase());
    this.speech = {
      start: performance.now() / 1000 + Math.max(.05,
        (window.MiaAudio && window.MiaAudio.delay ? window.MiaAudio.delay() : 0) + .02),
      visemes, times, durations,
      total: Math.max(Number(payload.duration_ms || 0) / 1000,
        (times[times.length - 1] + durations[durations.length - 1]) / 1000),
      pointer: 0,
    };
  }

  speakText(text, durationMs, extra) {
    if (!text) return;
    const timeline = textTimeline(text, durationMs || Math.max(800, text.length * 70));
    this.speak({ ...timeline, text, mood: 'warm', ...(extra || {}) });
  }

  stopSpeech() {
    this.speech = null;
    this.look = null;
  }

  _gestureOffsets(now) {
    const g = this.gesture;
    if (!g) return null;
    const p = (now - g.start) / g.dur;
    if (p >= 1) { this.gesture = null; return null; }
    const env = Math.sin(Math.PI * Math.min(1, Math.max(0, p)));
    const wave = g.cycles ? Math.cos(2 * Math.PI * g.cycles * p) : 1;
    const scale = env * wave;
    return {
      head: { x: (g.head?.x || 0) * scale, y: (g.head?.y || 0) * scale,
        z: (g.head?.z || 0) * scale },
      chest: { x: (g.chest?.x || 0) * scale, y: (g.chest?.y || 0) * scale,
        z: (g.chest?.z || 0) * scale },
    };
  }

  update(dt, now) {
    if (!this.ready) return;
    if (this.mixer) this.mixer.update(dt);
    const t = now;

    // blinking: Poisson-ish gaps, plus a double blink sometimes
    if (t > this.nextBlink && t > this.blinkUntil + .2) {
      this.blinkUntil = t + .11;
      this.nextBlink = t + 2.2 + Math.random() * 4.8;
      if (Math.random() < .18) this.nextBlink = t + .28;
    }
    const blink = t < this.blinkUntil ? 1 : 0;

    // gaze target: pointer while listening/speaking; away while thinking/tool,
    // unless the sentence carried an explicit [look:…] tag
    const think = this.state === 'thinking' || this.state === 'tool';
    let targetX = think ? (this.state === 'tool' ? .35 : -.25) : this.pointer.x * .22;
    let targetY = think ? (this.state === 'tool' ? -.1 : .18) : -this.pointer.y * .12;
    const look = this.look ? LOOKS[this.look] : null;
    if (Array.isArray(look)) { targetX = look[0]; targetY = look[1]; }
    else if (look === 'camera') { targetX = 0; targetY = 0; }
    else if (look === 'away') { targetX = -.4; targetY = .12; }
    this.gazeX = lerp(this.gazeX || 0, targetX, 1 - Math.pow(.001, dt));
    this.gazeY = lerp(this.gazeY || 0, targetY, 1 - Math.pow(.001, dt));

    const gest = this._gestureOffsets(now);
    const head = this.bones.Head || this.bones.head;
    if (head) {
      const sway = Math.sin(t * .6) * .012 + (this.state === 'speaking' ? Math.sin(t * 3.1) * .008 : 0);
      head.rotation.y = lerp(head.rotation.y, this.gazeX + (gest ? gest.head.y : 0), .08);
      head.rotation.x = lerp(head.rotation.x, this.gazeY * .6 + sway + (gest ? gest.head.x : 0), .06);
      head.rotation.z = lerp(head.rotation.z, Math.sin(t * .35) * .01 + (gest ? gest.head.z : 0), .05);
    }
    const chest = this.bones.Spine2 || this.bones.Spine1 || this.bones.Spine;
    if (chest) {
      const breath = Math.sin(t * 1.25) * .012;
      chest.rotation.x = lerp(chest.rotation.x, breath + (gest ? gest.chest.x : 0), .05);
      chest.rotation.y = lerp(chest.rotation.y, gest ? gest.chest.y : 0, .05);
      chest.rotation.z = lerp(chest.rotation.z, gest ? gest.chest.z : 0, .05);
      chest.scale.y = 1 + Math.sin(t * 1.25) * .006;
    }

    const desired = new Map();
    const mood = MOODS[this.mood] || MOODS.neutral;
    for (const [k, v] of Object.entries(mood)) desired.set(k, v);
    const moodClosed = desired.get('eyesClosed') || 0;
    const shut = Math.max(blink, moodClosed);
    desired.set('eyesClosed', shut);
    desired.set('eyeBlinkLeft', shut);
    desired.set('eyeBlinkRight', shut);
    const hx = clamp(this.gazeX, -1, 1);
    const vy = clamp(this.gazeY, -1, 1);
    desired.set('eyeLookInLeft', Math.max(0, hx) * .3);
    desired.set('eyeLookOutRight', Math.max(0, hx) * .3);
    desired.set('eyeLookOutLeft', Math.max(0, -hx) * .3);
    desired.set('eyeLookInRight', Math.max(0, -hx) * .3);
    desired.set('eyeLookUpLeft', Math.max(0, -vy) * .3);
    desired.set('eyeLookUpRight', Math.max(0, -vy) * .3);
    desired.set('eyeLookDownLeft', Math.max(0, vy) * .3);
    desired.set('eyeLookDownRight', Math.max(0, vy) * .3);

    if (this.speech) {
      const el = now - this.speech.start;
      if (el < 0) {
        // wait for audio start
      } else if (el > this.speech.total + .15) {
        this.speech = null;
        this.look = null;
        if (this.state === 'speaking') this.state = 'listening';
      } else {
        this._applySpeech(el, desired);
      }
    }

    // smooth and write morph influences
    const rate = 1 - Math.pow(.0001, dt);
    for (const [name, value] of desired) {
      const cur = this.current.get(name) || 0;
      const next = lerp(cur, value, name.startsWith('viseme_') ? Math.min(1, rate * 2.6) : rate);
      this.current.set(name, next);
      this._setMorph(name, next);
    }
    // decay targets that are no longer desired
    for (const name of this.current.keys()) {
      if (desired.has(name)) continue;
      const next = lerp(this.current.get(name), 0, rate);
      this.current.set(name, next);
      this._setMorph(name, next);
    }
  }

  _applySpeech(el, desired) {
    const s = this.speech;
    while (s.pointer + 1 < s.times.length && s.times[s.pointer + 1] <= el * 1000) {
      s.pointer++;
    }
    const i = Math.min(s.pointer, s.visemes.length - 1);
    const v = s.visemes[i] || 'sil';
    const open = VIS_OPEN[v] !== undefined ? VIS_OPEN[v] : .15;
    desired.set('viseme_' + v, .95);
    desired.set('jawOpen', open * .75);
    desired.set('mouthOpen', open);
    // soft coarticulation: blend neighbours while their windows overlap
    const next = s.visemes[i + 1];
    if (next && next !== v) {
      const nextStart = s.times[i + 1] / 1000;
      const w = Math.max(0, 1 - (nextStart - el) / .055);
      if (w > 0) desired.set('viseme_' + next, .55 * w);
    }
  }

  _setMorph(name, value) {
    for (const mesh of this.morphMeshes) {
      const dict = mesh.morphTargetDictionary;
      if (!dict) continue;
      const idx = dict[name];
      if (idx !== undefined && mesh.morphTargetInfluences) {
        mesh.morphTargetInfluences[idx] = clamp(value);
      }
    }
  }

  loop() {
    if (!this.ready) return;
    requestAnimationFrame(() => this.loop());
    const dt = Math.min(.05, this.clock.getDelta());
    this.frameTime = lerp(this.frameTime, dt * 1000, .05);
    if (this.qualityScale > .8 && this.frameTime > 30) {
      this.qualityScale = Math.max(.7, this.qualityScale - .05);
      this.resize();
    }
    this.update(dt, performance.now() / 1000);
    this.renderer.render(this.scene, this.camera);
  }
}

/* Slovenian/English grapheme → Oculus viseme fallback used for `mia_say`
 * reminders and for browsers that do not receive a server timeline. */
function textTimeline(text, durationMs) {
  const norm = String(text || '').toLowerCase().replace(/[^a-zčćžšđ0-9\s.,!?;:]+/gi, ' ');
  const out = [];
  let i = 0;
  const push = (v, w = 1) => out.push({ v, w });
  while (i < norm.length) {
    const ch = norm[i];
    const two = norm.slice(i, i + 2);
    if (ch === ' ' || ch === '\n') { push('sil', 1.3); i++; continue; }
    if ('.!?;:,'.includes(ch)) { push('sil', ch === ',' ? 2 : 3); i++; continue; }
    if (two === 'lj' || two === 'nj' || two === 'dž' || two === 'dz') {
      push('nn', 1); i += 2; continue;
    }
    if ('aeiou'.includes(ch)) {
      push({ a: 'aa', e: 'E', i: 'I', o: 'O', u: 'U' }[ch], 1.35); i++; continue;
    }
    if ('pb m'.replace(' ', '').includes(ch)) { push('PP', .8); i++; continue; }
    if ('fv'.includes(ch)) { push('FF', .7); i++; continue; }
    if ('td'.includes(ch)) { push('DD', .65); i++; continue; }
    if ('kg'.includes(ch)) { push('kk', .6); i++; continue; }
    if ('čćšž'.includes(ch)) { push('CH', .8); i++; continue; }
    if ('szc'.includes(ch)) { push('SS', .75); i++; continue; }
    if ('nl'.includes(ch)) { push('nn', .7); i++; continue; }
    if (ch === 'r') { push('RR', .8); i++; continue; }
    if (ch === 'h') { push('kk', .5); i++; continue; }
    if ('j'.includes(ch)) { push('I', .5); i++; continue; }
    if (ch === 'đ') { push('CH', .8); i++; continue; }
    i++;
  }
  if (!out.length) out.push({ v: 'sil', w: 1 });
  const totalW = out.reduce((a, b) => a + b.w, 0);
  const scale = Math.max(300, durationMs) / totalW;
  const visemes = [], times = [], durations = [];
  let t = 0;
  for (const item of out) {
    const d = item.w * scale;
    visemes.push(item.v);
    times.push(Math.round(t));
    durations.push(Math.max(35, Math.round(d)));
    t += d;
  }
  return { visemes, times, durations, duration_ms: Math.round(t) };
}

function boot() {
  const canvas = document.getElementById('avatar');
  if (!canvas) return;
  const avatar = new MiaAvatar(canvas);
  window.MiaAvatar = avatar;
  avatar.init();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot, { once: true });
} else {
  boot();
}

export { MiaAvatar, textTimeline, DEFAULTS, GESTURES, LOOKS };
