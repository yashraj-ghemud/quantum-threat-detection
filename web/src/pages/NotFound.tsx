import { Link } from 'react-router-dom';
import { motion } from 'motion/react';

export default function NotFound() {
  return (
    <div className="nf">
      <svg viewBox="0 0 200 200" width={200} aria-hidden>
        <circle cx={100} cy={100} r={80} fill="none" stroke="var(--line-strong)" strokeWidth={2} />
        <ellipse cx={100} cy={100} rx={80} ry={22} fill="none" stroke="var(--line-strong)" strokeDasharray="4 4" />
        <motion.line x1={100} y1={100} x2={100} y2={20} stroke="var(--lav)" strokeWidth={5} strokeLinecap="round" style={{ originX: '100px', originY: '100px' }}
          initial={{ rotate: -40 }} animate={{ rotate: 180 }} transition={{ type: 'spring', stiffness: 60, damping: 8, delay: 0.3 }} />
        <circle cx={100} cy={100} r={6} fill="var(--lav)" />
      </svg>
      <span className="kicker">404</span>
      <h1>State collapsed — this page does not exist</h1>
      <p className="muted">The measurement found |1⟩ where a page should have been.</p>
      <div className="row"><Link className="btn primary" to="/">Overview</Link><Link className="btn" to="/command">Command Center</Link></div>
    </div>
  );
}
