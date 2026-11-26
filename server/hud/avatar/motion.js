/* Procedural full-body motion for the Mia avatar.
 *
 * The free model ships one Mixamo idle clip and no gesture library, so every
 * action here is a keyframe track of *world-axis* rotations per bone. The
 * runtime converts an axis to bone-local space using the current parent world
 * rotation and premultiplies the delta, so chained poses (raise arm, then bend
 * elbow) behave the way they read.
 *
 * Pure module on purpose: no `three` import, so it can be unit-tested with
 * node and reused by the HUD. Axes: +X right, +Y up, +Z forward (character
 * faces the camera). A pose entry is `{ x, y, z }` in radians plus optional
 * `tx, ty, tz` in metres for the Hips.
 */

const key = (t, pose = {}) => ({ t, pose });

const GUARD = {
  LeftArm: { z: 0.5, x: -0.25 },
  RightArm: { z: -0.5, x: -0.25 },
  LeftForeArm: { x: -1.15 },
  RightForeArm: { x: -1.15 },
  Spine: { y: -0.06 },
  Head: { x: 0.04 },
};

const PUNCH_RIGHT = {
  RightArm: { x: -1.35, z: -0.12 },
  RightForeArm: { x: -0.18 },
  LeftForeArm: { x: -1.3 },
  Spine: { y: 0.32, x: 0.04 },
  Head: { y: -0.12 },
};

const PUNCH_LEFT = {
  LeftArm: { x: -1.35, z: 0.12 },
  LeftForeArm: { x: -0.18 },
  RightForeArm: { x: -1.3 },
  Spine: { y: -0.32, x: 0.04 },
  Head: { y: 0.12 },
};

const KICK_RIGHT = {
  RightUpLeg: { x: -1.05, z: -0.12 },
  RightLeg: { x: 0.32 },
  RightFoot: { x: -0.2 },
  LeftArm: { z: 0.75, x: -0.2 },
  RightArm: { z: -0.6, x: -0.35 },
  LeftForeArm: { x: -1.0 },
  RightForeArm: { x: -1.2 },
  Spine: { x: -0.14, y: 0.1 },
  Hips: { tx: 0.02 },
};

