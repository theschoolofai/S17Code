---
name: 3d-robots
description: Guides the agent on how to build and animate 3D humanoid robots, quadruped robot dogs, leg/arm joint hierarchies, and walk-cycle gait kinematics in Three.js.
when_to_use: the request asks for humanoid robots, quadruped dogs, bipeds, robotic legs, arm joint chains, or walk/trot cycle animations
keywords: [robot, humanoid, quadruped, leg, walking, gait, kinematics, joint, skeletal]
---

### 1. Joint Hierarchies (Kinematic Chains)
Robot limbs must be nested hierarchically so parent rotations move children naturally (e.g. rotating hip moves thighs, knees, and feet).

```javascript
// Thigh Group (Parent)
const thighGroup = new THREE.Group();
thighGroup.position.set(0, 0, 0); // Connected to hip

// Calf Group (Child of Thigh)
const calfGroup = new THREE.Group();
calfGroup.position.set(0, -2, 0); // Positioned at bottom of thigh
thighGroup.add(calfGroup);

// Foot Mesh (Child of Calf)
const footGeo = new THREE.BoxGeometry(0.3, 0.1, 0.6);
const foot = new THREE.Mesh(footGeo, metalMat);
foot.position.set(0, -1.5, 0.2); // Offset forward
calfGroup.add(foot);
```

---

### 2. Quadruped Gait Physics (Robot Dog Trot)
A robot dog trot cycle is modeled by phase-shifting diagonal legs by 180 degrees (Pi radians):
*   **Diagonal Group A**: Front-Left (FL) & Rear-Right (RR)
*   **Diagonal Group B**: Front-Right (FR) & Rear-Left (RL)

```javascript
function animateTrot(time, speed) {
    const angle = time * speed;
    
    // Group A (Phase 0)
    const swingA = Math.sin(angle) * 0.4;
    // Bend knee (lower leg) when leg is swinging forward (swingA > 0)
    const kneeA = swingA > 0 ? swingA * 0.8 : 0;
    
    // Group B (Phase Pi / 180 degree offset)
    const swingB = Math.sin(angle + Math.PI) * 0.4;
    const kneeB = swingB > 0 ? swingB * 0.8 : 0;
    
    // Apply hip rotation (swing) and knee bending (rotation)
    legFL.thigh.rotation.x = swingA;
    legFL.calf.rotation.x = -kneeA; // Bend backwards
    
    legRR.thigh.rotation.x = swingA;
    legRR.calf.rotation.x = -kneeA;
    
    legFR.thigh.rotation.x = swingB;
    legFR.calf.rotation.x = -kneeB;
    
    legRL.thigh.rotation.x = swingB;
    legRL.calf.rotation.x = -kneeB;

    // Treadmill effect: scroll the ground grid backward to simulate actual locomotion
    if (typeof gridHelper !== 'undefined') {
        gridHelper.position.z = (gridHelper.position.z + speed * 0.1) % 2; // Loop distance
    }
}
```

---

### 3. Humanoid Walk Balancers
To keep a walking humanoid balanced, synchronize arm swing opposite to leg swing, and apply body bobbing:
```javascript
const angle = time * speed;
leftHip.rotation.x = Math.sin(angle) * 0.45;
rightHip.rotation.x = -Math.sin(angle) * 0.45;

// Opposite Arm Swing
leftShoulder.rotation.x = -Math.sin(angle) * 0.35;
rightShoulder.rotation.x = Math.sin(angle) * 0.35;

// Body bobbing (bounces twice per full stride)
torso.position.y = defaultHeight + Math.sin(angle * 2) * 0.15;
```
