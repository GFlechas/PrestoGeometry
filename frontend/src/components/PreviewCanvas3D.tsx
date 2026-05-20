import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import * as THREE from "three";
import { useFloorplan } from "../state/useFloorplan";
import { buildScene } from "../preview3d/buildScene";

export function PreviewCanvas3D() {
  const doc = useFloorplan((s) => s.doc);
  const { instances, bounds } = useMemo(() => buildScene(doc), [doc]);

  const center = new THREE.Vector3();
  bounds.getCenter(center);
  const size = new THREE.Vector3();
  bounds.getSize(size);
  const radius = Math.max(size.x, size.z, size.y) || 10;
  const cameraPos: [number, number, number] = [
    center.x + radius * 1.4,
    center.y + radius * 1.0,
    center.z + radius * 1.4,
  ];

  return (
    <Canvas
      camera={{ position: cameraPos, fov: 45, near: 0.1, far: radius * 20 }}
      style={{ background: "#1f2329", width: "100%", height: "100%" }}
    >
      <ambientLight intensity={0.55} />
      <directionalLight position={[radius, radius * 2, radius]} intensity={0.9} castShadow />
      <directionalLight position={[-radius, radius, -radius]} intensity={0.35} />

      <Grid
        position={[center.x, 0, center.z]}
        args={[radius * 4, radius * 4]}
        cellSize={1}
        cellThickness={0.6}
        cellColor="#3d4450"
        sectionSize={5}
        sectionThickness={1}
        sectionColor="#4f9cff"
        infiniteGrid={false}
        fadeDistance={radius * 6}
      />

      {instances.map((inst, i) => (
        <group key={`${inst.storyId}-${i}`}>
          {inst.slabs.map((s, j) => (
            <mesh key={`slab-${j}`} geometry={s.geometry} castShadow receiveShadow>
              <meshStandardMaterial
                color={inst.color}
                transparent
                opacity={0.85}
                side={THREE.DoubleSide}
              />
            </mesh>
          ))}
          {inst.walls.map((w, j) => (
            <mesh
              key={`wall-${j}`}
              geometry={w.geometry}
              position={w.position}
              rotation={[0, w.rotationY, 0]}
              castShadow
              receiveShadow
            >
              <meshStandardMaterial
                color="#cfd6e1"
                transparent
                opacity={0.92}
                side={THREE.DoubleSide}
              />
            </mesh>
          ))}
          {inst.panels.map((p, j) => (
            <mesh
              key={`panel-${j}`}
              geometry={p.geometry}
              position={p.position}
              rotation={[0, p.rotationY, 0]}
            >
              <meshStandardMaterial
                color={p.kind === "window" ? "#4f9cff" : "#a86b3a"}
                transparent={p.kind === "window"}
                opacity={p.kind === "window" ? 0.55 : 1}
                side={THREE.DoubleSide}
                roughness={p.kind === "window" ? 0.15 : 0.7}
              />
            </mesh>
          ))}
        </group>
      ))}

      <OrbitControls target={[center.x, center.y, center.z]} makeDefault />
    </Canvas>
  );
}
