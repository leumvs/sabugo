import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";

const target = document.getElementById("app");
if (!target) {
  throw new Error("app_target_not_found");
}

const app = mount(App, {
  target: target,
});

export default app;
