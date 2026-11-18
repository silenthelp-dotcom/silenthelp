import React, {useSyncExternalStore} from 'react';
import NeuralBrain from './neural-brain/NeuralBrain';

const preference = '(prefers-reduced-motion: reduce)';
function subscribe(callback) {
  const query = window.matchMedia(preference);
  query.addEventListener('change', callback);
  return () => query.removeEventListener('change', callback);
}

export default function Brain() {
  const still = useSyncExternalStore(subscribe, () => window.matchMedia(preference).matches, () => true);
  return (
    <figure className="sh-brain" role="img" aria-label="A softly lit three-dimensional brain made of connected neurons">
      <NeuralBrain
        still={still}
        brainScale={1.15}
        nodeBrightness={0.82}
        lineBrightness={0.42}
        meshColor="#93888e"
        particleColor="#a6a4ae"
        pulseColor="#958898"
        pulseBrightness={0.33}
        autoRotationSpeed={0.018}
        hoverStrength={0}
        backgroundParticleCount={0}
        enterAnimEnabled={false}
      />
    </figure>
  );
}
