/* Mia avatar — defaults, presets and the settings schema.
 *
 * `avatar.js` (runtime) and `avatar.html` (control deck) share this module so
 * a setting can never exist in one place and be missing in the other. The
 * Python side mirrors `DEFAULTS` in `server/avatar_config.py`; a test keeps
 * the two lists identical.
 */

import { CHARACTERS } from './characters.js';

export const DEFAULTS = {
  enabled: true,
  model: '/hud/avatar/models/mia-female.glb',
  idle: '/hud/avatar/models/mia-female-idle.glb',

  // character
  character: 'mia',

  // wardrobe
  outfit: 'casual',
  top: true, bottom: true, footwear: true, glasses: false,
  topStyle: 'casual',
  topColor: '#1d3f52', bottomColor: '#101820', footwearColor: '#101820',
  glassesColor: '#101820', topRoughness: 0.85, topMetalness: 0.02,
  accessory: 'collar', accessoryColor: '#cfeefb', garmentLength: 0.6,
  robot: false, robotGlow: '#00e5ff', robotIntensity: 1.0,

  // hair and skin
  hair: true, hairStyle: 'long', hairLook: 'natural',
  hairColor: '#3b2418', hairScale: 1, hairVolume: 1,
  skinTone: '#f2d2bd', eyeColor: '#2f6f8f',

  // body and head shape
  bodyShape: 'natural',
  height: 1, build: 1, headSize: 1, headWidth: 1, neckLength: 1,
  eyeSize: 1, armLength: 1, legLength: 1,
  shoulderWidth: 1, hipWidth: 1, handSize: 1, footSize: 1,

  // face and expression
  mood: 'warm', smile: 0.16, browRaise: 0, eyeWide: 0,

  // behaviour
  autoBlink: true, blinkSpeed: 1, breathAmount: 1, swayAmount: 1,
  gazeFollow: 1, idleSpeed: 1, gestureAmount: 1, actionSpeed: 1,

  // camera
  camera: 'bust', cameraDistance: 1, cameraHeight: 0, cameraYaw: 0,
  cameraFov: 32, cameraParallax: 1, autoOrbit: false,

  // lighting
  light: 'studio', exposure: 1.05, envIntensity: 1,
  keyColor: '#ffe4c8', keyIntensity: 3.2,
  rimColor: '#00e5ff', rimIntensity: 2.4,
  fillColor: '#19f0d8', fillIntensity: 2.2,
  ambientColor: '#9fd8e8', ambientIntensity: 1.5,

  // scene and render
  background: 'transparent', backgroundColor: '#050b14',
  quality: 'high', shadows: true, fpsCap: 0, pixelRatio: 0,
};

export const HAIR_COLORS = [
  '#1b1410', '#3b2418', '#5a3825', '#7b4b2a', '#a56b3d', '#c98f5a',
  '#d9b380', '#e8d3a8', '#b8b8b8', '#e8e8e8', '#7a2e2e', '#3a2a55',
];

export const SKIN_TONES = [
  '#f7e0d0', '#f2d2bd', '#e8bfa3', '#d9a67f', '#c98a62', '#b06f48',
  '#8f5434', '#6e3d24', '#4f2a18', '#33200f',
];

export const EYE_COLORS = [
  '#3b2a1a', '#5a3d24', '#7a5a32', '#4f6b3a', '#2f6b5a', '#2f6f8f',
  '#4a7d9c', '#6d8fa8', '#8a8a8a', '#2a2a2a',
];

export const GARMENT_COLORS = [
  '#1d3f52', '#101820', '#e8eef2', '#22303f', '#7a3b2e', '#2a1633',
  '#0f6b7a', '#04262e', '#00e5ff', '#ffb300', '#ff4d5e', '#2a2a2a',
];

export const TOP_STYLES = {
  casual: { label: 'vsakdanji', roughness: 0.85, metalness: 0.02 },
  business: { label: 'poslovni', roughness: 0.45, metalness: 0.08 },
  sport: { label: 'športni', roughness: 0.7, metalness: 0.05 },
  evening: { label: 'večerni', roughness: 0.25, metalness: 0.35 },
  cyber: { label: 'cyber', roughness: 0.35, metalness: 0.55 },
  soft: { label: 'mehak', roughness: 0.95, metalness: 0.0 },
};

/* Hair variants reshape the mesh the model ships with; they are not new
 * geometry, so they work for any RPM/Avaturn hair mesh. */
