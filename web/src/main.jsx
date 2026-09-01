import { render } from "preact";
import { App } from "./app.jsx";
import { login } from "./auth.js";
import "./styles.css";

login().then(() => render(<App />, document.getElementById("app")));
