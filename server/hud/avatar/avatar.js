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
import {
  DEFAULTS, PRESETS, OUTFIT_PRESETS, LIGHT_PRESETS, CAMERA_PRESETS,
  HAIR_LOOKS, HAIR_STYLES, ACCESSORY_STYLES, BODY_SHAPES, HAIR_COLORS,
  SKIN_TONES, EYE_COLORS, TOP_STYLES,
} from './presets.js';
import {
  ACTIONS, resolveAction, samplePose, mixPose, addPose,
} from './motion.js';
import { buildHair, disposeHair } from './hair.js';
import { buildAccessory } from './garments.js';

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

const GESTURES = ACTIONS;

const AXES = [
  ['x', new THREE.Vector3(1, 0, 0)],
  ['y', new THREE.Vector3(0, 1, 0)],
  ['z', new THREE.Vector3(0, 0, 1)],
];


const LOOKS = {
  user: 'pointer', camera: 'camera', away: 'away',
  left: [-.55, 0], right: [.55, 0], up: [0, -.35], down: [0, .35],
};

function clamp(v, lo = 0, hi = 1) { return Math.min(hi, Math.max(lo, v)); }
function lerp(a, b, t) { return a + (b - a) * t; }
function num(v, fallback = 0) { const n = Number(v); return Number.isFinite(n) ? n : fallback; }
function color(value, fallback = '#ffffff') {
  return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
}

const MESH_NAMES = {
  top: [/outfit_top/i, /shirt/i, /^top$/i],
  bottom: [/outfit_bottom/i, /pants/i, /^bottom$/i],
  footwear: [/outfit_footwear/i, /footwear/i, /shoes?/i],
  glasses: [/glasses/i, /^avaturn_look_0$/i],
  body: [/^wolf3d_body$/i, /body/i],
  head: [/^wolf3d_head$/i, /^head$/i],
  eyes: [/^eyeleft$/i, /^eyeright$/i],
  teeth: [/^wolf3d_teeth$/i, /teeth/i],
};

