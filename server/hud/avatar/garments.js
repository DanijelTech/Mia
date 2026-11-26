/* Procedural garments, accessories and the robot rig.
 *
 * The RPM mesh only exposes whole top/bottom/footwear meshes, so extra
 * clothing is built as rigid props attached to bones: a collar follows the
 * neck, pauldrons follow the shoulders, a skirt follows the hips. Everything
 * is authored in world space from the current skeleton and then re-parented to
 * its bone by the runtime.
 */

import * as THREE from 'three';

const UP = new THREE.Vector3(0, 1, 0);
const AXIS_Z = new THREE.Vector3(0, 0, 1);

function baseMaterial(color) {
  return new THREE.MeshStandardMaterial({
    color: color || '#101820', metalness: 0.55, roughness: 0.34,
  });
}

function glowMaterial(color, intensity) {
  const mat = new THREE.MeshStandardMaterial({
    color: color || '#00e5ff', emissive: color || '#00e5ff',
    emissiveIntensity: Math.max(0, Number(intensity) || 1),
    metalness: 0.2, roughness: 0.3,
  });
  mat.toneMapped = false;
  return mat;
}

function addMesh(group, geometry, material, position, quaternion) {
  const mesh = new THREE.Mesh(geometry, material);
  if (position) mesh.position.copy(position);
  if (quaternion) mesh.quaternion.copy(quaternion);
  mesh.frustumCulled = false;
  group.add(mesh);
  return mesh;
}

function facing(basis) {
  const m = new THREE.Matrix4().makeBasis(basis.right, basis.up, basis.forward);
  return new THREE.Quaternion().setFromRotationMatrix(m);
}

function along(from, to) {
  return new THREE.Quaternion().setFromUnitVectors(from, to);
}

function part(bone, object, materials) {
  object.userData.materials = materials;
  return { bone, object };
}

function ringAt(group, mat, radius, tube, position, axis) {
  return addMesh(group, new THREE.TorusGeometry(radius, tube, 10, 28), mat,
    position, along(AXIS_Z, axis));
}

function cylinderAt(group, mat, top, bottom, height, position, axis) {
  return addMesh(group, new THREE.CylinderGeometry(top, bottom, height, 18, 1, true),
    mat, position, along(UP, axis));
}

function pauldronPair(ctx, mat) {
  const parts = [];
  if (!ctx.shoulders || !ctx.shoulders.left || !ctx.shoulders.right) return parts;
  for (const side of ['left', 'right']) {
    const sh = ctx.shoulders[side];
    const group = new THREE.Group();
    const dir = sh.dir.clone().normalize();
    addMesh(group, new THREE.SphereGeometry(1, 18, 12), mat,
      sh.pos.clone().add(dir.clone().multiplyScalar(0.03)),
      new THREE.Quaternion()).scale.set(ctx.torso.width * 0.22,
        ctx.torso.width * 0.15, ctx.torso.width * 0.24);
    parts.push(part(side === 'left' ? 'LeftShoulder' : 'RightShoulder', group, { base: mat }));
  }
  return parts;
}

function beltAt(ctx, mat) {
  const group = new THREE.Group();
  const pos = ctx.hips.pos.clone().add(ctx.hips.up.clone().multiplyScalar(0.015));
  ringAt(group, mat, ctx.hips.width * 0.8, 0.014, pos, ctx.hips.up);
  addMesh(group, new THREE.BoxGeometry(0.05, 0.035, 0.02), mat,
    ctx.hips.pos.clone()
      .add(ctx.hips.forward.clone().multiplyScalar(ctx.hips.depth * 0.5))
      .add(ctx.hips.up.clone().multiplyScalar(0.015)),
    facing(ctx.hips));
  return part('Hips', group, { base: mat });
}

function skirtAt(ctx, mat, length, topScale = 0.8, bottomScale = 1.18) {
  const group = new THREE.Group();
  const height = Math.max(0.08, length * 0.85);
  const top = ctx.hips.width * topScale;
  const bottom = ctx.hips.width * bottomScale;
  const pos = ctx.hips.pos.clone().add(ctx.hips.up.clone().multiplyScalar(-height * 0.42));
  cylinderAt(group, mat, top, bottom, height, pos, ctx.hips.up);
  ringAt(group, mat, top, 0.012, pos.clone().add(ctx.hips.up.clone().multiplyScalar(height * 0.5)), ctx.hips.up);
  return part('Hips', group, { base: mat });
}

