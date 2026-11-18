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
    <figure className="sh-brain" role="img" aria-label="A blue three-dimensional brain made of connected neurons">
      <NeuralBrain
        still={still}
        particleColor="#3988FF"
        meshColor="#2055DD"
        pulseColor="#8FC6FF"
      />
    </figure>
  );
}
