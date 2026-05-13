import React from 'react'
import ReactDOM from 'react-dom/client'
import { Amplify } from 'aws-amplify'
import App from './App'
import { awsConfig } from './aws-exports'
import './index.css'

/**
 * Configure AWS Amplify v6 before rendering the app.
 * Amplify v6 stores tokens in localStorage by default via
 * CognitoUserPoolsTokenProvider — acceptable for this SPA.
 */
Amplify.configure(awsConfig)

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