export const ACTIONS = {
  /* --- head ------------------------------------------------------------- */
  nod: {
    label: 'prikima', group: 'glava', dur: 0.85,
    keys: [
      key(0),
      key(0.22, { Head: { x: 0.22 }, Neck: { x: 0.08 } }),
      key(0.46, { Head: { x: -0.07 } }),
      key(0.66, { Head: { x: 0.13 }, Neck: { x: 0.04 } }),
      key(1),
    ],
  },
  shake: {
    label: 'odkima', group: 'glava', dur: 1.05,
    keys: [
      key(0),
      key(0.18, { Head: { y: 0.3 }, Neck: { y: 0.08 } }),
      key(0.38, { Head: { y: -0.3 }, Neck: { y: -0.08 } }),
      key(0.58, { Head: { y: 0.24 } }),
      key(0.78, { Head: { y: -0.15 } }),
      key(1),
    ],
  },
  tilt: {
    label: 'nagne glavo', group: 'glava', dur: 0.95,
    keys: [
      key(0),
      key(0.35, { Head: { z: 0.26, y: 0.05 } }),
      key(0.7, { Head: { z: 0.2 } }),
      key(1),
    ],
  },
  look: {
    label: 'pogled vstran', group: 'glava', dur: 1.0,
    keys: [
      key(0),
      key(0.3, { Head: { y: -0.32 }, Neck: { y: -0.08 } }),
      key(0.72, { Head: { y: -0.26 } }),
      key(1),
    ],
  },
  lookAround: {
    label: 'ozira se', group: 'glava', dur: 2.2,
    keys: [
      key(0),
      key(0.2, { Head: { y: 0.34 }, Neck: { y: 0.1 } }),
      key(0.45, { Head: { y: -0.34 }, Neck: { y: -0.1 } }),
      key(0.7, { Head: { y: 0.22 } }),
      key(0.85, { Head: { x: -0.12 } }),
      key(1),
    ],
  },

  /* --- arms and hands --------------------------------------------------- */
  wave: {
    label: 'maha', group: 'roke', dur: 1.9,
    keys: [
      key(0),
      key(0.14, { LeftArm: { z: 1.3, x: -0.2 }, LeftForeArm: { x: -0.35 },
        Head: { z: 0.06 }, Spine: { y: -0.04 } }),
      key(0.3, { LeftArm: { z: 1.55, x: -0.15 }, LeftForeArm: { x: -0.3 },
        LeftHand: { z: 0.3 }, Head: { z: 0.07 } }),
      key(0.46, { LeftArm: { z: 1.28, x: -0.22 }, LeftForeArm: { x: -0.4 },
        LeftHand: { z: -0.28 }, Head: { z: 0.05 } }),
      key(0.62, { LeftArm: { z: 1.55, x: -0.15 }, LeftForeArm: { x: -0.3 },
        LeftHand: { z: 0.3 }, Head: { z: 0.07 } }),
      key(0.78, { LeftArm: { z: 1.28, x: -0.22 }, LeftForeArm: { x: -0.4 },
        LeftHand: { z: -0.28 } }),
      key(0.9, { LeftArm: { z: 1.1 }, LeftForeArm: { x: -0.25 } }),
      key(1),
    ],
  },
  waveBoth: {
    label: 'maha z obema', group: 'roke', dur: 2.0,
    keys: [
      key(0),
      key(0.18, { LeftArm: { z: 1.45 }, RightArm: { z: -1.45 },
        LeftForeArm: { x: -0.35 }, RightForeArm: { x: -0.35 },
        Head: { x: -0.08 } }),
      key(0.36, { LeftArm: { z: 1.2 }, RightArm: { z: -1.2 },
        LeftHand: { z: 0.25 }, RightHand: { z: -0.25 } }),
      key(0.54, { LeftArm: { z: 1.45 }, RightArm: { z: -1.45 },
        LeftHand: { z: -0.25 }, RightHand: { z: 0.25 } }),
      key(0.72, { LeftArm: { z: 1.2 }, RightArm: { z: -1.2 } }),
      key(0.86, { LeftArm: { z: 1.35 }, RightArm: { z: -1.35 } }),
      key(1),
    ],
  },
  point: {
    label: 'pokaže', group: 'roke', dur: 1.25,
    keys: [
      key(0),
      key(0.24, { RightArm: { x: -1.15, z: -0.15 }, RightForeArm: { x: -0.1 },
        Spine: { y: 0.12 }, Head: { y: -0.08, x: -0.04 } }),
      key(0.72, { RightArm: { x: -1.12, z: -0.14 }, RightForeArm: { x: -0.08 },
        Spine: { y: 0.1 }, Head: { y: -0.07 } }),
      key(1),
    ],
  },
  shrug: {
    label: 'skomigne', group: 'roke', dur: 1.3,
    keys: [
      key(0),
      key(0.22, { LeftArm: { z: 0.42, x: -0.1 }, RightArm: { z: -0.42, x: -0.1 },
        LeftForeArm: { x: -0.7 }, RightForeArm: { x: -0.7 },
        Spine2: { x: -0.04 }, Head: { z: 0.09, x: 0.04 } }),
      key(0.62, { LeftArm: { z: 0.4, x: -0.1 }, RightArm: { z: -0.4, x: -0.1 },
        LeftForeArm: { x: -0.68 }, RightForeArm: { x: -0.68 },
        Spine2: { x: -0.04 }, Head: { z: 0.08 } }),
      key(1),
    ],
  },
  salute: {
    label: 'pozdravi', group: 'roke', dur: 1.5,
    keys: [
      key(0),
      key(0.25, { RightArm: { z: -1.05, x: -0.35 }, RightForeArm: { x: -1.95 },
        RightHand: { z: 0.2 }, Head: { x: -0.05 }, Spine: { x: -0.03 } }),
      key(0.75, { RightArm: { z: -1.05, x: -0.35 }, RightForeArm: { x: -1.95 },
        RightHand: { z: 0.2 }, Head: { x: -0.05 } }),
      key(1),
    ],
  },
  think: {
    label: 'razmišlja', group: 'roke', dur: 1.8,
    keys: [
      key(0),
      key(0.28, { RightArm: { x: -0.55, z: -0.5 }, RightForeArm: { x: -1.95 },
        Head: { z: -0.12, x: 0.06 }, Spine: { z: -0.03 } }),
      key(0.72, { RightArm: { x: -0.55, z: -0.5 }, RightForeArm: { x: -1.9 },
        Head: { z: -0.1, x: 0.04 } }),
      key(1),
    ],
  },
  heart: {
    label: 'srce', group: 'roke', dur: 1.8,
    keys: [
      key(0),
      key(0.25, { LeftArm: { x: -0.6, z: 0.42 }, RightArm: { x: -0.6, z: -0.42 },
        LeftForeArm: { x: -1.85 }, RightForeArm: { x: -1.85 },
        Head: { x: 0.08 }, Spine: { x: 0.05 } }),
      key(0.7, { LeftArm: { x: -0.58, z: 0.4 }, RightArm: { x: -0.58, z: -0.4 },
        LeftForeArm: { x: -1.8 }, RightForeArm: { x: -1.8 },
        Head: { x: 0.07 }, Spine: { x: 0.05 } }),
      key(1),
    ],
  },
  celebrate: {
    label: 'slavi', group: 'roke', dur: 1.9,
    keys: [
      key(0),
      key(0.2, { LeftArm: { z: 2.0 }, RightArm: { z: -2.0 },
        LeftForeArm: { x: -0.2 }, RightForeArm: { x: -0.2 },
        Head: { x: -0.16 }, Spine: { x: -0.07 } }),
      key(0.42, { LeftArm: { z: 1.8 }, RightArm: { z: -1.8 },
        Head: { x: -0.1 }, Spine: { z: 0.05 } }),
      key(0.62, { LeftArm: { z: 2.0 }, RightArm: { z: -2.0 },
        Head: { x: -0.16 }, Spine: { z: -0.05 } }),
      key(0.8, { LeftArm: { z: 1.85 }, RightArm: { z: -1.85 } }),
      key(1),
    ],
  },

  /* --- torso and whole body -------------------------------------------- */
  bow: {
    label: 'poklon', group: 'telo', dur: 1.5,
    keys: [
      key(0),
      key(0.28, { Spine: { x: 0.28 }, Spine1: { x: 0.18 }, Spine2: { x: 0.1 },
        Neck: { x: 0.08 }, Head: { x: 0.06 },
        LeftArm: { z: 0.12 }, RightArm: { z: -0.12 } }),
      key(0.62, { Spine: { x: 0.32 }, Spine1: { x: 0.2 }, Spine2: { x: 0.12 },
        Neck: { x: 0.1 }, Head: { x: 0.06 },
        LeftArm: { z: 0.12 }, RightArm: { z: -0.12 } }),
      key(1),
    ],
  },
  bend: {
    label: 'prekloni se', group: 'telo', dur: 2.1,
    keys: [
      key(0),
      key(0.24, { Spine: { x: 0.34 }, Spine1: { x: 0.24 }, Spine2: { x: 0.12 },
        Neck: { x: -0.12 }, Head: { x: -0.1 },
        LeftLeg: { x: 0.08 }, RightLeg: { x: 0.08 },
        Hips: { tz: -0.03, ty: -0.01 } }),
      key(0.5, { Spine: { x: 0.62 }, Spine1: { x: 0.4 }, Spine2: { x: 0.22 },
        Neck: { x: -0.24 }, Head: { x: -0.18 },
        LeftArm: { z: 0.18, x: 0.2 }, RightArm: { z: -0.18, x: 0.2 },
        LeftLeg: { x: 0.14 }, RightLeg: { x: 0.14 },
        Hips: { tz: -0.06, ty: -0.02 } }),
      key(0.74, { Spine: { x: 0.58 }, Spine1: { x: 0.38 }, Spine2: { x: 0.2 },
        Neck: { x: -0.22 }, Head: { x: -0.16 },
        LeftArm: { z: 0.18, x: 0.2 }, RightArm: { z: -0.18, x: 0.2 },
        LeftLeg: { x: 0.13 }, RightLeg: { x: 0.13 },
        Hips: { tz: -0.055, ty: -0.02 } }),
      key(1),
    ],
  },
  lean: {
    label: 'nagne se', group: 'telo', dur: 1.6,
    keys: [
      key(0),
      key(0.28, { Spine: { z: 0.22 }, Spine1: { z: 0.12 }, Head: { z: -0.12 },
        Hips: { tx: 0.02 } }),
      key(0.68, { Spine: { z: 0.24 }, Spine1: { z: 0.13 }, Head: { z: -0.12 },
        Hips: { tx: 0.02 } }),
      key(1),
    ],
  },
  stretch: {
    label: 'razteza se', group: 'telo', dur: 2.4,
    keys: [
      key(0),
      key(0.22, { LeftArm: { z: 2.15 }, RightArm: { z: -2.15 },
        LeftForeArm: { x: -0.1 }, RightForeArm: { x: -0.1 },
        Spine: { x: -0.16 }, Spine1: { x: -0.1 }, Head: { x: -0.2 } }),
      key(0.45, { LeftArm: { z: 2.2 }, RightArm: { z: -2.2 },
        Spine: { x: -0.2 }, Head: { x: -0.22 } }),
      key(0.65, { Spine: { x: 0.3 }, Spine1: { x: 0.2 },
        LeftArm: { x: -0.7, z: 0.2 }, RightArm: { x: -0.7, z: -0.2 },
        LeftForeArm: { x: -0.6 }, RightForeArm: { x: -0.6 },
        Head: { x: 0.12 } }),
      key(0.85, { Spine: { x: 0.2 }, Head: { x: 0.08 } }),
      key(1),
    ],
  },
  dance: {
    label: 'pleše', group: 'telo', dur: 3.0,
    keys: [
      key(0),
      key(0.14, { Hips: { y: 0.14 }, Spine: { z: 0.1, y: 0.06 },
        LeftArm: { z: 1.1, x: -0.2 }, RightArm: { z: -0.4 },
        LeftForeArm: { x: -0.6 }, RightForeArm: { x: -1.0 },
        Head: { z: 0.1 } }),
      key(0.3, { Hips: { y: -0.14 }, Spine: { z: -0.1, y: -0.06 },
        LeftArm: { z: 0.4 }, RightArm: { z: -1.1, x: -0.2 },
        LeftForeArm: { x: -1.0 }, RightForeArm: { x: -0.6 },
        Head: { z: -0.1 } }),
      key(0.46, { Hips: { y: 0.14 }, Spine: { z: 0.1, y: 0.06 },
        LeftArm: { z: 1.1, x: -0.2 }, RightArm: { z: -0.4 },
        LeftForeArm: { x: -0.6 }, RightForeArm: { x: -1.0 },
        Head: { z: 0.1 } }),
      key(0.62, { Hips: { y: -0.14 }, Spine: { z: -0.1, y: -0.06 },
        LeftArm: { z: 0.4 }, RightArm: { z: -1.1, x: -0.2 },
        LeftForeArm: { x: -1.0 }, RightForeArm: { x: -0.6 },
        Head: { z: -0.1 } }),
      key(0.8, { LeftArm: { z: 1.5 }, RightArm: { z: -1.5 },
        Head: { x: -0.1 } }),
      key(1),
    ],
  },

  /* --- combat ----------------------------------------------------------- */
  punch: {
    label: 'udari', group: 'borba', dur: 1.0,
    keys: [
      key(0),
      key(0.14, GUARD),
      key(0.36, PUNCH_RIGHT),
      key(0.56, GUARD),
      key(0.74, { ...GUARD, RightForeArm: { x: -1.25 }, Spine: { y: 0.04 } }),
      key(1),
    ],
  },
  kick: {
    label: 'brcne', group: 'borba', dur: 1.35,
    keys: [
      key(0),
      key(0.16, GUARD),
      key(0.42, KICK_RIGHT),
      key(0.62, KICK_RIGHT),
      key(0.8, GUARD),
      key(1),
    ],
  },
  block: {
    label: 'blokira', group: 'borba', dur: 1.1,
    keys: [
      key(0),
      key(0.2, { LeftArm: { x: -0.95, z: 0.2 }, RightArm: { x: -0.95, z: -0.2 },
        LeftForeArm: { x: -1.65 }, RightForeArm: { x: -1.65 },
        Head: { x: 0.1 }, Spine: { x: 0.08 } }),
      key(0.7, { LeftArm: { x: -0.92, z: 0.19 }, RightArm: { x: -0.92, z: -0.19 },
        LeftForeArm: { x: -1.6 }, RightForeArm: { x: -1.6 },
        Head: { x: 0.09 }, Spine: { x: 0.07 } }),
      key(1),
    ],
  },
  kata: {
    label: 'kata', group: 'borba', dur: 3.4,
    keys: [
      key(0),
      key(0.1, GUARD),
      key(0.24, PUNCH_RIGHT),
      key(0.4, PUNCH_LEFT),
      key(0.56, { LeftArm: { z: 1.5, x: -0.15 }, RightArm: { z: -1.5, x: -0.15 },
        LeftForeArm: { x: -0.15 }, RightForeArm: { x: -0.15 },
        Spine: { x: 0.04 }, Head: { x: -0.08 } }),
      key(0.7, { LeftArm: { x: -0.95, z: 0.2 }, RightArm: { x: -0.95, z: -0.2 },
        LeftForeArm: { x: -1.65 }, RightForeArm: { x: -1.65 },
        Spine: { x: 0.08 }, Head: { x: 0.1 } }),
      key(0.84, KICK_RIGHT),
      key(0.92, GUARD),
      key(1),
    ],
  },
  combat: {
    label: 'borilna kombinacija', group: 'borba', dur: 4.0,
    keys: [
      key(0),
      key(0.08, GUARD),
      key(0.22, PUNCH_RIGHT),
      key(0.34, GUARD),
      key(0.46, PUNCH_LEFT),
      key(0.58, GUARD),
      key(0.74, KICK_RIGHT),
      key(0.86, GUARD),
      key(0.94, { LeftArm: { x: -0.9, z: 0.2 }, RightArm: { x: -0.9, z: -0.2 },
        LeftForeArm: { x: -1.6 }, RightForeArm: { x: -1.6 } }),
      key(1),
    ],
  },

  /* --- robot ------------------------------------------------------------ */
  scan: {
    label: 'skenira', group: 'robot', dur: 2.4,
    keys: [
      key(0),
      key(0.15, { Head: { y: 0.34, x: -0.04 }, Neck: { y: 0.12 },
        RightArm: { x: -0.6, z: -0.35 }, RightForeArm: { x: -1.7 } }),
      key(0.45, { Head: { y: -0.34, x: -0.04 }, Neck: { y: -0.12 },
        RightArm: { x: -0.6, z: -0.35 }, RightForeArm: { x: -1.7 } }),
      key(0.7, { Head: { y: 0.18 }, Neck: { y: 0.06 },
        RightArm: { x: -0.6, z: -0.35 }, RightForeArm: { x: -1.7 } }),
      key(0.88, { Head: { x: 0.06 } }),
      key(1),
    ],
  },
  powerUp: {
    label: 'vklop moči', group: 'robot', dur: 2.6,
    keys: [
      key(0),
      key(0.2, { LeftArm: { z: 0.5, x: 0.15 }, RightArm: { z: -0.5, x: 0.15 },
        LeftForeArm: { x: -0.5 }, RightForeArm: { x: -0.5 },
        Head: { x: 0.12 }, Spine: { x: 0.06 } }),
      key(0.42, { LeftArm: { z: 1.35 }, RightArm: { z: -1.35 },
        LeftForeArm: { x: -0.2 }, RightForeArm: { x: -0.2 },
        Head: { x: -0.18 }, Spine: { x: -0.1 } }),
      key(0.7, { LeftArm: { z: 1.4 }, RightArm: { z: -1.4 },
        Head: { x: -0.2 }, Spine: { x: -0.12 } }),
      key(0.88, { LeftArm: { z: 1.2 }, RightArm: { z: -1.2 },
        Head: { x: -0.1 } }),
      key(1),
    ],
  },
  glitch: {
    label: 'glitch', group: 'robot', dur: 1.4,
    keys: [
      key(0),
      key(0.08, { Head: { z: 0.16, y: 0.12 }, Spine: { z: 0.05 },
        LeftArm: { x: -0.2, z: 0.25 }, RightArm: { x: -0.15, z: -0.3 } }),
      key(0.18, { Head: { z: -0.18, y: -0.14 }, Spine: { z: -0.05 },
        LeftArm: { x: -0.1, z: 0.15 }, RightArm: { x: -0.25, z: -0.2 } }),
      key(0.3, { Head: { z: 0.12, y: 0.08 }, LeftArm: { z: 0.3 },
        RightArm: { z: -0.35 } }),
      key(0.44, { Head: { z: -0.1 }, Spine: { z: 0.04 } }),
      key(0.58, { Head: { z: 0.08, y: -0.06 } }),
      key(0.75, { Head: { x: 0.1 } }),
      key(1),
    ],
  },
};

