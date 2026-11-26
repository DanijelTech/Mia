/* Procedural hairstyles for the Mia avatar.
 *
 * The free RPM mesh ships a single hair mesh, so "more hairstyles" cannot come
 * from swapping meshes. These are stylised wigs built from spheres, tubes and
 * cones around the head bounding box. They are attached to the Head bone, so
 * they follow every nod, shake and bend without skinning data.
 *
 * Geometry is built in head-centre space: +Y up, +Z forward, +X right.
 */

import * as THREE from 'three';
import { HAIR_STYLES } from './presets.js';

const HALF_PI = Math.PI / 2;

function material(color) {
  return new THREE.MeshStandardMaterial({
    color: color || '#3b2418',
    roughness: 0.62,
    metalness: 0.04,
    side: THREE.DoubleSide,
  });
}

function shell(group, mat, radius, phiStart, phiLength, thetaLength, scale, pos) {
  const geo = new THREE.SphereGeometry(radius, 28, 18, phiStart, phiLength, 0, thetaLength);
  const mesh = new THREE.Mesh(geo, mat);
  mesh.scale.set(scale.x, scale.y, scale.z);
  mesh.position.set(pos.x, pos.y, pos.z);
  mesh.frustumCulled = false;
  group.add(mesh);
  return mesh;
}

function tube(group, mat, points, radius, segments = 10) {
  const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(p[0], p[1], p[2])));
  const geo = new THREE.TubeGeometry(curve, segments, radius, 6, false);
  const mesh = new THREE.Mesh(geo, mat);
  mesh.frustumCulled = false;
  group.add(mesh);
  return mesh;
}

function blob(group, mat, radius, pos, scale) {
  const geo = new THREE.SphereGeometry(radius, 16, 12);
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(pos[0], pos[1], pos[2]);
  if (scale) mesh.scale.set(scale[0], scale[1], scale[2]);
  mesh.frustumCulled = false;
  group.add(mesh);
  return mesh;
}

function ring(group, mat, radius, tubeRadius, pos, dir) {
  const mesh = new THREE.Mesh(new THREE.TorusGeometry(radius, tubeRadius, 8, 20), mat);
  mesh.position.set(pos[0], pos[1], pos[2]);
  if (dir) {
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1),
      new THREE.Vector3(dir[0], dir[1], dir[2]).normalize());
  }
  mesh.frustumCulled = false;
  group.add(mesh);
  return mesh;
}

function cap(group, mat, hw, hh, hd, theta = Math.PI * 0.38) {
  return shell(group, mat, 1, 0, Math.PI * 2, theta,
    { x: hw * 1.025, y: hh * 1.02, z: hd * 1.025 },
    { x: 0, y: hh * 0.05, z: 0 });
}

/* A few raised strands break the smooth "helmet" look of the shell. */
function crownStrands(group, mat, hw, hh, hd) {
  for (const side of [-0.55, -0.2, 0.2, 0.55]) {
    tube(group, mat, [
      [side * hw * 0.35, hh * 0.98, hd * 0.5],
      [side * hw * 0.62, hh * 1.04, hd * 0.08],
      [side * hw * 0.55, hh * 1.0, -hd * 0.4],
      [side * hw * 0.3, hh * 0.9, -hd * 0.8],
    ], hw * 0.055, 9);
  }
}

function backMass(group, mat, hw, hh, hd, spread = 1.06) {
  return shell(group, mat, 1, Math.PI, Math.PI, Math.PI * 0.92,
    { x: hw * spread, y: hh * 1.08, z: hd * spread },
    { x: 0, y: hh * 0.04, z: -hd * 0.02 });
}

function fringe(group, mat, hw, hh, hd) {
  const z = hd * 0.82;
  tube(group, mat, [
    [-hw * 0.78, hh * 0.44, z * 0.9],
    [-hw * 0.4, hh * 0.62, z],
    [0, hh * 0.66, z * 1.04],
    [hw * 0.4, hh * 0.62, z],
    [hw * 0.78, hh * 0.44, z * 0.9],
  ], hw * 0.13, 14);
}

