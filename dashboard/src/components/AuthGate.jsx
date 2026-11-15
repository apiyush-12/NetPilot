import React, { useLayoutEffect } from 'react'
import { SignIn, useAuth } from '@clerk/react'
import App from '../App.jsx'
import { setClerkTokenGetter } from '../lib/api.js'
import './auth.css'

export default function AuthGate() {
  // Hooks must be called inside the React component.
  const { isLoaded, isSignedIn, getToken } = useAuth()

  useLayoutEffect(() => {
    setClerkTokenGetter(isSignedIn ? getToken : null)

    return () => {
      setClerkTokenGetter(null)
    }
  }, [isSignedIn, getToken])

  if (!isLoaded) {
    return (
      <div className="netpilot-auth-screen">
        <p>INITIALIZING NETPILOT AUTHENTICATION...</p>
      </div>
    )
  }

  if (!isSignedIn) {
    return (
      <div className="netpilot-auth-screen">
        <div className="netpilot-auth-heading">
          <div className="netpilot-auth-symbol">N·</div>
          <h1>NETPILOT</h1>
          <p>NETWORK OPERATIONS PLATFORM</p>
        </div>

        <div className="netpilot-auth-panel">
          <div className="netpilot-auth-label">
            IDENTITY VERIFICATION / SECURE ACCESS
          </div>
          <SignIn />
        </div>

        <div className="netpilot-auth-footer">
          AUTHORIZED OPERATORS ONLY
        </div>
      </div>
    )
  }

  return <App />
}