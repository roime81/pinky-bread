import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import FounderComposer from "./FounderComposer";
import "./styles.css";

const container = document.getElementById("a2a-workspace-root");
if (container) {
  createRoot(container).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

const composerContainer = document.getElementById("company-composer-root");
if (composerContainer) {
  createRoot(composerContainer).render(
    <React.StrictMode>
      <FounderComposer />
    </React.StrictMode>,
  );
}