function robotRig(ctx, baseMat, glowMat) {
  const parts = [];
  const neck = new THREE.Group();
  ringAt(neck, glowMat, ctx.torso.width * 0.2, 0.007,
    ctx.neck.pos.clone().add(ctx.neck.dir.clone().multiplyScalar(0.02)),
    ctx.neck.dir);
  parts.push(part('Neck', neck, { glow: glowMat }));

  for (const [side, bone] of [['left', 'LeftForeArm'], ['right', 'RightForeArm']]) {
    const arm = ctx.forearms && ctx.forearms[side];
    if (!arm) continue;
    const group = new THREE.Group();
    const dir = arm.dir.clone().normalize();
    ringAt(group, baseMat, 0.033, 0.009, arm.pos.clone().add(dir.clone().multiplyScalar(0.14)), dir);
    ringAt(group, glowMat, 0.033, 0.003, arm.pos.clone().add(dir.clone().multiplyScalar(0.155)), dir);
    parts.push(part(bone, group, { base: baseMat, glow: glowMat }));
  }

  for (const [side, bone] of [['left', 'LeftUpLeg'], ['right', 'RightUpLeg']]) {
    const leg = ctx.thighs && ctx.thighs[side];
    if (!leg) continue;
    const group = new THREE.Group();
    const dir = leg.dir.clone().normalize();
    ringAt(group, baseMat, 0.058, 0.012, leg.pos.clone().add(dir.clone().multiplyScalar(0.2)), dir);
    ringAt(group, glowMat, 0.058, 0.004, leg.pos.clone().add(dir.clone().multiplyScalar(0.215)), dir);
    parts.push(part(bone, group, { base: baseMat, glow: glowMat }));
  }

  const chest = new THREE.Group();
  const corePos = ctx.chest.pos.clone()
    .add(ctx.chest.forward.clone().multiplyScalar(ctx.chest.depth * 0.62))
    .add(ctx.chest.up.clone().multiplyScalar(ctx.chest.height * 0.06));
  addMesh(chest, new THREE.CylinderGeometry(0.028, 0.028, 0.012, 20), baseMat,
    corePos, along(UP, ctx.chest.forward));
  addMesh(chest, new THREE.CylinderGeometry(0.018, 0.018, 0.016, 20), glowMat,
    corePos.clone().add(ctx.chest.forward.clone().multiplyScalar(0.004)),
    along(UP, ctx.chest.forward));
  parts.push(part('Spine2', chest, { base: baseMat, glow: glowMat }));
  return parts;
}