/* Slovenian and English synonyms accepted from `[gesture:…]` tags. */
export const ACTION_ALIASES = {
  pomahaj: 'wave', mahanje: 'wave', mahati: 'wave', maha: 'wave',
  pomahajzobema: 'waveBoth', mahanjezobema: 'waveBoth',
  poklon: 'bow', pokloni: 'bow', poklonise: 'bow', priklon: 'bow',
  preklon: 'bend', prekloni: 'bend', preklonise: 'bend', skloni: 'bend',
  prikima: 'nod', prikimaj: 'nod', prikimi: 'nod', prikimavanje: 'nod',
  pritrdi: 'nod',
  odkima: 'shake', odkimaj: 'shake', odkimi: 'shake', odkimavanje: 'shake',
  zanika: 'shake',
  nagni: 'tilt', nagib: 'tilt',
  poglej: 'look', ozri: 'lookAround', oziraj: 'lookAround',
  pokazi: 'point', pokaži: 'point', pokazati: 'point',
  skomigni: 'shrug', skomigne: 'shrug',
  pozdravi: 'salute', salutiraj: 'salute',
  razmisljaj: 'think', razmisli: 'think', misli: 'think',
  srce: 'heart', ljubezen: 'heart',
  slavi: 'celebrate', proslavi: 'celebrate', veselje: 'celebrate',
  razteg: 'stretch', raztegni: 'stretch', pretegni: 'stretch',
  ples: 'dance', plesi: 'dance',
  nagnise: 'lean', nasloni: 'lean',
  udari: 'punch', udarec: 'punch', boks: 'punch', punch: 'punch',
  brca: 'kick', brcni: 'kick', brcnaprej: 'kick', kick: 'kick',
  blok: 'block', blokiraj: 'block', block: 'block',
  borba: 'combat', borilna: 'combat', borilne: 'combat', borbena: 'combat',
  skeniraj: 'scan', skeniranje: 'scan',
  vklop: 'powerUp', napajanje: 'powerUp', powerup: 'powerUp',
  glitch: 'glitch', napaka: 'glitch',
};