export const HAIR_LOOKS = {
  natural: { label: 'naravna', hairScale: 1, hairVolume: 1 },
  long: { label: 'dolga', hairScale: 1.28, hairVolume: 1.06 },
  short: { label: 'kratka', hairScale: 0.78, hairVolume: 0.96 },
  volume: { label: 'volumna', hairScale: 1.02, hairVolume: 1.38 },
  sleek: { label: 'gladka', hairScale: 1.1, hairVolume: 0.8 },
  wild: { label: 'divja', hairScale: 1.18, hairVolume: 1.2 },
};

/* Procedural wigs built by `hair.js`; used when the GLB only has one hair
 * mesh (the free RPM model) or when the user wants a different silhouette. */
export const HAIR_STYLES = {
  long: { label: 'dolga (do prsi)', length: 2.5, locks: 16, volume: 1.08, fringe: true },
  short: { label: 'kratka', length: 0.62, locks: 10, volume: 0.95, fringe: false },
  bob: { label: 'bob (do čeljusti)', length: 1.08, locks: 14, volume: 1.02, fringe: true },
  pixie: { label: 'pixie', length: 0.3, locks: 6, volume: 0.9, fringe: false },
  ponytail: { label: 'rep', length: 1.9, locks: 0, volume: 1, fringe: true },
  bun: { label: 'figa', length: 0.4, locks: 0, volume: 1, fringe: false },
  twin: { label: 'dvojni repki', length: 1.7, locks: 0, volume: 1.05, fringe: true },
  braid: { label: 'pletenice', length: 1.5, locks: 0, volume: 1, fringe: false },
  afro: { label: 'afro', length: 0.5, locks: 0, volume: 1.6, fringe: false },
  mohawk: { label: 'mohawk', length: 0.35, locks: 0, volume: 0.8, fringe: false },
};

export const ACCESSORY_STYLES = {
  none: { label: 'brez dodatkov' },
  collar: { label: 'ovratnik' },
  tie: { label: 'kravata' },
  scarf: { label: 'šal' },
  pauldrons: { label: 'naramnice' },
  armor: { label: 'oklep' },
  visor: { label: 'vizir' },
  antenna: { label: 'antena' },
  headset: { label: 'slušalke' },
  belt: { label: 'pas' },
  skirt: { label: 'krilo' },
  dress: { label: 'obleka' },
  thruster: { label: 'potisniki' },
};


export const BODY_SHAPES = {
  natural: { label: 'naravna', height: 1, build: 1, shoulderWidth: 1,
    hipWidth: 1, armLength: 1, legLength: 1 },
  slim: { label: 'vitka', height: 1.02, build: 0.86, shoulderWidth: 0.94,
    hipWidth: 0.9, armLength: 1.0, legLength: 1.04 },
  athletic: { label: 'atletska', height: 1.02, build: 1.12, shoulderWidth: 1.18,
    hipWidth: 1.02, armLength: 1.03, legLength: 1.02 },
  curvy: { label: 'oblina', height: 1, build: 1.1, shoulderWidth: 1.02,
    hipWidth: 1.2, armLength: 1, legLength: 1 },
  petite: { label: 'drobna', height: 0.9, build: 0.9, shoulderWidth: 0.92,
    hipWidth: 0.94, armLength: 0.92, legLength: 0.94 },
  tall: { label: 'visoka', height: 1.16, build: 0.98, shoulderWidth: 1.02,
    hipWidth: 0.98, armLength: 1.08, legLength: 1.08 },
};

export const MOOD_OPTIONS = [
  { value: 'neutral', label: 'nevtralno' },
  { value: 'warm', label: 'toplo' },
  { value: 'happy', label: 'veselo' },
  { value: 'sad', label: 'žalostno' },
  { value: 'angry', label: 'jezno' },
  { value: 'fearful', label: 'prestrašeno' },
  { value: 'disgust', label: 'gnus' },
  { value: 'love', label: 'ljubezen' },
  { value: 'sleep', label: 'spanje' },
];

export const BACKGROUND_OPTIONS = [
  { value: 'transparent', label: 'prosojno (HUD)' },
  { value: 'dark', label: 'temno' },
  { value: 'gradient', label: 'gradient' },
  { value: 'color', label: 'izbrana barva' },
  { value: 'studio', label: 'studio' },
];

export const QUALITY_OPTIONS = [
  { value: 'ultra', label: 'ultra' },
  { value: 'high', label: 'visoka' },
  { value: 'balanced', label: 'varčna' },
];