/* Build one accessory. Returns [{bone, object}] in world space. */
export function buildAccessory(id, ctx) {
  const baseMat = baseMaterial(ctx.color);
  const glowMat = glowMaterial(ctx.glow, ctx.intensity);
  const parts = [];
  const length = Math.max(0.15, Number(ctx.length) || 0.6);

  if (ctx.robot) parts.push(...robotRig(ctx, baseMat, glowMat));

  switch (id) {
    case 'collar': {
      const group = new THREE.Group();
      ringAt(group, baseMat, ctx.torso.width * 0.21, 0.012,
        ctx.neck.pos.clone().add(ctx.neck.dir.clone().multiplyScalar(0.03)),
        ctx.neck.dir);
      parts.push(part('Neck', group, { base: baseMat }));
      break;
    }
    case 'tie': {
      const group = new THREE.Group();
      const top = ctx.chest.pos.clone()
        .add(ctx.chest.forward.clone().multiplyScalar(ctx.chest.depth * 0.6))
        .add(ctx.chest.up.clone().multiplyScalar(ctx.chest.height * 0.2));
      const q = facing(ctx.chest);
      addMesh(group, new THREE.BoxGeometry(0.045, 0.035, 0.02), baseMat, top, q);
      addMesh(group, new THREE.BoxGeometry(0.05, 0.24 * length, 0.012), baseMat,
        top.clone().add(ctx.chest.up.clone().multiplyScalar(-0.15 * length - 0.02)), q);
      parts.push(part('Spine2', group, { base: baseMat }));
      break;
    }
    case 'scarf': {
      const group = new THREE.Group();
      ringAt(group, baseMat, ctx.torso.width * 0.23, 0.022,
        ctx.neck.pos.clone().add(ctx.neck.dir.clone().multiplyScalar(0.02)),
        ctx.neck.dir);
      const top = ctx.chest.pos.clone()
        .add(ctx.chest.forward.clone().multiplyScalar(ctx.chest.depth * 0.58))
        .add(ctx.chest.up.clone().multiplyScalar(ctx.chest.height * 0.16));
      addMesh(group, new THREE.BoxGeometry(0.07, 0.3 * length, 0.018), baseMat,
        top.clone().add(ctx.chest.up.clone().multiplyScalar(-0.17 * length)),
        facing(ctx.chest));
      parts.push(part('Spine2', group, { base: baseMat }));
      break;
    }
    case 'pauldrons':
      parts.push(...pauldronPair(ctx, baseMat));
      break;
    case 'armor': {
      parts.push(...pauldronPair(ctx, baseMat));
      const group = new THREE.Group();
      const q = facing(ctx.chest);
      const plate = ctx.chest.pos.clone()
        .add(ctx.chest.forward.clone().multiplyScalar(ctx.chest.depth * 0.52))
        .add(ctx.chest.up.clone().multiplyScalar(ctx.chest.height * 0.08));
      addMesh(group, new THREE.BoxGeometry(ctx.torso.width * 0.72, ctx.chest.height * 0.42, 0.03),
        baseMat, plate, q);
      addMesh(group, new THREE.BoxGeometry(0.014, ctx.chest.height * 0.3, 0.012), glowMat,
        plate.clone().add(ctx.chest.forward.clone().multiplyScalar(0.02)), q);
      parts.push(part('Spine2', group, { base: baseMat, glow: glowMat }));
      parts.push(beltAt(ctx, baseMat));
      break;
    }
    case 'visor': {
      const group = new THREE.Group();
      const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);
      const arc = new THREE.Mesh(
        new THREE.TorusGeometry(ctx.head.width * 0.5, 0.014, 10, 32, Math.PI * 0.96),
        glowMat);
      arc.position.copy(ctx.head.center).add(ctx.head.up.clone().multiplyScalar(ctx.head.height * 0.06));
      arc.quaternion.copy(q);
      arc.frustumCulled = false;
      group.add(arc);
      parts.push(part('Head', group, { glow: glowMat }));
      break;
    }
    case 'antenna': {
      const group = new THREE.Group();
      const base = ctx.head.center.clone()
        .add(ctx.head.up.clone().multiplyScalar(ctx.head.height * 0.42))
        .add(ctx.head.right.clone().multiplyScalar(ctx.head.width * 0.26));
      const tip = base.clone().add(ctx.head.up.clone().multiplyScalar(0.16));
      addMesh(group, new THREE.CylinderGeometry(0.005, 0.007, 0.16, 8), baseMat,
        base.clone().add(ctx.head.up.clone().multiplyScalar(0.08)),
        along(UP, ctx.head.up));
      addMesh(group, new THREE.SphereGeometry(0.018, 14, 10), glowMat, tip);
      parts.push(part('Head', group, { base: baseMat, glow: glowMat }));
      break;
    }
    case 'headset': {
      const group = new THREE.Group();
      const band = new THREE.Mesh(
        new THREE.TorusGeometry(ctx.head.height * 0.55, 0.012, 10, 32, Math.PI),
        baseMat);
      band.position.copy(ctx.head.center);
      band.frustumCulled = false;
      group.add(band);
      for (const side of [-1, 1]) {
        const cup = ctx.head.center.clone()
          .add(ctx.head.right.clone().multiplyScalar(side * ctx.head.width * 0.5))
          .add(ctx.head.up.clone().multiplyScalar(-ctx.head.height * 0.05));
        addMesh(group, new THREE.CylinderGeometry(0.032, 0.032, 0.022, 18), baseMat,
          cup, along(UP, ctx.head.right));
        ringAt(group, glowMat, 0.032, 0.004,
          cup.clone().add(ctx.head.right.clone().multiplyScalar(side * 0.013)),
          ctx.head.right);
      }
      parts.push(part('Head', group, { base: baseMat, glow: glowMat }));
      break;
    }
    case 'belt':
      parts.push(beltAt(ctx, baseMat));
      break;
    case 'skirt':
      parts.push(skirtAt(ctx, baseMat, length));
      break;
    case 'dress': {
      const group = new THREE.Group();
      const height = Math.max(0.2, ctx.torso.height * 1.15 * length);
      const pos = ctx.hips.pos.clone().add(ctx.hips.up.clone().multiplyScalar(height * 0.36));
      cylinderAt(group, baseMat, ctx.torso.width * 0.5, ctx.hips.width * 0.8,
        height, pos, ctx.hips.up);
      parts.push(part('Hips', group, { base: baseMat }));
      parts.push(skirtAt(ctx, baseMat, length * 1.15, 0.78, 1.25));
      break;
    }
    case 'thruster': {
      const group = new THREE.Group();
      for (const side of [-1, 1]) {
        const pos = ctx.chest.pos.clone()
          .add(ctx.chest.forward.clone().multiplyScalar(-ctx.chest.depth * 0.75))
          .add(ctx.chest.right.clone().multiplyScalar(side * ctx.torso.width * 0.32))
          .add(ctx.chest.up.clone().multiplyScalar(-ctx.chest.height * 0.05));
        addMesh(group, new THREE.CylinderGeometry(0.028, 0.04, 0.16, 14), baseMat,
          pos, along(UP, ctx.chest.up));
        addMesh(group, new THREE.CylinderGeometry(0.024, 0.024, 0.02, 14), glowMat,
          pos.clone().add(ctx.chest.up.clone().multiplyScalar(-0.09)),
          along(UP, ctx.chest.up));
      }
      parts.push(part('Spine2', group, { base: baseMat, glow: glowMat }));
      break;
    }
    default:
      break;
  }
  return parts;
}