function backLocks(group, mat, hw, hh, hd, cfg) {
  const count = cfg.locks;
  const length = hh * cfg.length;
  const long = cfg.length > 1.2;
  for (let i = 0; i < count; i += 1) {
    const a = 1.82 + (i / Math.max(1, count - 1)) * 2.68;
    const sx = Math.sin(a) * hw * 1.02;
    const sz = Math.cos(a) * hd * 1.02;
    const y0 = hh * (0.12 + 0.1 * Math.abs(Math.sin(a)));
    const bulge = cfg.volume;
    const x1 = sx * (long ? 1.45 : 1.08) * bulge;
    const z1 = sz * (long ? 1.3 : 1.08) * bulge - hd * (long ? 0.18 : 0.06);
    const x2 = sx * (long ? 2.1 : 0.92);
    const z2 = sz * (long ? 1.5 : 0.9) - hd * (long ? 0.4 : 0.08);
    tube(group, mat, [
      [sx, y0, sz],
      [x1, y0 - length * 0.32, z1],
      [x2, y0 - length * 0.7, z2],
      [x2, y0 - length, z2 - hd * 0.02],
    ], hw * (long ? 0.19 : 0.15) * Math.max(0.7, cfg.volume), 9);
  }
}

/* Two locks per side fall in front of the shoulder, so long hair reads as long
 * even with the model's fur collar. */
function faceLocks(group, mat, hw, hh, hd, length) {
  for (const side of [-1, 1]) {
    for (const [w, z, reach] of [[1.75, 1.35, 1], [1.45, 1.15, 0.9]]) {
      tube(group, mat, [
        [side * hw * 0.85, hh * 0.34, hd * 0.5],
        [side * hw * 1.25, -hh * 0.05, hd * 0.92],
        [side * hw * w, -hh * length * 0.7 * reach, hd * z],
        [side * hw * w * 0.94, -hh * length * reach, hd * z * 0.92],
      ], hw * 0.15, 9);
    }
  }
}

function ponytail(group, mat, hw, hh, hd) {
  const dir = [0, -0.45, -0.89];
  ring(group, mat, hw * 0.3, hw * 0.07, [0, hh * 0.5, -hd * 0.78], dir);
  tube(group, mat, [
    [0, hh * 0.5, -hd * 0.8],
    [0, hh * 0.2, -hd * 1.3],
    [0, -hh * 0.7, -hd * 1.35],
    [0, -hh * 1.6, -hd * 1.05],
    [0, -hh * 1.95, -hd * 0.8],
  ], hw * 0.26, 16);
}

function bun(group, mat, hw, hh, hd) {
  ring(group, mat, hw * 0.26, hw * 0.06, [0, hh * 0.62, -hd * 0.7], [0, 0.4, -0.9]);
  blob(group, mat, 1, [0, hh * 0.72, -hd * 0.86], [hw * 0.56, hh * 0.42, hd * 0.56]);
  blob(group, mat, 1, [0, hh * 0.72, -hd * 0.9], [hw * 0.42, hh * 0.32, hd * 0.42]);
}

function twinTails(group, mat, hw, hh, hd) {
  for (const side of [-1, 1]) {
    const base = [side * hw * 0.88, hh * 0.34, -hd * 0.3];
    ring(group, mat, hw * 0.18, hw * 0.05, base, [0, -0.3, -0.95]);
    tube(group, mat, [
      base,
      [side * hw * 1.18, hh * 0.1, -hd * 0.5],
      [side * hw * 1.28, -hh * 0.7, -hd * 0.45],
      [side * hw * 1.12, -hh * 1.5, -hd * 0.25],
    ], hw * 0.2, 12);
  }
}

function braids(group, mat, hw, hh, hd) {
  for (const side of [-1, 1]) {
    const points = [
      [side * hw * 0.82, hh * 0.3, -hd * 0.28],
      [side * hw * 1.02, -hh * 0.2, -hd * 0.18],
      [side * hw * 1.0, -hh * 0.8, hd * 0.02],
      [side * hw * 0.9, -hh * 1.35, hd * 0.12],
    ];
    const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p)));
    tube(group, mat, points, hw * 0.16, 12);
    for (let i = 1; i <= 7; i += 1) {
      const p = curve.getPoint(i / 8);
      blob(group, mat, 1, [p.x, p.y, p.z], [hw * 0.2, hw * 0.15, hw * 0.2]);
    }
    ring(group, mat, hw * 0.17, hw * 0.04, points[0], [0, -0.4, -0.9]);
  }
}

