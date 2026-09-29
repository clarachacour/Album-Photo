import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import "@/lib/i18n"; // side-effect: configures i18next before anything renders
import App from "@/App";
import { initMonitoring } from "@/lib/monitoring";

initMonitoring();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
