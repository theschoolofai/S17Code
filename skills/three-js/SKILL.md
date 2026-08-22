---
name: three-js
description: Guides the agent on importing Three.js, setting up Scene/Camera/Renderer boilerplate, lighting, OrbitControls, particle systems, lil-gui, post-processing bloom, and soft shadows.
when_to_use: the request asks for 3D, three.js, WebGL, animations, or interactive 3D graphics
keywords: [three.js, 3d, webgl, canvas, animation, scene, renderer, camera]
---

### 1. Script Imports & CSS Boilerplate
Include scripts in `<head>` and CSS to ensure full-screen canvas without margins/scrollbars:
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script src="https://cdn.jsdelivr.net/npm/lil-gui@0.18"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
<style>
    body { margin: 0; padding: 0; overflow: hidden; background-color: #05050a; }
    canvas { display: block; width: 100vw; height: 100vh; }
</style>
```

### 2. Boilerplate Setup & Controls
```javascript
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 5, 10);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

// Basic lighting (vital for standard/phong materials)
const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
scene.add(ambientLight);

const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(5, 10, 5);
scene.add(dirLight);

// Handle Resizing (Updates both renderer and EffectComposer to prevent pixelation/bugs)
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    if (typeof composer !== 'undefined') {
        composer.setSize(window.innerWidth, window.innerHeight);
    }
});
```

### 3. Particle Systems (Starfields / Nebulas)
Create high-performance particles using BufferGeometry and PointsMaterial:
```javascript
const count = 1000;
const geometry = new THREE.BufferGeometry();
const pos = new Float32Array(count * 3);
for (let i = 0; i < count * 3; i++) pos[i] = (Math.random() - 0.5) * 15;
geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3));

const starField = new THREE.Points(geometry, new THREE.PointsMaterial({
    size: 0.05, color: 0x00ffff, transparent: true, opacity: 0.8
}));
scene.add(starField);
```

### 4. Interactive GUI (lil-gui)
```javascript
const config = { speed: 0.01, color: '#00ffcc' };
const gui = new lil.GUI();
gui.add(config, 'speed', 0, 0.05);
gui.addColor(config, 'color').onChange(val => mesh.material.color.set(val));
```

### 5. UnrealBloomPass (Light Bloom / Neon Glow)
Import these CDN files to make meshes glow:
```html
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/EffectComposer.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/RenderPass.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/ShaderPass.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/CopyShader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/LuminosityHighPassShader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/UnrealBloomPass.js"></script>
```
Initialize in JavaScript:
```javascript
const composer = new THREE.EffectComposer(renderer);
composer.addPass(new THREE.RenderPass(scene, camera));

const bloom = new THREE.UnrealBloomPass(
    new THREE.Vector2(window.innerWidth, window.innerHeight), 1.5, 0.4, 0.85
);
composer.addPass(bloom);

// Call composer.render() inside requestAnimationFrame instead of renderer.render()
```

### 6. Premium Soft Shadows
```javascript
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

dirLight.castShadow = true;
dirLight.shadow.mapSize.width = 2048;
dirLight.shadow.mapSize.height = 2048;
dirLight.shadow.bias = -0.0005;

mesh.castShadow = true;
floor.receiveShadow = true;
```

### 7. Self-Contained 3D Assets (CORS & GLB Rules)
When loading external assets (models/textures) dynamically over the web:
*   **Use single-file `.glb` files**: Standard `.gltf` files reference separate texture files (e.g., `laces.png`). Loading these on raw CDNs will trigger CORS or path-resolution errors. A `.glb` file packs all geometry, materials, and textures into one single file, which loads without failures.
*   **Wait for DOM load**: Wrap your Three.js initialization code in `window.addEventListener('DOMContentLoaded', ...)` to ensure the canvas can mount correctly onto `document.body` without throwing undefined element errors.