export const OUTFIT_PRESETS = {
  casual: { topColor: '#1d3f52', bottomColor: '#101820', footwearColor: '#101820',
    glassesColor: '#101820', topStyle: 'casual', topRoughness: 0.85, topMetalness: 0.02 },
  business: { topColor: '#22303f', bottomColor: '#16202a', footwearColor: '#0d141b',
    glassesColor: '#c9d6df', topStyle: 'business', topRoughness: 0.45, topMetalness: 0.08 },
  sport: { topColor: '#0f6b7a', bottomColor: '#16232b', footwearColor: '#e8f4f8',
    glassesColor: '#101820', topStyle: 'sport', topRoughness: 0.7, topMetalness: 0.05 },
  evening: { topColor: '#2a1633', bottomColor: '#120a18', footwearColor: '#0a0a0f',
    glassesColor: '#d4af37', topStyle: 'evening', topRoughness: 0.25, topMetalness: 0.35 },
  cyber: { topColor: '#04262e', bottomColor: '#07161c', footwearColor: '#00e5ff',
    glassesColor: '#00e5ff', topStyle: 'cyber', topRoughness: 0.35, topMetalness: 0.55 },
  minimal: { topColor: '#e8eef2', bottomColor: '#20262c', footwearColor: '#111418',
    glassesColor: '#101820', topStyle: 'soft', topRoughness: 0.95, topMetalness: 0.0 },
  warm: { topColor: '#7a3b2e', bottomColor: '#2a1810', footwearColor: '#1a0f0a',
    glassesColor: '#ffb300', topStyle: 'casual', topRoughness: 0.85, topMetalness: 0.02 },
  mono: { topColor: '#2a2a2a', bottomColor: '#151515', footwearColor: '#0a0a0a',
    glassesColor: '#8a8a8a', topStyle: 'soft', topRoughness: 0.95, topMetalness: 0.0 },
  body: { top: false, bottom: false, footwear: false, glasses: false,
    topStyle: 'soft', topRoughness: 0.9, topMetalness: 0.0 },
  hoodie: { top: true, bottom: true, footwear: true, topColor: '#2f4a5c',
    bottomColor: '#1b2730', footwearColor: '#e8eef2', glassesColor: '#101820',
    topStyle: 'soft', topRoughness: 0.98, topMetalness: 0.0 },
  uniform: { top: true, bottom: true, footwear: true, topColor: '#1b2c4a',
    bottomColor: '#101a2c', footwearColor: '#080b10', glassesColor: '#c9d6df',
    topStyle: 'business', topRoughness: 0.5, topMetalness: 0.06 },
  gala: { top: true, bottom: true, footwear: true, topColor: '#3a1a4d',
    bottomColor: '#1a0c22', footwearColor: '#d4af37', glassesColor: '#d4af37',
    topStyle: 'evening', topRoughness: 0.2, topMetalness: 0.5 },
  techwear: { top: true, bottom: true, footwear: true, topColor: '#182229',
    bottomColor: '#0b1116', footwearColor: '#ffb300', glassesColor: '#ffb300',
    topStyle: 'cyber', topRoughness: 0.4, topMetalness: 0.6 },
  kimono: { top: true, bottom: true, footwear: true, topColor: '#8c2f39',
    bottomColor: '#2a1014', footwearColor: '#e8d3a8', glassesColor: '#101820',
    topStyle: 'soft', topRoughness: 0.9, topMetalness: 0.0 },
  stealth: { top: true, bottom: true, footwear: true, topColor: '#0c1014',
    bottomColor: '#080a0d', footwearColor: '#050608', glassesColor: '#19f0d8',
    topStyle: 'cyber', topRoughness: 0.55, topMetalness: 0.3 },
  pastel: { top: true, bottom: true, footwear: true, topColor: '#d9e8f2',
    bottomColor: '#b7c9d6', footwearColor: '#f2e2e8', glassesColor: '#8a8a8a',
    topStyle: 'soft', topRoughness: 0.95, topMetalness: 0.0 },
};

