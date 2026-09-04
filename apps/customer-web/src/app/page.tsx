import React from 'react';

export default function HomePage() {
  return (
    <main style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem', textAlign: 'center' }}>
      <div style={{ background: 'rgba(30, 41, 59, 0.7)', padding: '3rem', borderRadius: '16px', border: '1px solid rgba(255, 255, 255, 0.1)', maxWidth: '600px' }}>
        <h1 style={{ color: '#38bdf8', fontSize: '2.5rem', marginBottom: '1rem' }}>RoadResQ</h1>
        <p style={{ fontSize: '1.2rem', color: '#94a3b8', marginBottom: '2rem' }}>
          Digital Roadside Assistance Platform — Phase 0 Development Environment Operational.
        </p>
        <div style={{ display: 'inline-block', background: '#0284c7', color: '#ffffff', padding: '0.75rem 1.5rem', borderRadius: '8px', fontWeight: 600 }}>
          Phase 0 Foundation Ready
        </div>
      </div>
    </main>
  );
}
