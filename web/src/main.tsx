import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './map.css';
import './map-geometry.css';
import './forecast-story.css';
import './home-polish.css';
import './recovery-review.css';
import './landing.css';
import './map-selection.css';
import './hospital-forecast.css';
import './journey.css';
import './plan-focus.css';
import './story-type.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