export const LIGHT_PRESETS = {
  studio: { exposure: 1.05, envIntensity: 1,
    keyColor: '#ffe4c8', keyIntensity: 3.2, rimColor: '#00e5ff', rimIntensity: 2.4,
    fillColor: '#19f0d8', fillIntensity: 2.2, ambientColor: '#9fd8e8', ambientIntensity: 1.5 },
  cyan: { exposure: 1.0, envIntensity: 1.1,
    keyColor: '#bff6ff', keyIntensity: 2.6, rimColor: '#00e5ff', rimIntensity: 3.4,
    fillColor: '#19f0d8', fillIntensity: 2.0, ambientColor: '#6fd8ff', ambientIntensity: 1.4 },
  warm: { exposure: 1.1, envIntensity: 1,
    keyColor: '#ffd2a1', keyIntensity: 3.6, rimColor: '#ff8a4c', rimIntensity: 1.8,
    fillColor: '#ffb300', fillIntensity: 1.6, ambientColor: '#ffd9b0', ambientIntensity: 1.3 },
  cinema: { exposure: 0.95, envIntensity: 0.8,
    keyColor: '#fff1dc', keyIntensity: 2.4, rimColor: '#4c7dff', rimIntensity: 3.0,
    fillColor: '#ff4d5e', fillIntensity: 0.8, ambientColor: '#2a3a4a', ambientIntensity: 0.8 },
  night: { exposure: 0.8, envIntensity: 0.6,
    keyColor: '#7fa8ff', keyIntensity: 1.2, rimColor: '#00e5ff', rimIntensity: 1.8,
    fillColor: '#19f0d8', fillIntensity: 0.6, ambientColor: '#16243a', ambientIntensity: 0.6 },
  soft: { exposure: 1.15, envIntensity: 1.2,
    keyColor: '#fff4e8', keyIntensity: 2.2, rimColor: '#bfe9ff', rimIntensity: 1.2,
    fillColor: '#ffffff', fillIntensity: 1.0, ambientColor: '#dceef7', ambientIntensity: 1.6 },
  neon: { exposure: 1.0, envIntensity: 0.9,
    keyColor: '#ff4dd2', keyIntensity: 2.6, rimColor: '#00e5ff', rimIntensity: 3.6,
    fillColor: '#9d4dff', fillIntensity: 2.4, ambientColor: '#3a2a5a', ambientIntensity: 1.0 },
  flat: { exposure: 1.0, envIntensity: 1.4,
    keyColor: '#ffffff', keyIntensity: 1.8, rimColor: '#ffffff', rimIntensity: 0.4,
    fillColor: '#ffffff', fillIntensity: 0.6, ambientColor: '#ffffff', ambientIntensity: 1.8 },
};

export const CAMERA_PRESETS = {
  bust: { camera: 'bust', cameraDistance: 1, cameraHeight: 0, cameraYaw: 0,
    cameraFov: 32, cameraParallax: 1 },
  head: { camera: 'head', cameraDistance: 1, cameraHeight: 0, cameraYaw: 0,
    cameraFov: 30, cameraParallax: 0.7 },
  face: { camera: 'face', cameraDistance: 1, cameraHeight: 0, cameraYaw: 0,
    cameraFov: 26, cameraParallax: 0.4 },
  full: { camera: 'full', cameraDistance: 1, cameraHeight: 0, cameraYaw: 0,
    cameraFov: 34, cameraParallax: 0.8 },
  profile: { camera: 'profile', cameraDistance: 1.05, cameraHeight: 0, cameraYaw: 0,
    cameraFov: 30, cameraParallax: 0.5 },
  hero: { camera: 'hero', cameraDistance: 0.92, cameraHeight: 0.06, cameraYaw: -16,
    cameraFov: 30, cameraParallax: 1.4 },
  cinematic: { camera: 'cinematic', cameraDistance: 1.15, cameraHeight: 0.1,
    cameraYaw: 22, cameraFov: 28, cameraParallax: 0.9 },
};

export const MOOD_PRESETS = Object.fromEntries(
  MOOD_OPTIONS.map((m) => [m.value, { mood: m.value }]));

export const PRESETS = {
  character: CHARACTERS,
  outfit: OUTFIT_PRESETS,
  camera: CAMERA_PRESETS,
  light: LIGHT_PRESETS,
  mood: MOOD_PRESETS,
  hairLook: HAIR_LOOKS,
  bodyShape: BODY_SHAPES,
};

const opts = (obj) => Object.entries(obj).map(([value, v]) => ({
  value, label: typeof v === 'string' ? v : (v.label || value),
}));

