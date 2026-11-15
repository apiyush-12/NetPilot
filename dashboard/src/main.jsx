import React from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/react'
import AuthGate from './components/AuthGate.jsx'
import './style.css'

const publishableKey =
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!publishableKey) {
  throw new Error(
    'Missing VITE_CLERK_PUBLISHABLE_KEY in dashboard/.env.local'
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={publishableKey}>
      <AuthGate />
    </ClerkProvider>
  </React.StrictMode>
)