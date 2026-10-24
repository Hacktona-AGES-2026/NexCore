import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ToastProvider } from "./components/Toast";
import { Audit } from "./pages/Audit";
import { Home } from "./pages/Home";
import { Queue } from "./pages/Queue";
import { QueueProvider } from "./state/QueueContext";
import "./styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <QueueProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Home />} />
              <Route path="fila" element={<Queue />} />
              <Route path="fila/:id" element={<Queue />} />
              <Route path="auditoria" element={<Audit />} />
            </Route>
          </Routes>
        </QueueProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