export const SCHEMA = [
  {
    id: 'character', title: 'LIK / OSEBA', preset: 'character',
    controls: [
      { key: 'character', type: 'select', label: 'Ženska', options: opts(CHARACTERS) },
    ],
  },
  {
    id: 'outfit', title: 'OBLEKA IN DODATKI', preset: 'outfit',
    controls: [
      { key: 'top', type: 'toggle', label: 'Zgornji del' },
      { key: 'topColor', type: 'color', label: 'Barva zgornjega dela', palette: GARMENT_COLORS },
      { key: 'topStyle', type: 'select', label: 'Kroj tkanine', options: opts(TOP_STYLES) },
      { key: 'topRoughness', type: 'range', label: 'Hrapavost tkanine', min: 0, max: 1, step: 0.01 },
      { key: 'topMetalness', type: 'range', label: 'Kovinski lesk', min: 0, max: 1, step: 0.01 },
      { key: 'bottom', type: 'toggle', label: 'Spodnji del' },
      { key: 'bottomColor', type: 'color', label: 'Barva spodnjega dela', palette: GARMENT_COLORS },
      { key: 'footwear', type: 'toggle', label: 'Obutev' },
      { key: 'footwearColor', type: 'color', label: 'Barva obutve', palette: GARMENT_COLORS },
      { key: 'glasses', type: 'toggle', label: 'Očala' },
      { key: 'glassesColor', type: 'color', label: 'Barva očal', palette: GARMENT_COLORS },
      { key: 'accessory', type: 'select', label: 'Dodatek / obleka', options: opts(ACCESSORY_STYLES) },
      { key: 'accessoryColor', type: 'color', label: 'Barva dodatka', palette: GARMENT_COLORS },
      { key: 'garmentLength', type: 'range', label: 'Dolžina krila / obleke', min: 0.2, max: 1.2, step: 0.01 },
      { key: 'robot', type: 'toggle', label: 'Robot oklep in žareče linije' },
      { key: 'robotGlow', type: 'color', label: 'Barva žarenja', palette: GARMENT_COLORS },
      { key: 'robotIntensity', type: 'range', label: 'Moč žarenja', min: 0, max: 3, step: 0.05 },
    ],
  },
  {
    id: 'hair', title: 'LASJE, KOŽA IN OČI', preset: 'hairLook',
    controls: [
      { key: 'hair', type: 'toggle', label: 'Lasje' },
      { key: 'hairStyle', type: 'select', label: 'Pričeska', dynamic: 'hairStyles' },
      { key: 'hairColor', type: 'color', label: 'Barva las', palette: HAIR_COLORS },
      { key: 'hairScale', type: 'range', label: 'Dolžina las', min: 0.6, max: 1.4, step: 0.01 },
      { key: 'hairVolume', type: 'range', label: 'Volumen las', min: 0.6, max: 1.5, step: 0.01 },
      { key: 'skinTone', type: 'color', label: 'Odtenek kože', palette: SKIN_TONES },
      { key: 'eyeColor', type: 'color', label: 'Barva oči', palette: EYE_COLORS },
    ],
  },
  {
    id: 'shape', title: 'OBLIKA TELESA IN GLAVE', preset: 'bodyShape',
    controls: [
      { key: 'height', type: 'range', label: 'Višina', min: 0.75, max: 1.35, step: 0.01 },
      { key: 'build', type: 'range', label: 'Postava', min: 0.75, max: 1.4, step: 0.01 },
      { key: 'headSize', type: 'range', label: 'Velikost glave', min: 0.75, max: 1.35, step: 0.01 },
      { key: 'headWidth', type: 'range', label: 'Širina glave', min: 0.8, max: 1.25, step: 0.01 },
      { key: 'neckLength', type: 'range', label: 'Dolžina vratu', min: 0.8, max: 1.3, step: 0.01 },
      { key: 'eyeSize', type: 'range', label: 'Velikost oči', min: 0.7, max: 1.4, step: 0.01 },
      { key: 'armLength', type: 'range', label: 'Dolžina rok', min: 0.85, max: 1.15, step: 0.01 },
      { key: 'legLength', type: 'range', label: 'Dolžina nog', min: 0.85, max: 1.15, step: 0.01 },
      { key: 'shoulderWidth', type: 'range', label: 'Širina ramen', min: 0.8, max: 1.25, step: 0.01 },
      { key: 'hipWidth', type: 'range', label: 'Širina bokov', min: 0.8, max: 1.25, step: 0.01 },
      { key: 'handSize', type: 'range', label: 'Velikost rok', min: 0.8, max: 1.3, step: 0.01 },
      { key: 'footSize', type: 'range', label: 'Velikost stopal', min: 0.8, max: 1.3, step: 0.01 },
    ],
  },
  {
    id: 'face', title: 'OBRAZ IN IZRAZ', preset: 'mood',
    controls: [
      { key: 'mood', type: 'select', label: 'Razpoloženje', options: MOOD_OPTIONS },
      { key: 'smile', type: 'range', label: 'Nasmeh', min: 0, max: 1, step: 0.01 },
      { key: 'browRaise', type: 'range', label: 'Dvignjene obrvi', min: 0, max: 1, step: 0.01 },
      { key: 'eyeWide', type: 'range', label: 'Široke oči', min: 0, max: 1, step: 0.01 },
    ],
  },
  {
    id: 'behaviour', title: 'VEDENJE IN ANIMACIJA',
    controls: [
      { key: 'autoBlink', type: 'toggle', label: 'Samodejno utripanje' },
      { key: 'blinkSpeed', type: 'range', label: 'Hitrost utripanja', min: 0.3, max: 2.5, step: 0.01 },
      { key: 'breathAmount', type: 'range', label: 'Dihanje', min: 0, max: 2, step: 0.01 },
      { key: 'swayAmount', type: 'range', label: 'Zibanje glave', min: 0, max: 2.5, step: 0.01 },
      { key: 'gazeFollow', type: 'range', label: 'Sledenje kazalcu', min: 0, max: 1.5, step: 0.01 },
      { key: 'idleSpeed', type: 'range', label: 'Hitrost idle animacije', min: 0.3, max: 2, step: 0.01 },
      { key: 'gestureAmount', type: 'range', label: 'Moč gest', min: 0, max: 2, step: 0.01 },
      { key: 'actionSpeed', type: 'range', label: 'Hitrost gest in gibov', min: 0.4, max: 2, step: 0.01 },
    ],
  },
  {
    id: 'camera', title: 'KAMERA', preset: 'camera',
    controls: [
      { key: 'cameraDistance', type: 'range', label: 'Oddaljenost', min: 0.6, max: 2.5, step: 0.01 },
      { key: 'cameraHeight', type: 'range', label: 'Višina kamere', min: -0.25, max: 0.35, step: 0.01 },
      { key: 'cameraYaw', type: 'range', label: 'Kot (yaw)', min: -60, max: 60, step: 1, unit: '°' },
      { key: 'cameraFov', type: 'range', label: 'Zorno polje (FOV)', min: 18, max: 60, step: 1, unit: '°' },
      { key: 'cameraParallax', type: 'range', label: 'Paralaksa na kazalec', min: 0, max: 2.5, step: 0.01 },
      { key: 'autoOrbit', type: 'toggle', label: 'Samodejno kroženje kamere' },
    ],
  },
  {
    id: 'light', title: 'LUČI IN VZDUŠJE', preset: 'light',
    controls: [
      { key: 'exposure', type: 'range', label: 'Osvetlitev', min: 0.4, max: 2, step: 0.01 },
      { key: 'envIntensity', type: 'range', label: 'Okoljski odsev', min: 0, max: 2, step: 0.01 },
      { key: 'keyColor', type: 'color', label: 'Ključna luč — barva' },
      { key: 'keyIntensity', type: 'range', label: 'Ključna luč — moč', min: 0, max: 6, step: 0.05 },
      { key: 'rimColor', type: 'color', label: 'Obrobna luč — barva' },
      { key: 'rimIntensity', type: 'range', label: 'Obrobna luč — moč', min: 0, max: 6, step: 0.05 },
      { key: 'fillColor', type: 'color', label: 'Polnilna luč — barva' },
      { key: 'fillIntensity', type: 'range', label: 'Polnilna luč — moč', min: 0, max: 6, step: 0.05 },
      { key: 'ambientColor', type: 'color', label: 'Ambient — barva' },
      { key: 'ambientIntensity', type: 'range', label: 'Ambient — moč', min: 0, max: 4, step: 0.05 },
    ],
  },
  {
    id: 'scene', title: 'OZADJE IN RENDER',
    controls: [
      { key: 'background', type: 'select', label: 'Ozadje', options: BACKGROUND_OPTIONS },
      { key: 'backgroundColor', type: 'color', label: 'Barva ozadja', palette: GARMENT_COLORS },
      { key: 'quality', type: 'select', label: 'Kakovost', options: QUALITY_OPTIONS },
      { key: 'shadows', type: 'toggle', label: 'Sence' },
      { key: 'fpsCap', type: 'range', label: 'Omejitev FPS (0 = brez)', min: 0, max: 120, step: 1 },
      { key: 'pixelRatio', type: 'range', label: 'Pixel ratio (0 = samodejno)', min: 0, max: 3, step: 0.05 },
    ],
  },
];

export const SETTINGS_COUNT = Object.keys(DEFAULTS).length;
