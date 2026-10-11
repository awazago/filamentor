// Visualizador 3D: mesa da impressora + modelo colorido por overhang.
// Mundo em Z para cima (mesma convenção da impressora e da análise do backend).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const BED_TOLERANCE_MM = 0.2; // igual ao backend: faces encostadas na mesa não são overhang
const BASE_COLOR = [0.78, 0.8, 0.84];
const WARN_COLOR = [0.98, 0.66, 0.15];
const OVERHANG_COLOR = [0.9, 0.2, 0.25];
const WARN_MARGIN_DEG = 15;

export class Viewer {
  constructor(container) {
    this.container = container;
    this.threshold = 45;
    this.original = null; // posições originais (Float32Array), para reaplicar rotações
    this.rotation = new THREE.Matrix4();

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.append(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 2.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(1, -1.5, 2);
    this.scene.add(sun);

    this.bed = new THREE.Group();
    this.scene.add(this.bed);
    this.setBed(256, 256);

    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    this.renderer.setAnimationLoop(() => {
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
    });
  }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  setBed(x, y) {
    this.bedSize = [x, y];
    this.bed.clear();
    const plate = new THREE.Mesh(
      new THREE.PlaneGeometry(x, y),
      new THREE.MeshStandardMaterial({ color: 0x2a2f38, roughness: 0.9 }),
    );
    plate.position.z = -0.05;
    const grid = new THREE.GridHelper(Math.max(x, y), Math.max(x, y) / 10, 0x4a5260, 0x3a404b);
    grid.rotation.x = Math.PI / 2;
    this.bed.add(plate, grid);
    if (this.mesh) this.placeOnBed();
  }

  /** Carrega um STL (ArrayBuffer). 3MF chega já convertido pelo backend, placa a placa:
   *  o leitor de 3MF do Three.js não entende os projetos do Bambu Studio. */
  loadSTL(buffer) {
    const geometry = new STLLoader().parse(buffer);
    this.setGeometry(geometry.index ? geometry.toNonIndexed() : geometry);
  }

  setGeometry(geometry) {
    if (this.mesh) {
      this.scene.remove(this.mesh);
      this.mesh.geometry.dispose();
    }
    const position = geometry.getAttribute("position");
    this.original = position.array.slice();
    const clean = new THREE.BufferGeometry();
    clean.setAttribute("position", new THREE.BufferAttribute(position.array.slice(), 3));
    clean.setAttribute(
      "color",
      new THREE.BufferAttribute(new Uint8Array(position.count * 3), 3, true),
    );
    this.mesh = new THREE.Mesh(
      clean,
      new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, metalness: 0.05 }),
    );
    this.scene.add(this.mesh);
    this.rotation.identity();
    this.applyTransform();
    this.frame();
  }

  /** Aplica uma rotação 3×3 (linhas, como vem do backend) à peça original. */
  setRotation(rows) {
    this.rotation.set(
      rows[0][0], rows[0][1], rows[0][2], 0,
      rows[1][0], rows[1][1], rows[1][2], 0,
      rows[2][0], rows[2][1], rows[2][2], 0,
      0, 0, 0, 1,
    );
    this.applyTransform();
    this.frame();
  }

  /** Escala uniforme só visual (mostra o tamanho final sobre a mesa). Ângulos não mudam. */
  setScale(factor) {
    if (!this.mesh || this.mesh.scale.x === factor) return;
    this.mesh.scale.setScalar(factor);
    this.frame();
  }

  setThreshold(degrees) {
    this.threshold = degrees;
    if (this.mesh) this.colorize();
  }

  applyTransform() {
    const position = this.mesh.geometry.getAttribute("position");
    position.array.set(this.original);
    this.mesh.geometry.applyMatrix4(this.rotation);
    this.placeOnBed();
    this.mesh.geometry.computeVertexNormals();
    this.colorize();
  }

  placeOnBed() {
    const geometry = this.mesh.geometry;
    geometry.computeBoundingBox();
    const { min, max } = geometry.boundingBox;
    geometry.translate(-(min.x + max.x) / 2, -(min.y + max.y) / 2, -min.z);
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
  }

  colorize() {
    const position = this.mesh.geometry.getAttribute("position").array;
    const colors = this.mesh.geometry.getAttribute("color");
    const out = colors.array;
    const limit = -Math.cos((this.threshold * Math.PI) / 180);
    const warn = -Math.cos(((this.threshold + WARN_MARGIN_DEG) * Math.PI) / 180);
    let overhangArea = 0;
    let totalArea = 0;

    for (let i = 0; i < position.length; i += 9) {
      // Normal da face pelo produto vetorial (normais gravadas no STL nem sempre são confiáveis).
      const ax = position[i + 3] - position[i], ay = position[i + 4] - position[i + 1], az = position[i + 5] - position[i + 2];
      const bx = position[i + 6] - position[i], by = position[i + 7] - position[i + 1], bz = position[i + 8] - position[i + 2];
      const nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
      const length = Math.hypot(nx, ny, nz) || 1;
      const z = nz / length;
      const centerZ = (position[i + 2] + position[i + 5] + position[i + 8]) / 3;
      const area = length / 2;
      totalArea += area;

      let color = BASE_COLOR;
      if (centerZ > BED_TOLERANCE_MM) {
        if (z < limit) {
          color = OVERHANG_COLOR;
          overhangArea += area;
        } else if (z < warn) {
          color = WARN_COLOR;
        }
      }
      for (let v = 0; v < 3; v++) {
        const o = i + v * 3;
        out[o] = color[0] * 255;
        out[o + 1] = color[1] * 255;
        out[o + 2] = color[2] * 255;
      }
    }
    colors.needsUpdate = true;
    this.overhangRatio = totalArea ? overhangArea / totalArea : 0;
    this.container.dispatchEvent(
      new CustomEvent("overhang", { detail: { ratio: this.overhangRatio, threshold: this.threshold } }),
    );
  }

  frame() {
    const sphere = this.mesh?.geometry.boundingSphere;
    const scale = this.mesh?.scale.x ?? 1;
    const radius = sphere ? Math.max(sphere.radius * scale, 5) : Math.max(...this.bedSize) / 2;
    const center = sphere ? sphere.center.clone().multiplyScalar(scale) : new THREE.Vector3();
    // Usa o menor campo de visão (vertical ou horizontal) para caber também em telas estreitas.
    const vertical = (this.camera.fov * Math.PI) / 180;
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * this.camera.aspect);
    const distance = radius / Math.sin(Math.min(vertical, horizontal) / 2);
    this.camera.position.set(center.x + distance * 0.6, center.y - distance * 0.9, center.z + distance * 0.55);
    this.camera.near = distance / 100;
    this.camera.far = distance * 100;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(center);
  }
}
