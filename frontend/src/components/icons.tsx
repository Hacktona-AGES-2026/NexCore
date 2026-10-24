const base = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export const HomeIcon = () => <svg {...base}><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /></svg>;
export const ListIcon = () => <svg {...base}><path d="M9 6h12M9 12h12M9 18h12M4 6h.01M4 12h.01M4 18h.01" /></svg>;
export const ShieldIcon = ({ check = true }: { check?: boolean }) => (
  <svg {...base}><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z" />{check && <path d="M9 12l2 2 4-4" />}</svg>
);
export const ChevronDown = () => <svg {...base} strokeWidth={2}><path d="M7 10l5 5 5-5" /></svg>;
export const ChevronRight = () => <svg {...base} strokeWidth={2} className="chev"><path d="M9 6l6 6-6 6" /></svg>;
export const SearchIcon = () => <svg {...base} strokeWidth={2}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>;
export const DownloadIcon = () => <svg {...base} strokeWidth={2}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>;
export const InfoIcon = () => <svg {...base} strokeWidth={2}><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></svg>;
export const AlertIcon = () => <svg {...base}><path d="M10.3 3.9L2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></svg>;
export const MapIcon = () => <svg {...base}><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></svg>;
export const ScreenIcon = () => <svg {...base}><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>;
export const CheckIcon = () => <svg {...base} strokeWidth={2.2}><path d="M20 6L9 17l-5-5" /></svg>;
