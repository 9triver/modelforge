import { Link, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage';
import RepoPage from './pages/RepoPage';

function NavBar() {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
        <Link to="/" className="text-xl font-bold text-gray-900">
          🔨 ModelForge
        </Link>
        <nav className="text-sm text-gray-600 flex gap-4">
          <Link to="/" className="hover:text-gray-900">仓库</Link>
          <a href="/docs" className="hover:text-gray-900" target="_blank">API</a>
        </nav>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <>
      <NavBar />
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/:namespace/:name" element={<RepoPage />} />
          <Route path="*" element={<div className="text-center py-20 text-gray-500">404 Not Found</div>} />
        </Routes>
      </main>
    </>
  );
}
