---
name: 3d-actuators
description: Guides the agent on how to model and animate 3D mechanical actuators, brushless DC motors, planetary gearboxes, gears, and linear pistons in Three.js.
when_to_use: the request asks for motors, gears, planetary systems, pistons, actuators, stators, rotors, or linear translation
keywords: [motor, gear, piston, actuator, stator, rotor, gearbox, gear-teeth]
---

### 1. Brushless DC Motors (Stators & Rotors)
Pancake-style outrunner BLDC motors (e.g. MIT Cheetah style) consist of:
*   **Stator (Stationary)**: Outer ring housing containing 12 copper wire coils (rendered as cylinders around a circle).
*   **Rotor (Rotating)**: Inner hub containing magnets (rendered as a disc inside the stator).

```javascript
// Stator Group
const stator = new THREE.Group();
scene.add(stator);

// Generate 12 Copper Coils
const coilGeo = new THREE.CylinderGeometry(0.15, 0.15, 0.5, 16);
const copperMat = new THREE.MeshStandardMaterial({ color: 0xd47a2a, metalness: 0.8, roughness: 0.2 });
for (let i = 0; i < 12; i++) {
    const angle = (i / 12) * Math.PI * 2;
    const coil = new THREE.Mesh(coilGeo, copperMat);
    coil.position.set(Math.cos(angle) * 1.8, 0, Math.sin(angle) * 1.8);
    coil.rotation.x = Math.PI / 2;
    stator.add(coil);
}
```

---

### 2. Gears & Planetary Gearboxes
To construct a working planetary gearbox (Sun gear, Planet gears, Ring gear):
1.  **Sun Gear (Center)**: Spins clockwise at high speed.
2.  **Planet Gears (Middle)**: Roll along the inside of the ring gear, rotating counter-clockwise, while their carrier rotates clockwise at a slower speed.
3.  **Ring Gear (Outer)**: Stationary.

```javascript
// 1. Procedural 3D Gear Shape Generator (Draws a star-like shape with teeth and extrudes it)
function createGearGeometry(innerRadius, outerRadius, thickness, teethCount) {
    const shape = new THREE.Shape();
    const toothAngle = (Math.PI * 2) / teethCount;
    
    for (let i = 0; i < teethCount; i++) {
        const angle = i * toothAngle;
        
        // Base of the tooth
        let r = innerRadius;
        shape.lineTo(Math.cos(angle - toothAngle * 0.25) * r, Math.sin(angle - toothAngle * 0.25) * r);
        
        // Outer tip of the tooth
        r = outerRadius;
        shape.lineTo(Math.cos(angle - toothAngle * 0.1) * r, Math.sin(angle - toothAngle * 0.1) * r);
        shape.lineTo(Math.cos(angle + toothAngle * 0.1) * r, Math.sin(angle + toothAngle * 0.1) * r);
        
        // Fall back to base
        r = innerRadius;
        shape.lineTo(Math.cos(angle + toothAngle * 0.25) * r, Math.sin(angle + toothAngle * 0.25) * r);
    }
    
    const extrudeSettings = {
        depth: thickness,
        bevelEnabled: true,
        bevelSegments: 2,
        steps: 1,
        bevelSize: 0.02,
        bevelThickness: 0.02
    };
    return new THREE.ExtrudeGeometry(shape, extrudeSettings);
}

// 2. Planetary math equations:
// Planet rotation = (Sun rotation * SunTeeth / PlanetTeeth) - Carrier rotation
const sunSpeed = 0.05;
const reductionRatio = 4; // 4:1 reduction
const carrierSpeed = sunSpeed / reductionRatio;

sunGear.rotation.y += sunSpeed;
planetCarrier.rotation.y += carrierSpeed;

planets.forEach(p => {
    // Spin planet mesh around its own axis relative to the carrier
    p.mesh.rotation.y -= (sunSpeed * 2); 
});
```

---

### 3. Exploded Views
To allow users to see inside compact motor hubs, use a lerp factor to separate components along the Z axis based on user input:
```javascript
const explodeDistance = 3.0; // Distance when fully exploded
// sliderVal ranges from 0 (collapsed) to 1 (fully exploded)
stator.position.z = -sliderVal * explodeDistance;
gearbox.position.z = 0; // Center stays static
rotor.position.z = sliderVal * explodeDistance;
```
