import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";

import App from "./App";
import { ApiError } from "./lib/api";
import { AuthProvider } from "./lib/auth";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      // Do not retry client errors such as 403/404.
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
          {/* Toasts (STYLEGUIDE §10.6): slate-900, white text, e3 shadow, bottom centre, 5 seconds. */}
          <Toaster position="bottom-center" duration={5000} closeButton
            toastOptions={{
              style: {
                background: "#141824", color: "#FFFFFF", border: 0, borderRadius: 8, padding: "12px 16px",
                font: "400 14px/20px 'IBM Plex Sans', 'Helvetica Neue', system-ui, sans-serif",
                boxShadow: "0 4px 8px rgba(19,35,74,.08), 0 24px 48px rgba(19,35,74,.16)",
              },
              classNames: { closeButton: "!bg-[#141824] !text-white !border-[#4A5368]", actionButton: "!bg-white !text-[#141824] !font-medium" },
            }} />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