const SHAPE_BONES = {
  head: ['Head'], neck: ['Neck'],
  arm: ['LeftArm', 'RightArm'], forearm: ['LeftForeArm', 'RightForeArm'],
  shoulder: ['LeftShoulder', 'RightShoulder'], hips: ['Hips'],
  upperLeg: ['LeftUpLeg', 'RightUpLeg'], leg: ['LeftLeg', 'RightLeg'],
  hand: ['LeftHand', 'RightHand'], foot: ['LeftFoot', 'RightFoot'],
  eyes: ['LeftEye', 'RightEye'],
};

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
    this.action = null;
    this.fade = null;
    this.held = null;
    this.lastPose = {};
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
    this.lights = null;
    this.cameraBase = null;
    this._baseBoneScale = null;
    this._baseHairScale = null;
    this._baseModelScale = null;
    this._basePose = null;
    this._orderedBones = null;
    this._worldQuat = new Map();
    this._worldScale = new Map();
    this._desired = new Map();
    this._morphTargets = new Map();
    this._tmpQ = new THREE.Quaternion();
    this._tmpQ2 = new THREE.Quaternion();
    this._tmpV = new THREE.Vector3();
    this._tmpS = new THREE.Vector3();
    this.headFrame = null;
    this.procHair = null;
    this.procHairStyle = null;
    this.accessoryParts = [];
    this._accessoryKey = '';
    this._bgKey = '';
    this.forcePreview = /avatar\.html$/.test(location.pathname);
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
      if (qp.get('camera')) this.config.camera = qp.get('camera');
      if (!this.config.enabled && !this.forcePreview) return;
      this.setupRenderer();
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(32, 1, 0.01, 30);
      this.setupLights();
      await this.loadModel();
      await this.loadIdle();
      this.applyConfig(this.config);
      if (qp.get('pose')) this.holdAction(qp.get('pose'), Number(qp.get('at') || .5));
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
    this.lights = { hemi, key, rim, fill };
  }

  async loadModel() {
    this.eyes = []; this.morphMeshes = []; this.teeth = null; this.bones = {};
    this.hairMeshes = [];
    this._morphTargets = new Map();
    this._disposeAccessory();
    this._disposeHair();
    this._accessoryKey = '';
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
    // Flatten the morph dictionaries once so the render loop writes a morph
    // influence directly instead of scanning every mesh for every name.
    for (const mesh of this.morphMeshes) {
      for (const [name, idx] of Object.entries(mesh.morphTargetDictionary)) {
        let list = this._morphTargets.get(name);
        if (!list) this._morphTargets.set(name, list = []);
        list.push({ mesh, idx });
      }
    }
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
    this._baseBoneScale = new Map();
    for (const b of Object.values(this.bones)) this._baseBoneScale.set(b, b.scale.clone());
    this._baseHairScale = new Map();
    for (const m of this.hairMeshes) this._baseHairScale.set(m, m.scale.clone());
    this._baseModelScale = this.model.scale.clone();
    this.scene.add(this.model);
    this.model.updateMatrixWorld(true);
    this._captureSkeleton();
    this.frameModel();
  }

  /* Rest pose, hierarchy order and the head frame drive additive animation,
   * procedural hair and bone-attached garments. */
  _captureSkeleton() {
    this._worldQuat.clear();
    this._worldScale.clear();
    const boneSet = new Set(Object.values(this.bones));
    this._basePose = new Map();
    for (const bone of boneSet) {
      this._basePose.set(bone, {
        position: bone.position.clone(),
        quaternion: bone.quaternion.clone(),
      });
      this._worldQuat.set(bone, new THREE.Quaternion());
      this._worldScale.set(bone, new THREE.Vector3(1, 1, 1));
    }
    this._orderedBones = [];
    for (const bone of boneSet) {
      let parentBone = null;
      let walk = bone.parent;
      while (walk) {
        if (boneSet.has(walk)) { parentBone = walk; break; }
        walk = walk.parent;
      }
      let depth = 0;
      let node = bone;
      while (node && boneSet.has(node)) { depth += 1; node = node.parent; }
      const ancestor = node || bone.parent;
      const ancestorQuat = ancestor
        ? ancestor.getWorldQuaternion(new THREE.Quaternion())
        : new THREE.Quaternion();
      const ancestorScale = ancestor
        ? ancestor.getWorldScale(new THREE.Vector3())
        : new THREE.Vector3(1, 1, 1);
      this._orderedBones.push({ bone, parentBone, depth, ancestorQuat, ancestorScale });
    }
    this._orderedBones.sort((a, b) => a.depth - b.depth);

    const headMesh = this.model.getObjectByName('Wolf3D_Head') || this.head;
    this.headFrame = null;
    if (headMesh) {
      const box = new THREE.Box3().setFromObject(headMesh);
      const size = new THREE.Vector3();
      box.getSize(size);
      if (size.x > 0.01 && size.y > 0.01 && size.z > 0.01) {
        this.headFrame = {
          center: box.getCenter(new THREE.Vector3()),
          size,
        };
      }
    }
  }

  /* The mixer owns the animated bones, but three.js can skip writing its tracks
   * for a frame at a loop boundary. Restoring the last mixer output (instead of
   * the GLB bind pose) keeps that frame on the idle pose, so the avatar never
   * snaps back to the T-pose while the clip wraps. The cache is taken before
   * the procedural deltas are added, so those deltas cannot accumulate. */
  _restoreBase() {
    if (!this._basePose) return;
    for (const [bone, pose] of this._basePose) {
      bone.position.copy(pose.position);
      bone.quaternion.copy(pose.quaternion);
    }
  }

  _cacheBase() {
    if (!this._basePose) return;
    for (const [bone, pose] of this._basePose) {
      pose.position.copy(bone.position);
      pose.quaternion.copy(bone.quaternion);
    }
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
      this.speech = null; this.action = null; this.fade = null;
      this.lastPose = {}; this.look = null;
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

  /* Load a different idle clip without rebuilding the model. */
  async reloadIdle(url) {
    if (!this.ready || !this.model) return false;
    this.config.idle = url || '';
    if (this.mixer) { this.mixer.stopAllAction(); this.mixer = null; }
    await this.loadIdle();
    return !!this.mixer;
  }

  /* Hair styles available in the loaded GLB plus the procedural wigs. */
  hairStyles() {
    const out = this.hairMeshes.map((m, i) => ({
      id: i === 0 ? 'default' : (i === 1 ? 'alt' : 'alt' + i),
      label: i === 0 ? 'pričeska 1' : 'pričeska ' + (i + 1),
      mesh: m.name,
    }));
    for (const [id, cfg] of Object.entries(HAIR_STYLES)) {
      out.push({ id, label: cfg.label, procedural: true });
    }
    out.push({ id: 'none', label: 'brez', mesh: null });
    return out;
  }

  _hairSelection() {
    if (this.config.hair === false || this.config.hairStyle === 'none') return null;
    const styles = this.hairStyles();
    const want = styles.find((s) => s.id === this.config.hairStyle);
    if (want) return want;
    return styles.find((s) => !s.procedural && s.id !== 'none')
      || styles.find((s) => s.procedural) || null;
  }

  _applyHair() {
    const selection = this._hairSelection();
    const meshStyle = selection && !selection.procedural ? selection : null;
    for (const m of this.hairMeshes) m.visible = !!meshStyle && m.name === meshStyle.mesh;
    this._buildHair(selection && selection.procedural ? selection.id : null);
    if (this.procHair) {
      const scale = Math.max(.2, num(this.config.hairScale, 1));
      const volume = Math.max(.2, num(this.config.hairVolume, 1));
      this.procHair.scale.set(volume, scale, volume);
      const mat = this.procHair.userData.material;
      if (mat && mat.color) mat.color.set(color(this.config.hairColor, '#3b2418'));
      if (mat && this.config.robot === true) {
        mat.emissive.set(color(this.config.robotGlow, '#00e5ff'));
        mat.emissiveIntensity = .12 * num(this.config.robotIntensity, 1);
      } else if (mat && mat.emissive) {
        mat.emissive.set('#000000');
        mat.emissiveIntensity = 0;
      }
    }
  }

  _buildHair(styleId) {
    if (styleId === this.procHairStyle) return;
    this._disposeHair();
    this.procHairStyle = styleId || null;
    if (!styleId || !this.headFrame || !this.bones.Head) return;
    const group = buildHair(styleId, {
      width: this.headFrame.size.x,
      height: this.headFrame.size.y,
      depth: this.headFrame.size.z,
      color: this.config.hairColor,
    });
    if (!group) return;
    group.position.copy(this.headFrame.center);
    this._attachToBone(group, this.bones.Head);
    this.procHair = group;
  }

  _disposeHair() {
    if (!this.procHair) return;
    if (this.procHair.parent) this.procHair.parent.remove(this.procHair);
    disposeHair(this.procHair);
    this.procHair = null;
    this.procHairStyle = null;
  }

  /* Re-parent a world-space object to a bone without moving it. */
  _attachToBone(object, bone) {
    if (!object || !bone) return;
    this.model.updateMatrixWorld(true);
    const inverse = new THREE.Matrix4().copy(bone.matrixWorld).invert();
    object.applyMatrix4(inverse);
    bone.add(object);
  }

  _boneWorld(name) {
    const bone = this.bones[name];
    if (!bone) return null;
    return {
      pos: bone.getWorldPosition(new THREE.Vector3()),
      dir: new THREE.Vector3(0, 1, 0)
        .applyQuaternion(bone.getWorldQuaternion(new THREE.Quaternion())).normalize(),
    };
  }

  _garmentContext() {
    if (!this.model || !this.bones.Hips) return null;
    this.model.updateMatrixWorld(true);
    const hips = this._boneWorld('Hips');
    const neck = this._boneWorld('Neck');
    const head = this._boneWorld('Head');
    const chestBone = this.bones.Spine2 || this.bones.Spine1 || this.bones.Spine;
    const chest = chestBone ? {
      pos: chestBone.getWorldPosition(new THREE.Vector3()),
      dir: new THREE.Vector3(0, 1, 0)
        .applyQuaternion(chestBone.getWorldQuaternion(new THREE.Quaternion())).normalize(),
    } : neck;
    const leftArm = this._boneWorld('LeftArm') || this._boneWorld('LeftShoulder');
    const rightArm = this._boneWorld('RightArm') || this._boneWorld('RightShoulder');
    const leftLeg = this._boneWorld('LeftUpLeg');
    const rightLeg = this._boneWorld('RightUpLeg');
    if (!hips || !neck || !head || !chest) return null;
    const right = leftArm && rightArm
      ? leftArm.pos.clone().sub(rightArm.pos).normalize()
      : new THREE.Vector3(1, 0, 0);
    const up = neck.pos.clone().sub(hips.pos).normalize();
    const forward = right.clone().cross(up).normalize();
    if (!Number.isFinite(forward.x) || forward.lengthSq() < .5) forward.set(0, 0, 1);
    const width = leftArm && rightArm ? leftArm.pos.distanceTo(rightArm.pos) : 0.24;
    const torsoHeight = hips.pos.distanceTo(neck.pos);
    const hipWidth = leftLeg && rightLeg
      ? leftLeg.pos.distanceTo(rightLeg.pos) : width * 0.75;
    const headSize = this.headFrame ? this.headFrame.size : new THREE.Vector3(.18, .26, .22);
    return {
      color: color(this.config.accessoryColor, '#101820'),
      glow: color(this.config.robotGlow, '#00e5ff'),
      length: num(this.config.garmentLength, .6),
      intensity: num(this.config.robotIntensity, 1),
      robot: this.config.robot === true,
      torso: { width, height: torsoHeight, depth: Math.max(.08, width * .55) },
      hips: { pos: hips.pos, width: Math.max(.12, hipWidth), depth: Math.max(.08, hipWidth * .6),
        up, forward, right },
      chest: { pos: chest.pos, height: torsoHeight * .45,
        depth: Math.max(.08, width * .5), up, forward, right },
      neck,
      head: { center: this.headFrame ? this.headFrame.center : head.pos,
        width: headSize.x, height: headSize.y, depth: headSize.z,
        up: new THREE.Vector3(0, 1, 0), right: new THREE.Vector3(1, 0, 0),
        forward: new THREE.Vector3(0, 0, 1) },
      shoulders: { left: this._boneWorld('LeftShoulder') || leftArm,
        right: this._boneWorld('RightShoulder') || rightArm },
      forearms: { left: this._boneWorld('LeftForeArm'), right: this._boneWorld('RightForeArm') },
      thighs: { left: leftLeg, right: rightLeg },
    };
  }

  _applyAccessory() {
    const shape = [this.config.height, this.config.build, this.config.shoulderWidth,
      this.config.hipWidth, this.config.headSize, this.config.headWidth,
      this.config.neckLength, this.config.armLength, this.config.legLength].join(',');
    const key = [this.config.accessory, this.config.accessoryColor,
      this.config.garmentLength, this.config.robot, this.config.robotGlow,
      this.config.robotIntensity, shape].join('|');
    if (key === this._accessoryKey) return;
    this._disposeAccessory();
    this._accessoryKey = key;
    const id = ACCESSORY_STYLES[this.config.accessory] ? this.config.accessory : 'none';
    if (id === 'none' && this.config.robot !== true) return;
    const ctx = this._garmentContext();
    if (!ctx) return;
    for (const { bone, object } of buildAccessory(id, ctx)) {
      const target = this.bones[bone];
      if (!target) { disposeTree(object); continue; }
      this._attachToBone(object, target);
      this.accessoryParts.push(object);
    }
  }

  _disposeAccessory() {
    for (const object of this.accessoryParts) {
      if (object.parent) object.parent.remove(object);
      disposeTree(object);
    }
    this.accessoryParts = [];
  }

  _applyRobotSkin() {
    const robot = this.config.robot === true;
    const glow = color(this.config.robotGlow, '#00e5ff');
    const intensity = num(this.config.robotIntensity, 1);
    for (const kind of ['body', 'head']) {
      for (const mesh of this._meshesFor(kind)) {
        for (const mat of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
          if (!mat) continue;
          if (mat.userData.__basePhys === undefined) {
            mat.userData.__basePhys = {
              metalness: mat.metalness, roughness: mat.roughness,
            };
          }
          if (robot) {
            mat.metalness = .8;
            mat.roughness = .24;
            if (mat.emissive) {
              mat.emissive.set(glow);
              mat.emissiveIntensity = .06 * intensity;
            }
          } else {
            mat.metalness = mat.userData.__basePhys.metalness;
            mat.roughness = mat.userData.__basePhys.roughness;
            if (mat.emissive) {
              mat.emissive.set('#000000');
              mat.emissiveIntensity = 0;
            }
          }
          mat.needsUpdate = true;
        }
      }
    }
    for (const mesh of this._meshesFor('eyes')) {
      for (const mat of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
        if (!mat || !mat.emissive) continue;
        if (robot) {
          mat.emissive.set(glow);
          mat.emissiveIntensity = .8 * intensity;
        } else {
          mat.emissive.set('#000000');
          mat.emissiveIntensity = 0;
        }
        mat.needsUpdate = true;
      }
    }
  }


  async loadIdle() {
    if (!this.config.idle) return;
    try {
      const gltf = await new GLTFLoader().loadAsync(cacheBust(this.config.idle));
      if (!gltf.animations || !gltf.animations.length) return;
      const clip = gltf.animations[0];
      // The idle is a rotation-only base layer. Position tracks would move the
      // rig to the idle GLB's own rest height, and scale tracks would overwrite
      // the body-shape bone scales every frame; both are owned here instead.
      clip.tracks = clip.tracks.filter((track) => track.name.endsWith('.quaternion'));
      this.mixer = new THREE.AnimationMixer(this.model);
      const action = this.mixer.clipAction(clip);
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
    const cfg = this.config;
    const h = num(cfg.height, 1);
    const b = num(cfg.build, 1);
    const sizeY = this.modelSize.y * h;
    const cx = this.modelCenter.x * b;
    const cy = this.modelCenter.y * h;
    const cz = this.modelCenter.z * b;
    const views = {
      full: { dist: Math.max(3.15, sizeY * 1.8), look: cy, yaw: 0, abs: false },
      bust: { dist: Math.max(1.55, sizeY * 0.88), look: cy + sizeY * 0.26, yaw: 0, abs: false },
      head: { dist: 0.75, look: cy + sizeY * 0.32, yaw: 0, abs: true },
      face: { dist: 0.55, look: cy + sizeY * 0.34, yaw: 0, abs: true },
      profile: { dist: 0.8, look: cy + sizeY * 0.32, yaw: 38, abs: true },
      hero: { dist: Math.max(1.45, sizeY * 0.95), look: cy + sizeY * 0.26, yaw: -18, abs: false },
      cinematic: { dist: Math.max(2.6, sizeY * 1.4), look: cy + sizeY * 0.1, yaw: 22, abs: false },
    };
    const v = views[view] || views.bust;
    const yaw = (v.yaw + num(cfg.cameraYaw, 0)) * Math.PI / 180;
    const dist = v.dist * num(cfg.cameraDistance, 1) * (v.abs ? h : 1);
    const lookY = v.look + num(cfg.cameraHeight, 0) * sizeY;
    this.cameraBase = {
      x: cx + Math.sin(yaw) * dist,
      y: lookY + sizeY * 0.03,
      z: cz + Math.cos(yaw) * dist,
      lx: cx, ly: lookY, lz: cz,
      cx, cz, yaw, dist,
    };
    this.camera.position.set(this.cameraBase.x, this.cameraBase.y, this.cameraBase.z);
    this.camera.lookAt(cx, lookY, cz);
    this.camera.fov = num(cfg.cameraFov, 32);
    this.camera.updateProjectionMatrix();
    this.resize();
  }

  resize() {
    if (!this.renderer || !this.camera) return;
    const parent = this.canvas.parentElement;
    const w = Math.max(64, parent ? parent.clientWidth : window.innerWidth);
    const h = Math.max(64, parent ? parent.clientHeight : window.innerHeight);
    const want = num(this.config.pixelRatio, 0);
    const base = want > 0 ? Math.min(3, want) : Math.min(window.devicePixelRatio || 1, 2);
    // qualityScale is the adaptive knob: balanced starts at .75 and the loop
    // lowers it further when frames run long. It must actually scale the
    // backing store or the auto-degrade does nothing.
    const dpr = Math.max(.5, Math.min(3, base * (this.qualityScale || 1)));
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  applyConfig(cfg) {
    this.config = { ...this.config, ...cfg };
    if (!this.model) return;
    this._applyWardrobe();
    this._applyColors();
    this._applyShape();
    this._applyAccessory();
    this._applyRobotSkin();
    this._applyLighting();
    this._applyBackground();
    this.setMood(this.config.mood || this.mood);
    this.setCamera(this.config.camera || 'bust');
    this._applyQuality();
    if (this.mixer) this.mixer.timeScale = num(this.config.idleSpeed, 1);
    document.body.classList.toggle('avatar-hair-off',
      this.config.hair === false || this.config.hairStyle === 'none');
    document.body.classList.toggle('avatar-disabled', this.config.enabled === false);
  }

  _meshesFor(kind) {
    const out = [];
    const pats = MESH_NAMES[kind] || [];
    if (!this.model || !pats.length) return out;
    this.model.traverse((o) => {
      if (!(o.isMesh || o.isSkinnedMesh) || !o.material) return;
      if (pats.some((re) => re.test(o.name))) out.push(o);
    });
    return out;
  }

  _setVisible(kind, on) {
    for (const m of this._meshesFor(kind)) m.visible = !!on;
  }

  /* This GLB only skins the torso in Wolf3D_Body: the arms live in the top
   * mesh, the legs in the bottom mesh and the feet in the footwear mesh.
   * Hiding a layer would delete limbs, so "off" means bare skin: the mesh
   * stays, but its fabric map is dropped and the surface takes the skin tone. */
  _setBare(mesh, bare) {
    if (!mesh.userData.__clothed) mesh.userData.__clothed = mesh.material;
    if (!bare) {
      mesh.material = mesh.userData.__clothed;
      mesh.needsUpdate = true;
      return;
    }
    if (!mesh.userData.__bare) {
      const source = mesh.userData.__clothed;
      const clone = (m) => {
        const copy = m.clone();
        if ('map' in copy) copy.map = null;
        if (copy.emissive) copy.emissive.set('#000000');
        copy.roughness = 0.62;
        copy.metalness = 0;
        copy.needsUpdate = true;
        return copy;
      };
      mesh.userData.__bare = Array.isArray(source) ? source.map(clone) : clone(source);
    }
    mesh.material = mesh.userData.__bare;
    mesh.needsUpdate = true;
  }

  _applyWardrobe() {
    this._applyHair();
    this._setVisible('glasses', this.config.glasses === true);
    for (const kind of ['top', 'bottom', 'footwear']) {
      const on = this.config[kind] !== false;
      this._setVisible(kind, true);
      for (const m of this._meshesFor(kind)) this._setBare(m, !on);
    }
    if (this.config.top === false) return;
    const style = TOP_STYLES[this.config.topStyle];
    const roughness = num(this.config.topRoughness, style ? style.roughness : 0.8);
    const metalness = num(this.config.topMetalness, style ? style.metalness : 0);
    for (const m of this._meshesFor('top'))
      this._setMaterial(m, { roughness, metalness });
  }

  _tintKind(kind, value, blend = 1) {
    if (!value) return;
    for (const m of this._meshesFor(kind)) this.tintMesh(m, value, blend);
  }

  _applyColors() {
    const cfg = this.config;
    const skin = cfg.skinTone;
    for (const m of this.hairMeshes) this.tintMesh(m, cfg.hairColor);
    this._tintKind('glasses', cfg.glassesColor);
    this._tintKind('top', cfg.top === false ? skin : cfg.topColor);
    this._tintKind('bottom', cfg.bottom === false ? skin : cfg.bottomColor);
    this._tintKind('footwear', cfg.footwear === false ? skin : cfg.footwearColor);
    this._tintKind('body', skin);
    this._tintKind('head', skin);
    this._tintKind('eyes', cfg.eyeColor, 0.55);
  }

  _applyShape() {
    const cfg = this.config;
    const h = num(cfg.height, 1);
    const b = num(cfg.build, 1);
    if (this._baseModelScale) {
      this.model.scale.set(this._baseModelScale.x * b, this._baseModelScale.y * h,
        this._baseModelScale.z * b);
    }
    if (this._baseBoneScale) {
      for (const [bone, scale] of this._baseBoneScale) bone.scale.copy(scale);
    }
    const scaleBone = (names, x, y, z) => {
      for (const name of names) {
        const bone = this.bones[name];
        if (bone) bone.scale.set(bone.scale.x * x, bone.scale.y * y, bone.scale.z * z);
      }
    };
    const head = num(cfg.headSize, 1);
    const headW = num(cfg.headWidth, 1);
    scaleBone(SHAPE_BONES.head, head * headW, head, head * headW);
    scaleBone(SHAPE_BONES.neck, 1, num(cfg.neckLength, 1), 1);
    const eye = num(cfg.eyeSize, 1);
    scaleBone(SHAPE_BONES.eyes, eye, eye, eye);
    const arm = num(cfg.armLength, 1);
    scaleBone(SHAPE_BONES.arm, 1, arm, 1);
    scaleBone(SHAPE_BONES.forearm, 1, arm, 1);
    const leg = num(cfg.legLength, 1);
    scaleBone(SHAPE_BONES.upperLeg, 1, leg, 1);
    scaleBone(SHAPE_BONES.leg, 1, leg, 1);
    const shoulder = num(cfg.shoulderWidth, 1);
    scaleBone(SHAPE_BONES.shoulder, shoulder, 1, shoulder);
    const hip = num(cfg.hipWidth, 1);
    scaleBone(SHAPE_BONES.hips, hip, 1, hip);
    if (hip !== 1) {
      // Hips scale propagates to the whole spine; undo it above the pelvis.
      scaleBone(['Spine'], 1 / hip, 1, 1 / hip);
    }
    const hand = num(cfg.handSize, 1);
    scaleBone(SHAPE_BONES.hand, hand, hand, hand);
    const foot = num(cfg.footSize, 1);
    scaleBone(SHAPE_BONES.foot, foot, foot, foot);
    if (this._baseHairScale) {
      const hs = num(cfg.hairScale, 1);
      const hv = num(cfg.hairVolume, 1);
      for (const [mesh, scale] of this._baseHairScale)
        mesh.scale.set(scale.x * hv, scale.y * hs, scale.z * hv);
    }
  }

  _applyLighting() {
    const cfg = this.config;
    const L = this.lights;
    const set = (light, value, intensity) => {
      if (!light) return;
      if (value) light.color.set(color(value, '#' + light.color.getHexString()));
      if (intensity !== undefined) light.intensity = num(intensity, light.intensity);
    };
    if (L) {
      set(L.hemi, cfg.ambientColor, cfg.ambientIntensity);
      set(L.key, cfg.keyColor, cfg.keyIntensity);
      set(L.rim, cfg.rimColor, cfg.rimIntensity);
      set(L.fill, cfg.fillColor, cfg.fillIntensity);
    }
    if (this.renderer) this.renderer.toneMappingExposure = num(cfg.exposure, 1.05);
    const env = num(cfg.envIntensity, 1);
    if (this.scene && 'environmentIntensity' in this.scene) this.scene.environmentIntensity = env;
    if (this.model) {
      this.model.traverse((o) => {
        if (!o.material) return;
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          if (m && m.envMapIntensity !== undefined) m.envMapIntensity = 0.65 * env;
        }
      });
    }
  }

  _applyBackground() {
    const cfg = this.config;
    const mode = cfg.background || 'transparent';
    const hex = color(cfg.backgroundColor, '#050b14');
    if (mode === 'gradient') {
      const key = 'grad:' + hex;
      if (this._bgKey !== key) {
        this._setBackground(this._gradientTexture(cfg.backgroundColor));
        this._bgKey = key;
      }
      return;
    }
    const key = mode === 'dark' ? 'dark' : mode === 'studio' ? 'studio'
      : mode === 'color' ? 'color:' + hex : 'none';
    if (key === this._bgKey) return;
    const value = key === 'dark' ? new THREE.Color('#050b14')
      : key === 'studio' ? new THREE.Color('#0a1a2c')
      : key === 'none' ? null : new THREE.Color(hex);
    this._setBackground(value);
    this._bgKey = key;
  }

  /* Replacing a gradient background must dispose the old canvas texture or
   * dragging the colour picker leaks a texture per input event. */
  _setBackground(value) {
    const previous = this.scene.background;
    if (previous && previous.isTexture && previous !== value) previous.dispose();
    this.scene.background = value;
  }

  _gradientTexture(hex) {
    const canvas = document.createElement('canvas');
    canvas.width = 4;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, 256);
    grad.addColorStop(0, color(hex, '#050b14'));
    grad.addColorStop(1, '#02060b');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 4, 256);
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  _applyQuality() {
    const cfg = this.config;
    const q = cfg.quality || 'high';
    this.qualityScale = q === 'balanced' ? .75 : q === 'high' ? 1 : 1.25;
    this._qualityTarget = this.qualityScale;
    this._slowFrames = 0;
    const shadows = cfg.shadows !== false && q !== 'balanced';
    if (this.renderer) this.renderer.shadowMap.enabled = shadows;
    if (this.lights && this.lights.key) this.lights.key.castShadow = shadows;
    this.resize();
  }

  _setMaterial(mesh, props) {
    for (const m of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (!m) continue;
      if (props.roughness !== undefined && 'roughness' in m) m.roughness = props.roughness;
      if (props.metalness !== undefined && 'metalness' in m) m.metalness = props.metalness;
      m.needsUpdate = true;
    }
  }

  tint(name, value, blend = 1) {
    const o = this.model && this.model.getObjectByName(name);
    if (o) this.tintMesh(o, value, blend);
  }

  tintMesh(o, value, blend = 1) {
    if (!o || !value) return;
    const target = new THREE.Color(value);
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      if (!m || !m.color) continue;
      if (m.userData.__baseColor === undefined) m.userData.__baseColor = m.color.clone();
      const base = m.userData.__baseColor || m.color.clone();
      if (blend >= 1) m.color.copy(target);
      else m.color.copy(base).lerp(target, blend);
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
    if (!this.ready) return false;
    const id = resolveAction(name);
    if (!id) return false;
    this.held = null;
    const now = performance.now() / 1000;
    const speed = Math.max(.1, num(this.config.actionSpeed, 1));
    if (this.action) {
      this.fade = { pose: this.lastPose || {}, start: now, dur: .14 };
    }
    this.action = {
      def: ACTIONS[id],
      name: id,
      start: now,
      dur: Math.max(.25, ACTIONS[id].dur / speed),
    };
    return true;
  }

  playAction(name) {
    return this.playGesture(name);
  }

  /* Freeze one action at a normalized time; used by the settings preview and
   * `?pose=<name>&at=<0..1>` links. */
  holdAction(name, p = .5) {
    const id = resolveAction(name);
    if (!id) return false;
    this.held = { def: ACTIONS[id], p: clamp(Number(p) || 0, 0, 1) };
    return true;
  }

  releaseAction() {
    this.held = null;
    this.action = null;
    this.fade = null;
  }

  setLook(look) {
    this.look = look && LOOKS[look] !== undefined ? look : null;
  }

  configure(patch, save = true) {
    let next = patch || {};
    const keys = Object.keys(next);
    const bundle = PRESETS.character[next.character];
    if (keys.length === 1 && bundle) {
      const { label, note, ...rest } = bundle;
      next = { ...rest, character: next.character };
    }
    this.applyConfig(next);
    if (save) this.saveConfig();
  }

  getConfig() {
    return { ...this.config };
  }

  resetConfig(save = true) {
    this.configure({ ...DEFAULTS }, save);
  }

  /* Apply a named preset group: character / outfit / camera / light / mood. */
  applyPreset(kind, name, save = true) {
    const group = PRESETS[kind];
    if (!group || !group[name]) return false;
    const { label, note, ...bundle } = group[name];
    this.configure({ ...bundle, [kind]: name }, save);
    return true;
  }

  randomizeConfig(save = true) {
    const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
    const rand = (lo, hi) => lo + Math.random() * (hi - lo);
    const characters = Object.keys(PRESETS.character);
    const character = pick(characters);
    const { label, note, ...bundle } = PRESETS.character[character];
    const outfits = Object.keys(OUTFIT_PRESETS).filter((id) => id !== 'body');
    const outfit = pick(outfits);
    const light = pick(Object.keys(LIGHT_PRESETS));
    const camera = pick(Object.keys(CAMERA_PRESETS));
    const hairLook = pick(Object.keys(HAIR_LOOKS));
    const bodyShape = pick(Object.keys(BODY_SHAPES));
    const accessories = Object.keys(ACCESSORY_STYLES);
    const hairStyles = this.hairStyles().filter((s) => s.id !== 'none');
    const patch = {
      ...bundle,
      character,
      ...OUTFIT_PRESETS[outfit], outfit,
      ...LIGHT_PRESETS[light], light,
      ...CAMERA_PRESETS[camera], camera,
      ...HAIR_LOOKS[hairLook], hairLook,
      ...BODY_SHAPES[bodyShape], bodyShape,
      hairColor: pick(HAIR_COLORS),
      skinTone: pick(SKIN_TONES),
      eyeColor: pick(EYE_COLORS),
      hairStyle: hairStyles.length ? pick(hairStyles).id : 'default',
      accessory: pick(accessories),
      headSize: rand(0.93, 1.07),
      cameraDistance: rand(0.88, 1.12),
    };
    this.configure(patch, save);
    return this.getConfig();
  }

  importConfig(data, save = true) {
    if (!data || typeof data !== 'object') return false;
    const patch = {};
    for (const key of Object.keys(DEFAULTS)) {
      if (data[key] !== undefined) patch[key] = data[key];
    }
    if (!Object.keys(patch).length) return false;
    this.configure(patch, save);
    return true;
  }

  exportConfig() {
    return JSON.stringify(this.getConfig(), null, 2);
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

  _actionPose(now) {
    if (this.held) return samplePose(this.held.def, this.held.p);
    let pose = {};
    if (this.action) {
      const p = (now - this.action.start) / this.action.dur;
      pose = samplePose(this.action.def, p);
      if (p >= 1) { this.action = null; this.fade = null; }
    }
    if (this.fade) {
      const w = clamp((now - this.fade.start) / this.fade.dur);
      if (w >= 1) this.fade = null;
      else pose = mixPose(this.fade.pose, pose, w);
    }
    this.lastPose = pose;
    return pose;
  }

  /* Apply world-axis deltas on top of the mixer pose, parents first. The world
   * quats/scales are preallocated per bone so the render loop does not allocate
   * two objects per bone per frame (which showed up as GC stutter). */
  _applyPose(pose) {
    if (!this._orderedBones || !this.model) return;
    const worldQ = this._worldQuat;
    const worldS = this._worldScale;
    for (const entry of this._orderedBones) {
      const bone = entry.bone;
      const parentQ = entry.parentBone
        ? (worldQ.get(entry.parentBone) || entry.ancestorQuat)
        : entry.ancestorQuat;
      const parentS = entry.parentBone
        ? (worldS.get(entry.parentBone) || entry.ancestorScale)
        : this._tmpS.copy(entry.ancestorScale).multiply(this.model.scale);
      const delta = pose[bone.name];
      if (delta) {
        this._tmpQ.copy(parentQ).invert();
        for (const [axis, worldAxis] of AXES) {
          const angle = delta[axis] || 0;
          if (!angle) continue;
          this._tmpV.copy(worldAxis).applyQuaternion(this._tmpQ).normalize();
          this._tmpQ2.setFromAxisAngle(this._tmpV, angle);
          bone.quaternion.premultiply(this._tmpQ2);
        }
        if (delta.tx || delta.ty || delta.tz) {
          this._tmpV.set(delta.tx || 0, delta.ty || 0, delta.tz || 0)
            .applyQuaternion(this._tmpQ);
          this._tmpV.divide(parentS);
          bone.position.add(this._tmpV);
        }
      }
      const wq = worldQ.get(bone);
      if (wq) wq.copy(parentQ).multiply(bone.quaternion);
      const ws = worldS.get(bone);
      if (ws) ws.copy(parentS).multiply(bone.scale);
    }
  }

  update(dt, now) {
    if (!this.ready) return;
    const cfg = this.config;
    this._restoreBase();
    if (this.mixer) {
      this.mixer.timeScale = num(cfg.idleSpeed, 1);
      this.mixer.update(dt);
    }
    this._cacheBase();
    const t = now;

    // blinking: Poisson-ish gaps, plus a double blink sometimes
    const blinkSpeed = Math.max(.1, num(cfg.blinkSpeed, 1));
    if (cfg.autoBlink !== false && t > this.nextBlink && t > this.blinkUntil + .2) {
      this.blinkUntil = t + .11;
      this.nextBlink = t + (2.2 + Math.random() * 4.8) / blinkSpeed;
      if (Math.random() < .18) this.nextBlink = t + .28 / blinkSpeed;
    }
    const blink = cfg.autoBlink === false ? 0 : (t < this.blinkUntil ? 1 : 0);

    // gaze target: pointer while listening/speaking; away while thinking/tool,
    // unless the sentence carried an explicit [look:…] tag
    const follow = num(cfg.gazeFollow, 1);
    const think = this.state === 'thinking' || this.state === 'tool';
    let targetX = think ? (this.state === 'tool' ? .35 : -.25) : this.pointer.x * .22 * follow;
    let targetY = think ? (this.state === 'tool' ? -.1 : .18) : -this.pointer.y * .12 * follow;
    const look = this.look ? LOOKS[this.look] : null;
    if (Array.isArray(look)) { targetX = look[0]; targetY = look[1]; }
    else if (look === 'camera') { targetX = 0; targetY = 0; }
    else if (look === 'away') { targetX = -.4; targetY = .12; }
    this.gazeX = lerp(this.gazeX || 0, targetX, 1 - Math.pow(.001, dt));
    this.gazeY = lerp(this.gazeY || 0, targetY, 1 - Math.pow(.001, dt));

    const pose = {};
    const swayAmount = num(cfg.swayAmount, 1);
    const sway = (Math.sin(t * .6) * .012 +
      (this.state === 'speaking' ? Math.sin(t * 3.1) * .008 : 0)) * swayAmount;
    pose.Head = {
      y: this.gazeX,
      x: this.gazeY * .6 + sway,
      z: Math.sin(t * .35) * .01 * swayAmount,
    };
    const breathAmount = num(cfg.breathAmount, 1);
    const breath = Math.sin(t * 1.25) * .012 * breathAmount;
    pose.Spine2 = { x: breath };
    addPose(pose, this._actionPose(now), num(cfg.gestureAmount, 1));
    this._applyPose(pose);
    const chest = this.bones.Spine2 || this.bones.Spine1 || this.bones.Spine;
    if (chest) chest.scale.y = 1 + Math.sin(t * 1.25) * .006 * breathAmount;

    if (this.camera && this.cameraBase) {
      const parallax = num(cfg.cameraParallax, 1);
      const orbit = cfg.autoOrbit ? Math.sin(t * .3) * .4 : 0;
      const dx = this.cameraBase.x - this.cameraBase.cx;
      const dz = this.cameraBase.z - this.cameraBase.cz;
      const cos = Math.cos(orbit);
      const sin = Math.sin(orbit);
      this.camera.position.x = this.cameraBase.cx + dx * cos - dz * sin + this.pointer.x * .05 * parallax;
      this.camera.position.y = this.cameraBase.y - this.pointer.y * .03 * parallax;
      this.camera.position.z = this.cameraBase.cz + dx * sin + dz * cos;
      this.camera.lookAt(this.cameraBase.lx, this.cameraBase.ly, this.cameraBase.lz);
    }

    const desired = this._desired;
    desired.clear();
    const mood = MOODS[this.mood] || MOODS.neutral;
    for (const k in mood) desired.set(k, mood[k]);
    const add = (name, value) => desired.set(name, clamp((desired.get(name) || 0) + value));
    const smile = num(cfg.smile, 0);
    if (smile) {
      add('mouthSmileLeft', smile); add('mouthSmileRight', smile);
      add('cheekSquintLeft', smile * .4); add('cheekSquintRight', smile * .4);
    }
    const brow = num(cfg.browRaise, 0);
    if (brow) {
      add('browInnerUp', brow);
      add('browOuterUpLeft', brow * .8); add('browOuterUpRight', brow * .8);
    }
    const wide = num(cfg.eyeWide, 0);
    if (wide) { add('eyeWideLeft', wide); add('eyeWideRight', wide); }
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
    const targets = this._morphTargets.get(name);
    if (!targets) return;
    const v = clamp(value);
    for (const target of targets) {
      if (target.mesh.morphTargetInfluences) {
        target.mesh.morphTargetInfluences[target.idx] = v;
      }
    }
  }

  loop() {
    if (!this.ready) return;
    requestAnimationFrame(() => this.loop());
    if (document.hidden) return;
    if (this.config.enabled === false && !this.forcePreview) return;
    const cap = num(this.config.fpsCap, 0);
    const stamp = performance.now();
    if (cap > 0 && stamp - (this._lastRender || 0) < 1000 / cap) return;
    this._lastRender = stamp;
    const dt = Math.min(.05, this.clock.getDelta());
    this.frameTime = lerp(this.frameTime, dt * 1000, .05);
    // Adaptive resolution: require several slow frames in a row so a single GC
    // pause does not drop quality, then recover slowly when the GPU is idle.
    if (this.frameTime > 30) this._slowFrames = (this._slowFrames || 0) + 1;
    else this._slowFrames = 0;
    const target = this._qualityTarget || 1;
    const canChange = stamp - (this._lastQualityChange || 0) > 400;
    if (this._slowFrames > 6 && this.qualityScale > .55 && canChange) {
      this.qualityScale = Math.max(.55, this.qualityScale - .05);
      this._slowFrames = 0;
      this._lastQualityChange = stamp;
      this.resize();
    } else if (this.frameTime < 18 && this.qualityScale < target && canChange) {
      this.qualityScale = Math.min(target, this.qualityScale + .02);
      this._lastQualityChange = stamp;
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

export {
  MiaAvatar, textTimeline, DEFAULTS, GESTURES, ACTIONS, LOOKS, MOODS,
  PRESETS, HAIR_STYLES, ACCESSORY_STYLES,
};
