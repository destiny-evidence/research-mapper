import { render } from 'preact'
import { App } from './app.jsx'
import { login } from './auth.js'
import './styles.css'

// Sign in first: a redirect to Keycloak would throw away anything rendered
// here, and every API call needs the token anyway.
login().then(() => render(<App />, document.getElementById('app')))