function afro(group, mat, hw, hh, hd) {
  shell(group, mat, 1, HALF_PI + 0.9, Math.PI * 2 - 1.8, Math.PI * 0.96,
    { x: hw * 1.58, y: hh * 1.46, z: hd * 1.58 },
    { x: 0, y: hh * 0.12, z: -hd * 0.02 });
  const bumps = 10;
  for (let i = 0; i < bumps; i += 1) {
    const a = (i / bumps) * Math.PI * 2;
    const r = hw * 1.42;
    blob(group, mat, 1,
      [Math.sin(a) * r, hh * (0.55 + 0.35 * Math.cos(a * 2)), -Math.cos(a) * r * 0.9],
      [hw * 0.32, hh * 0.28, hd * 0.32]);
  }
}

function mohawk(group, mat, hw, hh, hd) {
  const count = 6;
  for (let i = 0; i < count; i += 1) {
    const t = i / (count - 1);
    const z = hd * (0.5 - t * 1.15);
    const h = hh * (0.55 + 0.35 * Math.sin(t * Math.PI));
    const cone = new THREE.Mesh(new THREE.ConeGeometry(hw * 0.17, h, 7), mat);
    cone.position.set(0, hh * 0.92 + h * 0.35, z);
    cone.rotation.x = -0.25 + t * 0.35;
    cone.frustumCulled = false;
    group.add(cone);
  }
}

function pixieTufts(group, mat, hw, hh, hd) {
  for (const side of [-1, 1]) {
    const cone = new THREE.Mesh(new THREE.ConeGeometry(hw * 0.2, hh * 0.62, 6), mat);
    cone.position.set(side * hw * 0.52, hh * 0.86, hd * 0.42);
    cone.rotation.z = side * 0.95;
    cone.rotation.x = -0.35;
    cone.frustumCulled = false;
    group.add(cone);
  }
  tube(group, mat, [
    [-hw * 0.7, hh * 0.58, hd * 0.55],
    [-hw * 0.3, hh * 0.82, hd * 0.82],
    [hw * 0.15, hh * 0.84, hd * 0.84],
    [hw * 0.55, hh * 0.68, hd * 0.62],
  ], hw * 0.11, 10);
}

/* Build one procedural wig. Returns a Group whose origin is the head centre. */
export function buildHair(styleId, opts = {}) {
  const cfg = HAIR_STYLES[styleId];
  if (!cfg) return null;
  const hw = Math.max(0.02, Number(opts.width) || 0.18) / 2;
  const hh = Math.max(0.02, Number(opts.height) || 0.26) / 2;
  const hd = Math.max(0.02, Number(opts.depth) || 0.22) / 2;
  const mat = material(opts.color);
  const group = new THREE.Group();
  group.name = 'mia-hair-' + styleId;
  group.userData.material = mat;
  group.userData.style = styleId;

  const hasCap = styleId !== 'mohawk';
  if (hasCap) {
    cap(group, mat, hw, hh, hd, styleId === 'pixie' ? Math.PI * 0.34 : Math.PI * 0.38);
    crownStrands(group, mat, hw, hh, hd);
  }

  if (styleId === 'long' || styleId === 'short' || styleId === 'bob') {
    backMass(group, mat, hw, hh, hd, cfg.volume);
    backLocks(group, mat, hw, hh, hd, cfg);
    if (styleId === 'long') faceLocks(group, mat, hw, hh, hd, cfg.length * 0.85);
    if (cfg.fringe) fringe(group, mat, hw, hh, hd);
  } else if (styleId === 'pixie') {
    backMass(group, mat, hw, hh, hd, 0.98);
    backLocks(group, mat, hw, hh, hd, cfg);
    pixieTufts(group, mat, hw, hh, hd);
  } else if (styleId === 'ponytail') {
    backMass(group, mat, hw, hh, hd, 1);
    ponytail(group, mat, hw, hh, hd);
    fringe(group, mat, hw, hh, hd);
  } else if (styleId === 'bun') {
    backMass(group, mat, hw, hh, hd, 1);
    bun(group, mat, hw, hh, hd);
  } else if (styleId === 'twin') {
    backMass(group, mat, hw, hh, hd, 1.02);
    twinTails(group, mat, hw, hh, hd);
    fringe(group, mat, hw, hh, hd);
  } else if (styleId === 'braid') {
    backMass(group, mat, hw, hh, hd, 1.02);
    braids(group, mat, hw, hh, hd);
  } else if (styleId === 'afro') {
    afro(group, mat, hw, hh, hd);
  } else if (styleId === 'mohawk') {
    mohawk(group, mat, hw, hh, hd);
  }
  return group;
}

export function disposeHair(group) {
  if (!group) return;
  group.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();
  });
}
