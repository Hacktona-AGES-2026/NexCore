import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ToastProvider } from "./components/Toast";
import { Audit } from "./pages/Audit";
import { Equity } from "./pages/Equity";
import { Home } from "./pages/Home";
import { Impact } from "./pages/Impact";
import { Pendencies } from "./pages/Pendencies";
import { Queue } from "./pages/Queue";
import { Screen } from "./pages/Screen";
import { QueueProvider } from "./state/QueueContext";
import "./styles/global.css";
import "./styles/features.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <QueueProvider>
          <Routes>
            <Route path="telao" element={<Screen />} />
            <Route element={<Layout />}>
              <Route index element={<Home />} />
              <Route path="fila" element={<Queue />} />
              <Route path="fila/:id" element={<Queue />} />
              <Route path="pendencias" element={<Pendencies />} />
              <Route path="equidade" element={<Equity />} />
              <Route path="impacto" element={<Impact />} />
              <Route path="auditoria" element={<Audit />} />
            </Route>
          </Routes>
        </QueueProvider>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
