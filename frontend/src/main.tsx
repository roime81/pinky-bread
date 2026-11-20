import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import WorkspaceApp from "./WorkspaceApp";
import "./styles.css";
import "@uppy/core/css/style.min.css";
import "@uppy/dashboard/css/style.min.css";
import "./workspace.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Pinky Bread workspace root element #root was not found.");
}

createRoot(container).render(
  <StrictMode>
    <WorkspaceApp />
  </StrictMode>,
);
