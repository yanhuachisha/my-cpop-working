'use client';

import { useEffect } from 'react';

export function PointerAtmosphere() {
  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const coarsePointer = window.matchMedia('(pointer: coarse)');
    if (reducedMotion.matches || coarsePointer.matches) return;

    const root = document.documentElement;
    let frame = 0;
    let latestEvent: PointerEvent | null = null;
    let activeCard: HTMLElement | null = null;

    const resetCard = () => {
      if (!activeCard) return;
      activeCard.classList.remove('pointer-card-active');
      activeCard.style.removeProperty('--card-tilt-x');
      activeCard.style.removeProperty('--card-tilt-y');
      activeCard.style.removeProperty('--card-pointer-x');
      activeCard.style.removeProperty('--card-pointer-y');
      activeCard = null;
    };

    const render = () => {
      frame = 0;
      const event = latestEvent;
      if (!event) return;

      const viewportX = event.clientX / window.innerWidth;
      const viewportY = event.clientY / window.innerHeight;
      root.style.setProperty('--pointer-x', `${event.clientX}px`);
      root.style.setProperty('--pointer-y', `${event.clientY}px`);
      root.style.setProperty('--pointer-disc-x', `${((0.5 - viewportX) * 16).toFixed(2)}px`);
      root.style.setProperty('--pointer-disc-y', `${((0.5 - viewportY) * 12).toFixed(2)}px`);
      root.style.setProperty('--pointer-copy-x', `${((viewportX - 0.5) * 7).toFixed(2)}px`);
      root.style.setProperty('--pointer-copy-y', `${((viewportY - 0.5) * 5).toFixed(2)}px`);
      root.classList.add('pointer-enabled');

      const target = event.target instanceof Element
        ? event.target.closest<HTMLElement>([
          '[data-pointer-reactive]',
          '.knowledge-routes',
          '.knowledge-canvas',
          '.knowledge-insight',
          '.kugou-bridge-lab',
          '.kugou-discovery-card',
          '.library-import-card',
        ].join(','))
        : null;
      if (target !== activeCard) {
        resetCard();
        activeCard = target;
      }
      if (!activeCard) return;

      const rect = activeCard.getBoundingClientRect();
      const localX = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      const localY = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
      const inferredStrength = activeCard.classList.contains('knowledge-canvas')
        ? 0.22
        : activeCard.classList.contains('kugou-bridge-lab')
          ? 0.35
          : 0.5;
      const strength = Number(activeCard.dataset.pointerStrength || inferredStrength);
      activeCard.style.setProperty('--card-pointer-x', `${(localX * 100).toFixed(1)}%`);
      activeCard.style.setProperty('--card-pointer-y', `${(localY * 100).toFixed(1)}%`);
      activeCard.style.setProperty('--card-tilt-x', `${((0.5 - localY) * 5 * strength).toFixed(2)}deg`);
      activeCard.style.setProperty('--card-tilt-y', `${((localX - 0.5) * 7 * strength).toFixed(2)}deg`);
      activeCard.classList.add('pointer-card-active');
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (event.pointerType === 'touch') return;
      latestEvent = event;
      if (!frame) frame = window.requestAnimationFrame(render);
    };

    const handlePointerLeave = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = 0;
      latestEvent = null;
      resetCard();
      root.classList.remove('pointer-enabled');
    };

    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    document.documentElement.addEventListener('pointerleave', handlePointerLeave);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      document.documentElement.removeEventListener('pointerleave', handlePointerLeave);
      if (frame) window.cancelAnimationFrame(frame);
      resetCard();
      root.classList.remove('pointer-enabled');
    };
  }, []);

  return (
    <div className="pointer-atmosphere" aria-hidden="true">
      <i className="pointer-aura pointer-aura-main" />
      <i className="pointer-aura pointer-aura-ring" />
    </div>
  );
}