export function resolveAction(name) {
  const raw = String(name || '').trim().toLowerCase();
  if (!raw) return null;
  const flat = raw.replace(/[\s_-]+/g, '');
  const id = ACTIONS[raw] ? raw : (ACTIONS[flat] ? flat : ACTION_ALIASES[flat]);
  return id && ACTIONS[id] ? id : null;
}

function mix(a, b, w) {
  return a + (b - a) * w;
}

function smooth(t) {
  return t * t * (3 - 2 * t);
}

/* Sample a track at normalized time `p`; missing axes interpolate from zero. */
export function samplePose(def, p) {
  const keys = (def && def.keys) || [];
  if (!keys.length) return {};
  const t = Math.min(1, Math.max(0, Number(p) || 0));
  let a = keys[0];
  let b = keys[keys.length - 1];
  for (let i = 0; i < keys.length - 1; i += 1) {
    if (t >= keys[i].t && t <= keys[i + 1].t) { a = keys[i]; b = keys[i + 1]; break; }
  }
  const span = Math.max(1e-6, b.t - a.t);
  const w = smooth(Math.min(1, Math.max(0, (t - a.t) / span)));
  const out = {};
  const pa = a.pose || {};
  const pb = b.pose || {};
  const names = new Set([...Object.keys(pa), ...Object.keys(pb)]);
  for (const name of names) {
    const va = pa[name] || {};
    const vb = pb[name] || {};
    const axes = new Set([...Object.keys(va), ...Object.keys(vb)]);
    const pose = {};
    for (const axis of axes) pose[axis] = mix(Number(va[axis]) || 0, Number(vb[axis]) || 0, w);
    out[name] = pose;
  }
  return out;
}

/* Cross-fade two pose maps (used when an action interrupts another). */
export function mixPose(a, b, w) {
  const out = {};
  const names = new Set([...Object.keys(a || {}), ...Object.keys(b || {})]);
  for (const name of names) {
    const va = (a && a[name]) || {};
    const vb = (b && b[name]) || {};
    const axes = new Set([...Object.keys(va), ...Object.keys(vb)]);
    const pose = {};
    for (const axis of axes) pose[axis] = mix(Number(va[axis]) || 0, Number(vb[axis]) || 0, w);
    out[name] = pose;
  }
  return out;
}

/* Merge additive pose maps into `target` (world-axis angles add up). */
export function addPose(target, source, scale = 1) {
  if (!source) return target;
  for (const [name, pose] of Object.entries(source)) {
    const dst = target[name] || (target[name] = {});
    for (const [axis, value] of Object.entries(pose)) {
      dst[axis] = (dst[axis] || 0) + (Number(value) || 0) * scale;
    }
  }
  return target;
}

export const ACTION_IDS = Object.keys(ACTIONS);
