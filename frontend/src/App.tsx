import { Route, Routes } from "react-router-dom";
import CommandCenter from "./pages/CommandCenter";

// Additional routes (/forecast, /map, /simulator, ...) are registered as each
// page is implemented, so there are never links to unfinished pages.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<CommandCenter />} />
    </Routes>
  );
}
