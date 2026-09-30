import { lazy } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { App } from './App';
import { RouteError } from './ErrorBoundary';

const Overview = lazy(() => import('@/pages/Overview'));
const Command = lazy(() => import('@/pages/Command'));
const Studio = lazy(() => import('@/pages/Studio'));
const AttackLab = lazy(() => import('@/pages/AttackLab'));
const Playground = lazy(() => import('@/pages/Playground'));
const Analytics = lazy(() => import('@/pages/Analytics'));
const Ledger = lazy(() => import('@/pages/Ledger'));
const Incidents = lazy(() => import('@/pages/Incidents'));
const Session = lazy(() => import('@/pages/Session'));
const Method = lazy(() => import('@/pages/Method'));
const NotFound = lazy(() => import('@/pages/NotFound'));

export const router = createBrowserRouter([
  {
    path: '/', element: <App />, errorElement: <RouteError />,
    children: [
      { index: true, element: <Overview /> },
      { path: 'command', element: <Command /> },
      { path: 'studio', element: <Studio /> },
      { path: 'attack-lab', element: <AttackLab /> },
      { path: 'playground', element: <Playground /> },
      { path: 'analytics', element: <Analytics /> },
      { path: 'ledger', element: <Ledger /> },
      { path: 'incidents', element: <Incidents /> },
      { path: 'incidents/:id', element: <Incidents /> },
      { path: 'sessions/:id', element: <Session /> },
      { path: 'method', element: <Method /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]);
